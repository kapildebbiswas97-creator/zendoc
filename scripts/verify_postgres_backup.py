"""Verify a ZENDOC PostgreSQL backup archive without modifying a database."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path


class VerificationError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_backup(archive: Path, *, pg_restore: str = "pg_restore") -> dict:
    archive = archive.expanduser().resolve()
    if not archive.is_file() or archive.stat().st_size <= 0:
        raise VerificationError("Backup archive is missing or empty.")

    checksum_path = archive.with_suffix(archive.suffix + ".sha256")
    manifest_path = archive.with_suffix(archive.suffix + ".json")
    if not checksum_path.is_file():
        raise VerificationError("Checksum sidecar is missing.")
    if not manifest_path.is_file():
        raise VerificationError("Backup manifest is missing.")

    expected = checksum_path.read_text(encoding="utf-8").strip().split()[0]
    actual = sha256(archive)
    if expected.lower() != actual.lower():
        raise VerificationError("SHA-256 checksum mismatch.")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as error:
        raise VerificationError("Backup manifest is not valid JSON.") from error
    if manifest.get("archive") != archive.name:
        raise VerificationError("Backup manifest does not match the archive filename.")
    if manifest.get("sha256") != actual:
        raise VerificationError("Backup manifest checksum does not match the archive.")

    executable = shutil.which(pg_restore)
    if not executable:
        raise VerificationError(f"{pg_restore!r} was not found on PATH.")
    result = subprocess.run(
        [executable, "--list", str(archive)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or "pg_restore could not read the archive").strip().splitlines()[-1]
        raise VerificationError(detail[:500])

    entries = [line for line in result.stdout.splitlines() if line and not line.startswith(";")]
    return {
        "status": "archive_verified",
        "archive": archive.name,
        "size_bytes": archive.stat().st_size,
        "sha256": actual,
        "catalog_entries": len(entries),
        "restore_drill_verified": False,
        "note": (
            "Checksum and pg_restore catalog are valid. A separate restore into "
            "an isolated temporary PostgreSQL database is still required before "
            "setting ZENDOC_BACKUP_VERIFIED=true."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive")
    parser.add_argument("--pg-restore", default="pg_restore")
    args = parser.parse_args()
    try:
        result = verify_backup(Path(args.archive), pg_restore=args.pg_restore)
    except VerificationError as error:
        print(f"Backup verification FAILED: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
