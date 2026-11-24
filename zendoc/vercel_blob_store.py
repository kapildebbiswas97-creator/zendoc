"""Private Vercel Blob operations used by Vercel-hosted ZENDOC storage."""
from __future__ import annotations

import os


class VercelBlobStore:
    """Small, bounded adapter over the official synchronous Blob SDK."""

    def __init__(self, prefix: str):
        self.prefix = prefix.rstrip("/") + "/"

    def _client(self):
        try:
            from vercel.blob import sync as blob
        except ImportError as exc:
            raise RuntimeError(
                "vercel-blob is required for Vercel Blob storage."
            ) from exc
        return blob

    def key(self, value: str) -> str:
        key = str(value or "").strip()
        if (
            not key.startswith(self.prefix)
            or key.startswith("/")
            or ".." in key.split("/")
            or "//" in key
        ):
            raise ValueError("Storage key is invalid.")
        return key

    def save(self, key: str, body: bytes, content_type: str) -> tuple[str, int]:
        if not body:
            raise ValueError("Uploaded file is empty.")
        blob = self._client()
        result = blob.put_blob(
            self.key(key),
            body,
            access="private",
            content_type=content_type or "application/octet-stream",
        )
        metadata = blob.head_blob(result.pathname)
        if metadata.size != len(body):
            try:
                blob.delete_blob(result.pathname)
            finally:
                raise RuntimeError("Vercel Blob upload verification failed.")
        return result.pathname, metadata.size

    def delete(self, key: str):
        self._client().delete_blob(self.key(key))

    def read(self, key: str, max_bytes: int) -> tuple[bytes, str | None]:
        blob = self._client()
        pathname = self.key(key)
        metadata = blob.head_blob(pathname)
        if metadata.size > max_bytes:
            raise ValueError("Stored file exceeds the bounded read limit.")
        result = blob.get_blob(pathname, access="private")
        if len(result.body) > max_bytes:
            raise ValueError("Stored file exceeds the bounded read limit.")
        return result.body, result.metadata.content_type

    def status(self) -> dict:
        try:
            from flask import current_app, has_app_context
            verified = bool(has_app_context() and current_app.config.get("STORAGE_VERIFIED"))
        except (ImportError, RuntimeError):
            verified = False
        configured = bool(
            os.environ.get("BLOB_STORE_ID")
            or os.environ.get("BLOB_READ_WRITE_TOKEN")
            or os.environ.get("VERCEL_BLOB_READ_WRITE_TOKEN")
        )
        return {
            "provider": "vercel_blob",
            "status": "configured_unverified" if configured else "integration_required",
            "access": "private",
            "scope": "durable_private_object_storage",
            "durable_ready": verified,
            "truth_notice": (
                "A connected private Vercel Blob store is configured; a real save/read/delete "
                "operation is still required before claiming storage is verified."
                if configured
                else "Connect a private Vercel Blob store to this project before accepting uploads."
            ),
        }
