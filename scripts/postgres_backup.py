"""Create a least-privilege PostgreSQL backup without putting DATABASE_URL in argv.

This operator tool is intended for self-managed deployments such as the
zero-budget OCI beta path. It produces a PostgreSQL custom-format archive,
SHA-256 checksum and non-secret manifest. It does not upload or claim a backup
is durable; the operator must copy the artifact off-instance and verify it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit


class BackupError(RuntimeError):
    pass


def connection_environment(database_url: str) -> dict[str, str]:
    """Translate a PostgreSQL URL into libpq environment variables.

    Keeping the password in PGPASSWORD avoids exposing the full connection URL
    in the pg_dump process arguments. The child receives only the small set of
    environment variables required by libpq and the executable search path.
    """
    parsed = urlsplit(str(database_url or "").strip())
    if parsed.scheme not in {"postgresql", "postgres"}:
        raise BackupError("DATABASE_URL must use postgresql:// or postgres://.")
    if not parsed.hostname:
        raise BackupError("DATABASE_URL is missing a PostgreSQL host.")
    database = unquote(parsed.path.lstrip("/"))
    if not database:
        raise BackupError("DATABASE_URL is missing a PostgreSQL database name.")

    env = {
        "PGHOST": parsed.hostname,
        "PGPORT": str(parsed.port or 5432),
        "PGDATABASE": database,
    }
    if parsed.username:
        env["PGUSER"] = unquote(parsed.username)
    if parsed.password:
        env["PGPASSWORD"] = unquote(parsed.password)

    query = parse_qs(parsed.query, keep_blank_values=False)
    sslmode = (query.get("sslmode") or [None])[0]
    if sslmode:
        env["PGSSLMODE"] = str(sslmode)
    return env


def _child_environment(database_url: str) -> dict[str, str]:
    child = {
        key: value
        for key in ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "TEMP", "TMP")
        if (value := os.environ.get(key))
    }
    child.update(connection_environment(database_url))
    return child


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_backup(database_url: str, output_dir: Path, *, pg_dump: str = "pg_dump") -> dict:
    executable = shutil.which(pg_dump)
    if not executable:
        raise BackupError(f"{pg_dump!r} was not found on PATH.")

    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        output_dir.chmod(0o700)
    except OSError:
        pass

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    final_path = output_dir / f"zendoc-postgres-{timestamp}.dump"
    with tempfile.NamedTemporaryFile(
        prefix=".zendoc-postgres-",
        suffix=".dump",
        dir=output_dir,
        delete=False,
    ) as temp_handle:
        temp_path = Path(temp_handle.name)

    try:
        command = [
            executable,
            "--format=custom",
            "--no-owner",
            "--no-privileges",
            "--file",
            str(temp_path),
        ]
        result = subprocess.run(
            command,
            env=_child_environment(database_url),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            message = (result.stderr or "pg_dump failed").strip().splitlines()[-1]
            raise BackupError(f"pg_dump failed: {message[:500]}")
        if not temp_path.exists() or temp_path.stat().st_size <= 0:
            raise BackupError("pg_dump returned success but produced an empty archive.")

        temp_path.chmod(0o600)
        temp_path.replace(final_path)
        final_path.chmod(0o600)

        checksum = _sha256(final_path)
        checksum_path = final_path.with_suffix(final_path.suffix + ".sha256")
        checksum_path.write_text(f"{checksum}  {final_path.name}\n", encoding="utf-8")
        checksum_path.chmod(0o600)

        manifest = {
            "format": "postgresql_custom",
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "archive": final_path.name,
            "size_bytes": final_path.stat().st_size,
            "sha256": checksum,
            "off_instance_copy_verified": False,
            "restore_drill_verified": False,
        }
        manifest_path = final_path.with_suffix(final_path.suffix + ".json")
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        manifest_path.chmod(0o600)
        return {
            **manifest,
            "archive": str(final_path),
            "checksum": str(checksum_path),
            "manifest": str(manifest_path),
        }
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        default=os.environ.get("ZENDOC_POSTGRES_BACKUP_DIR", "/var/backups/zendoc"),
    )
    parser.add_argument("--pg-dump", default="pg_dump")
    args = parser.parse_args()

    database_url = str(os.environ.get("DATABASE_URL") or "").strip()
    if not database_url:
        print("Backup FAILED: DATABASE_URL is not configured.", file=sys.stderr)
        return 2

    try:
        result = create_backup(database_url, Path(args.output_dir), pg_dump=args.pg_dump)
    except BackupError as error:
        print(f"Backup FAILED: {error}", file=sys.stderr)
        return 1

    # Print only non-secret artifact metadata. Never echo DATABASE_URL.
    print(json.dumps(result, indent=2))
    print(
        "Backup created locally. ZENDOC_BACKUP_VERIFIED must remain false until "
        "this archive is copied off-instance and a restore drill is verified."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
