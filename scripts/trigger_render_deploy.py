"""Trigger a Render deploy hook without exposing the secret URL."""
from __future__ import annotations

import sys
import urllib.parse
import urllib.request


def fail(message: str) -> None:
    print(f"Render deploy trigger FAILED: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> int:
    if len(sys.argv) != 2:
        fail("expected a single deploy hook URL argument")
    raw = str(sys.argv[1] or "").strip()
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme != "https" or not parsed.netloc:
        fail("deploy hook must be an absolute HTTPS URL")
    if not parsed.hostname or not parsed.hostname.endswith("render.com"):
        fail("deploy hook host must be a Render domain")

    request = urllib.request.Request(
        raw,
        headers={"User-Agent": "ZENDOC-Render-Deploy-Trigger/1.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            status = int(response.status)
    except Exception as error:
        fail(f"request failed: {type(error).__name__}")

    if status < 200 or status >= 300:
        fail(f"unexpected HTTP status {status}")
    print("Render deploy hook accepted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
