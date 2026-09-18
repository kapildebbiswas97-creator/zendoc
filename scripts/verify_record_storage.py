#!/usr/bin/env python3
"""Perform a real save/read/delete smoke test against configured ZENDOC record storage.

Run this only in the target deployment environment after setting the storage
credentials. On success, it is reasonable to set ZENDOC_STORAGE_VERIFIED=true
for that same storage configuration.
"""
from __future__ import annotations

import io
import os
import sys

from werkzeug.datastructures import FileStorage

from zendoc import create_app
from zendoc.record_storage import get_record_storage


TEST_BYTES = b"zendoc-record-storage-verification-v1"


def main() -> int:
    app = create_app()
    with app.app_context():
        storage = get_record_storage()
        before = storage.status()
        print("Configured storage:", before)
        if before.get("status") == "integration_required":
            print("FAIL: configured storage provider is not ready.", file=sys.stderr)
            return 2

        upload = FileStorage(
            stream=io.BytesIO(TEST_BYTES),
            filename="zendoc-storage-smoke.txt",
            content_type="text/plain",
        )
        stored = None
        try:
            stored = storage.save(upload, "zendoc-storage-smoke.txt")
            recovered = storage.read_bytes(stored.storage_key, max_bytes=4096)
            if recovered != TEST_BYTES:
                print("FAIL: read-back bytes did not match saved bytes.", file=sys.stderr)
                return 1
            storage.delete(stored.storage_key)
            print(
                "PASS: real save/read/delete completed.",
                {"provider": stored.provider, "storage_key": stored.storage_key, "size_bytes": stored.size_bytes},
            )
            print("You may set ZENDOC_STORAGE_VERIFIED=true for this unchanged storage configuration.")
            return 0
        except Exception as exc:
            print(f"FAIL: real storage verification failed: {exc}", file=sys.stderr)
            if stored is not None:
                try:
                    storage.delete(stored.storage_key)
                except Exception:
                    pass
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
