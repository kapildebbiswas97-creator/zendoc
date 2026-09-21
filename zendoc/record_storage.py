"""Medical-record storage provider abstraction.

Local storage is real and available for development. External object storage is
never reported as working until a concrete adapter is installed and tested.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from flask import current_app, send_file, send_from_directory


@dataclass(frozen=True)
class StoredRecord:
    provider: str
    storage_key: str
    size_bytes: int


class LocalRecordStorage:
    name = "local"

    def _root(self) -> Path:
        root = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _path(self, storage_key: str) -> Path:
        root = self._root()
        target = (root / str(storage_key)).resolve()
        if target.parent != root:
            raise ValueError("Storage key is invalid.")
        return target

    def save(self, upload, original_filename: str) -> StoredRecord:
        storage_key = f"{secrets.token_hex(16)}-{original_filename}"
        destination = self._path(storage_key)
        upload.save(destination)
        return StoredRecord(self.name, storage_key, destination.stat().st_size)

    def delete(self, storage_key: str):
        self._path(storage_key).unlink(missing_ok=True)

    def read_bytes(self, storage_key: str, *, max_bytes: int = 1_048_576) -> bytes:
        try:
            max_bytes = int(max_bytes)
        except (TypeError, ValueError) as error:
            raise ValueError("max_bytes must be an integer.") from error
        if max_bytes < 1 or max_bytes > 10_485_760:
            raise ValueError("max_bytes must be between 1 byte and 10 MiB.")
        target = self._path(storage_key)
        if not target.exists() or not target.is_file():
            raise LookupError("Stored medical record was not found.")
        if target.stat().st_size > max_bytes:
            raise ValueError("Stored medical record exceeds the bounded read limit.")
        return target.read_bytes()

    def response(self, storage_key: str, download_name: str):
        return send_from_directory(self._root(), storage_key, as_attachment=True, download_name=download_name)

    def status(self) -> dict:
        return {"provider": self.name, "status": "working", "scope": "development_local_filesystem"}


class S3CompatibleRecordStorage:
    """S3-compatible durable object storage (AWS S3, R2, MinIO and similar).

    Configuration proves only that an adapter is configured. Individual
    save/read/delete calls remain the authoritative evidence that the remote
    service actually succeeded.
    """

    name = "s3"

    def _settings(self):
        required = {
            "bucket": str(current_app.config.get("S3_BUCKET") or "").strip(),
            "access_key": str(current_app.config.get("S3_ACCESS_KEY_ID") or "").strip(),
            "secret_key": str(current_app.config.get("S3_SECRET_ACCESS_KEY") or ""),
        }
        missing = [key for key, value in required.items() if not value]
        if missing:
            raise RuntimeError(
                "S3-compatible medical-record storage is not fully configured: "
                + ", ".join(missing)
            )
        return {
            **required,
            "endpoint_url": str(current_app.config.get("S3_ENDPOINT_URL") or "").strip() or None,
            "region": str(current_app.config.get("S3_REGION") or "auto").strip() or "auto",
            "sse": str(current_app.config.get("S3_SERVER_SIDE_ENCRYPTION") or "").strip(),
        }

    def _client(self):
        settings = self._settings()
        try:
            import boto3
        except ImportError as exc:
            raise RuntimeError("boto3 is required for S3-compatible record storage.") from exc
        return boto3.client(
            "s3",
            endpoint_url=settings["endpoint_url"],
            region_name=settings["region"],
            aws_access_key_id=settings["access_key"],
            aws_secret_access_key=settings["secret_key"],
        ), settings

    def _key(self, storage_key: str) -> str:
        key = str(storage_key or "").strip()
        if not key or key.startswith("/") or ".." in key.split("/"):
            raise ValueError("Storage key is invalid.")
        return key

    def save(self, upload, original_filename: str) -> StoredRecord:
        key = f"medical-records/{secrets.token_hex(16)}-{Path(original_filename).name}"
        client, settings = self._client()
        extra = {}
        mimetype = str(getattr(upload, "mimetype", "") or "").strip()
        if mimetype:
            extra["ContentType"] = mimetype
        if settings["sse"]:
            extra["ServerSideEncryption"] = settings["sse"]
        if extra:
            client.upload_fileobj(
                upload.stream,
                settings["bucket"],
                key,
                ExtraArgs=extra,
            )
        else:
            client.upload_fileobj(upload.stream, settings["bucket"], key)
        head = client.head_object(Bucket=settings["bucket"], Key=key)
        return StoredRecord(self.name, key, int(head.get("ContentLength") or 0))

    def delete(self, storage_key: str):
        client, settings = self._client()
        client.delete_object(Bucket=settings["bucket"], Key=self._key(storage_key))

    def read_bytes(self, storage_key: str, *, max_bytes: int = 1_048_576) -> bytes:
        try:
            max_bytes = int(max_bytes)
        except (TypeError, ValueError) as error:
            raise ValueError("max_bytes must be an integer.") from error
        if max_bytes < 1 or max_bytes > 10_485_760:
            raise ValueError("max_bytes must be between 1 byte and 10 MiB.")
        client, settings = self._client()
        key = self._key(storage_key)
        head = client.head_object(Bucket=settings["bucket"], Key=key)
        size = int(head.get("ContentLength") or 0)
        if size > max_bytes:
            raise ValueError("Stored medical record exceeds the bounded read limit.")
        body = client.get_object(Bucket=settings["bucket"], Key=key)["Body"].read(max_bytes + 1)
        if len(body) > max_bytes:
            raise ValueError("Stored medical record exceeds the bounded read limit.")
        return body

    def response(self, storage_key: str, download_name: str):
        client, settings = self._client()
        key = self._key(storage_key)
        result = client.get_object(Bucket=settings["bucket"], Key=key)
        body = result["Body"].read(10_485_761)
        if len(body) > 10_485_760:
            raise ValueError("Stored medical record exceeds the configured 10 MiB download limit.")
        return send_file(
            BytesIO(body),
            as_attachment=True,
            download_name=download_name,
            mimetype=result.get("ContentType") or "application/octet-stream",
        )

    def status(self) -> dict:
        try:
            settings = self._settings()
        except RuntimeError as exc:
            return {
                "provider": self.name,
                "status": "integration_required",
                "scope": "durable_object_storage",
                "message": str(exc),
            }
        endpoint_url = settings["endpoint_url"]
        transport_secure = endpoint_url is None or str(endpoint_url).lower().startswith("https://")
        return {
            "provider": self.name,
            "status": "configured_unverified",
            "scope": "durable_object_storage",
            "bucket": settings["bucket"],
            "endpoint_configured": bool(endpoint_url),
            "transport_secure": transport_secure,
            "truth_notice": (
                "Configuration is present. A real object operation is still required "
                "to prove remote storage availability."
            ),
        }


class UnavailableExternalRecordStorage:
    def __init__(self, provider: str):
        self.name = provider

    def _raise(self):
        raise RuntimeError(f"Medical-record storage provider '{self.name}' is Integration Required.")

    def save(self, upload, original_filename: str):
        self._raise()

    def delete(self, storage_key: str):
        self._raise()

    def read_bytes(self, storage_key: str, *, max_bytes: int = 1_048_576):
        self._raise()

    def response(self, storage_key: str, download_name: str):
        self._raise()

    def status(self) -> dict:
        return {"provider": self.name, "status": "integration_required"}


def get_record_storage():
    provider = str(current_app.config.get("STORAGE_PROVIDER") or "local").strip().lower()
    if provider == "local":
        return LocalRecordStorage()
    if provider in {"s3", "s3_compatible", "r2"}:
        return S3CompatibleRecordStorage()
    return UnavailableExternalRecordStorage(provider)
