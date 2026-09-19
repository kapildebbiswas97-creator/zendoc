#!/usr/bin/env python3
"""Verify the configured ZENDOC Health Community media storage.

Run this in the target deployment environment after durable object-storage
credentials are configured. It performs a real save/read/delete cycle using a
small PNG-signature payload and does not create a Community post.
"""
from __future__ import annotations

import io
import sys

from werkzeug.datastructures import FileStorage

from zendoc import create_app
from zendoc.community_media import get_community_media_storage


TEST_BYTES = b"\x89PNG\r\n\x1a\n" + b"zendoc-community-media-verification-v1"


def main() -> int:
    app = create_app()
    with app.app_context():
        storage = get_community_media_storage()
        before = storage.status()
        print("Configured community media storage:", before)
        if before.get("status") == "integration_required":
            print("FAIL: configured community-media storage provider is not ready.", file=sys.stderr)
            return 2

        upload = FileStorage(
            stream=io.BytesIO(TEST_BYTES),
            filename="zendoc-community-media-smoke.png",
            content_type="image/png",
        )
        stored = None
        try:
            stored = storage.save(upload)
            recovered = storage.read_bytes(stored.storage_key, max_bytes=4096)
            if recovered != TEST_BYTES:
                print("FAIL: Community media read-back bytes did not match saved bytes.", file=sys.stderr)
                return 1
            storage.delete(stored.storage_key)
            print(
                "PASS: Community media save/read/delete completed.",
                {
                    "provider": stored.provider,
                    "storage_key": stored.storage_key,
                    "mime_type": stored.mime_type,
                    "size_bytes": stored.size_bytes,
                },
            )
            print(
                "When the medical-record storage smoke test also passes for the same unchanged "
                "configuration, ZENDOC_STORAGE_VERIFIED=true can represent both storage paths."
            )
            return 0
        except Exception as exc:
            print(f"FAIL: Community media storage verification failed: {exc}", file=sys.stderr)
            if stored is not None:
                try:
                    storage.delete(stored.storage_key)
                except Exception:
                    pass
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
