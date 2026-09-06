"""Repository secret-pattern gate for CI.

Scans tracked source-like files and reports only file/line/category.
It intentionally never prints the matched secret value.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


MAX_BYTES = 2 * 1024 * 1024

SKIP_PREFIXES = (
    ".git/",
    ".venv/",
    "venv/",
    "node_modules/",
    "instance/",
    "uploads/",
    "backups/",
)

SKIP_SUFFIXES = (
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip",
    ".db", ".sqlite", ".sqlite3", ".pyc", ".woff", ".woff2", ".ttf",
)

PATTERNS = (
    ("private-key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{30,}\b")),
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b")),
    ("stripe-live-key", re.compile(r"\b(?:sk|rk)_live_[0-9A-Za-z]{16,}\b")),
    ("generic-secret-assignment", re.compile(
        r"""(?ix)
        \b(?:api[_-]?key|access[_-]?token|auth[_-]?token|secret|password)
        \s*[:=]\s*
        ["']
        (?!development-only|test-secret|ci-only|CI-Only|zendoc_ci_password)
        [^"'\s]{20,}
        ["']
        """
    )),
)

SAFE_LINE_MARKERS = (
    "example.invalid",
    "example.com",
    "development-only-secret-key",
    "test-secret",
    "ci-only-secret-key",
    "CI-Only-Strong-Password",
    "zendoc_ci_password",
    "YOUR_API_KEY",
    "<api-key>",
    "${{ secrets.",
    "os.environ.get(",
)


def tracked_files() -> list[Path]:
    output = subprocess.check_output(["git", "ls-files", "-z"])
    names = output.decode("utf-8", errors="ignore").split("\0")
    return [Path(name) for name in names if name]


def should_scan(path: Path) -> bool:
    posix = path.as_posix()
    if any(posix.startswith(prefix) for prefix in SKIP_PREFIXES):
        return False
    if path.suffix.lower() in SKIP_SUFFIXES:
        return False
    try:
        return path.stat().st_size <= MAX_BYTES
    except OSError:
        return False


def main() -> int:
    findings: list[tuple[str, int, str]] = []
    for path in tracked_files():
        if not should_scan(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if any(marker in line for marker in SAFE_LINE_MARKERS):
                continue
            for category, pattern in PATTERNS:
                if pattern.search(line):
                    findings.append((path.as_posix(), lineno, category))

    if findings:
        print("Potential committed secrets detected:", file=sys.stderr)
        for filename, lineno, category in findings:
            print(f"  {filename}:{lineno} [{category}]", file=sys.stderr)
        print("Matched values are intentionally suppressed.", file=sys.stderr)
        return 1

    print("Repository secret-pattern gate PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
