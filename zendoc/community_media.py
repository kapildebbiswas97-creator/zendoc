"""Storage and validation for user-generated Health Community media.

Local media storage is available for development. Public hosted releases should
use the already-configured S3-compatible durable storage boundary. Media bytes
are never treated as clinical evidence merely because they are stored by ZENDOC.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from flask import current_app, send_file, send_from_directory
from werkzeug.utils import secure_filename


MAX_COMMUNITY_MEDIA_BYTES = 25 * 1024 * 1024
ALLOWED_MEDIA_TYPES = {
    "image/jpeg": "image",
    "image/png": "image",
    "image/webp": "image",
    "video/mp4": "video",
    "video/webm": "video",
}
MESSAGE_MEDIA_TYPES = {
    **ALLOWED_MEDIA_TYPES,
    "audio/webm": "audio",
    "audio/ogg": "audio",
    "audio/mp4": "audio",
}
EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/mp4": ".m4a",
}


@dataclass(frozen=True)
class StoredCommunityMedia:
    provider: str
    storage_key: str
    original_filename: str
    mime_type: str
    media_kind: str
    size_bytes: int


def _looks_like_supported_bytes(mime_type: str, header: bytes) -> bool:
    if mime_type == "image/jpeg":
        return header.startswith(b"\xff\xd8\xff")
    if mime_type == "image/png":
        return header.startswith(b"\x89PNG\r\n\x1a\n")
    if mime_type == "image/webp":
        return len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WEBP"
    if mime_type == "video/mp4":
        return len(header) >= 12 and header[4:8] == b"ftyp"
    if mime_type in {"video/webm", "audio/webm"}:
        return header.startswith(b"\x1aE\xdf\xa3")
    if mime_type == "audio/ogg":
        return header.startswith(b"OggS")
    if mime_type == "audio/mp4":
        return len(header) >= 12 and header[4:8] == b"ftyp"
    return False


def validate_community_upload(upload, *, allowed_media_types=None):
    allowed = allowed_media_types or ALLOWED_MEDIA_TYPES
    if not upload or not getattr(upload, "filename", ""):
        raise ValueError("Choose a supported media file to upload.")
    mime_type = str(getattr(upload, "mimetype", "") or "").lower().strip()
    if mime_type not in allowed:
        if allowed is MESSAGE_MEDIA_TYPES:
            raise ValueError("Private message media must be JPEG, PNG, WebP, MP4, WebM, OGG audio, or M4A/MP4 audio.")
        raise ValueError("Community media must be JPEG, PNG, WebP, MP4, or WebM.")

    stream = upload.stream
    start = stream.tell()
    header = stream.read(32)
    stream.seek(start)
    if not _looks_like_supported_bytes(mime_type, header):
        raise ValueError("The uploaded file content does not match its declared media type.")

    # Prefer content_length when available, but never trust it as the only bound.
    advertised = int(getattr(upload, "content_length", 0) or 0)
    if advertised > MAX_COMMUNITY_MEDIA_BYTES:
        raise ValueError("Community media must be 25 MiB or smaller.")

    safe_name = secure_filename(str(upload.filename))
    if not safe_name:
        safe_name = "community-media" + EXTENSIONS[mime_type]
    return mime_type, safe_name


class LocalCommunityMediaStorage:
    name = "local"

    def _root(self) -> Path:
        root = Path(current_app.instance_path) / "community-media"
        root.mkdir(parents=True, exist_ok=True)
        return root.resolve()

    def _path(self, storage_key: str) -> Path:
        root = self._root()
        key = str(storage_key or "").strip()
        target = (root / key).resolve()
        if target.parent != root:
            raise ValueError("Community media storage key is invalid.")
        return target

    def save(self, upload, *, allowed_media_types=None) -> StoredCommunityMedia:
        allowed = allowed_media_types or ALLOWED_MEDIA_TYPES
        mime_type, original_name = validate_community_upload(upload, allowed_media_types=allowed)
        key = f"{secrets.token_hex(20)}{EXTENSIONS[mime_type]}"
        destination = self._path(key)

        total = 0
        with destination.open("wb") as handle:
            while True:
                chunk = upload.stream.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_COMMUNITY_MEDIA_BYTES:
                    handle.close()
                    destination.unlink(missing_ok=True)
                    raise ValueError("Community media must be 25 MiB or smaller.")
                handle.write(chunk)
        if total == 0:
            destination.unlink(missing_ok=True)
            raise ValueError("Uploaded community media is empty.")
        return StoredCommunityMedia(
            provider=self.name,
            storage_key=key,
            original_filename=original_name,
            mime_type=mime_type,
            media_kind=allowed[mime_type],
            size_bytes=total,
        )

    def delete(self, storage_key: str):
        self._path(storage_key).unlink(missing_ok=True)

    def read_bytes(self, storage_key: str, *, max_bytes: int = MAX_COMMUNITY_MEDIA_BYTES) -> bytes:
        limit = max(1, min(int(max_bytes), MAX_COMMUNITY_MEDIA_BYTES))
        target = self._path(storage_key)
        if not target.exists() or not target.is_file():
            raise LookupError("Stored community media was not found.")
        if target.stat().st_size > limit:
            raise ValueError("Stored community media exceeds the bounded read limit.")
        return target.read_bytes()

    def response(self, storage_key: str, *, mime_type: str, download_name: str):
        return send_from_directory(
            self._root(),
            self._path(storage_key).name,
            mimetype=mime_type,
            as_attachment=False,
            download_name=download_name,
            max_age=3600,
        )

    def status(self) -> dict:
        return {
            "provider": self.name,
            "status": "working",
            "scope": "development_local_community_media",
            "durable_public_ready": False,
        }


class S3CommunityMediaStorage:
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
                "S3-compatible community-media storage is not fully configured: "
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
            raise RuntimeError("boto3 is required for S3-compatible community media.") from exc
        return boto3.client(
            "s3",
            endpoint_url=settings["endpoint_url"],
            region_name=settings["region"],
            aws_access_key_id=settings["access_key"],
            aws_secret_access_key=settings["secret_key"],
        ), settings

    def _key(self, storage_key: str) -> str:
        key = str(storage_key or "").strip()
        if not key.startswith("community-media/") or ".." in key.split("/"):
            raise ValueError("Community media storage key is invalid.")
        return key

    def save(self, upload, *, allowed_media_types=None) -> StoredCommunityMedia:
        allowed = allowed_media_types or ALLOWED_MEDIA_TYPES
        mime_type, original_name = validate_community_upload(upload, allowed_media_types=allowed)
        # Bound the upload in memory to keep the maximum explicit and portable.
        body = upload.stream.read(MAX_COMMUNITY_MEDIA_BYTES + 1)
        if not body:
            raise ValueError("Uploaded community media is empty.")
        if len(body) > MAX_COMMUNITY_MEDIA_BYTES:
            raise ValueError("Community media must be 25 MiB or smaller.")

        key = f"community-media/{secrets.token_hex(20)}{EXTENSIONS[mime_type]}"
        client, settings = self._client()
        extra = {"ContentType": mime_type}
        if settings["sse"]:
            extra["ServerSideEncryption"] = settings["sse"]
        client.upload_fileobj(BytesIO(body), settings["bucket"], key, ExtraArgs=extra)
        head = client.head_object(Bucket=settings["bucket"], Key=key)
        stored_size = int(head.get("ContentLength") or 0)
        if stored_size != len(body):
            try:
                client.delete_object(Bucket=settings["bucket"], Key=key)
            finally:
                raise RuntimeError("Community media storage verification failed.")
        return StoredCommunityMedia(
            provider=self.name,
            storage_key=key,
            original_filename=original_name,
            mime_type=mime_type,
            media_kind=allowed[mime_type],
            size_bytes=stored_size,
        )

    def delete(self, storage_key: str):
        client, settings = self._client()
        client.delete_object(Bucket=settings["bucket"], Key=self._key(storage_key))

    def read_bytes(self, storage_key: str, *, max_bytes: int = MAX_COMMUNITY_MEDIA_BYTES) -> bytes:
        limit = max(1, min(int(max_bytes), MAX_COMMUNITY_MEDIA_BYTES))
        client, settings = self._client()
        key = self._key(storage_key)
        head = client.head_object(Bucket=settings["bucket"], Key=key)
        size = int(head.get("ContentLength") or 0)
        if size > limit:
            raise ValueError("Stored community media exceeds the bounded read limit.")
        body = client.get_object(Bucket=settings["bucket"], Key=key)["Body"].read(limit + 1)
        if len(body) > limit:
            raise ValueError("Stored community media exceeds the bounded read limit.")
        return body

    def response(self, storage_key: str, *, mime_type: str, download_name: str):
        client, settings = self._client()
        key = self._key(storage_key)
        head = client.head_object(Bucket=settings["bucket"], Key=key)
        size = int(head.get("ContentLength") or 0)
        if size > MAX_COMMUNITY_MEDIA_BYTES:
            raise ValueError("Stored community media exceeds the supported size.")
        result = client.get_object(Bucket=settings["bucket"], Key=key)
        body = result["Body"].read(MAX_COMMUNITY_MEDIA_BYTES + 1)
        if len(body) > MAX_COMMUNITY_MEDIA_BYTES:
            raise ValueError("Stored community media exceeds the supported size.")
        return send_file(
            BytesIO(body),
            mimetype=mime_type or result.get("ContentType") or "application/octet-stream",
            as_attachment=False,
            download_name=download_name,
            max_age=3600,
        )

    def status(self) -> dict:
        try:
            settings = self._settings()
        except RuntimeError as exc:
            return {
                "provider": self.name,
                "status": "integration_required",
                "scope": "durable_community_media",
                "message": str(exc),
                "durable_public_ready": False,
            }
        endpoint = settings["endpoint_url"]
        transport_secure = endpoint is None or endpoint.lower().startswith("https://")
        return {
            "provider": self.name,
            "status": "configured_unverified",
            "scope": "durable_community_media",
            "transport_secure": transport_secure,
            "durable_public_ready": bool(transport_secure and current_app.config.get("STORAGE_VERIFIED")),
            "truth_notice": (
                "Configuration is present. A real save/read/delete operation is still required "
                "before claiming public durable community-media availability."
            ),
        }


class UnavailableCommunityMediaStorage:
    def __init__(self, provider: str):
        self.name = provider

    def _raise(self):
        raise RuntimeError(f"Community media storage provider '{self.name}' is Integration Required.")

    def save(self, upload, *, allowed_media_types=None):
        self._raise()

    def delete(self, storage_key: str):
        self._raise()

    def read_bytes(self, storage_key: str, *, max_bytes: int = MAX_COMMUNITY_MEDIA_BYTES):
        self._raise()

    def response(self, storage_key: str, *, mime_type: str, download_name: str):
        self._raise()

    def status(self) -> dict:
        return {
            "provider": self.name,
            "status": "integration_required",
            "scope": "durable_community_media",
            "durable_public_ready": False,
        }


def get_community_media_storage():
    provider = str(current_app.config.get("STORAGE_PROVIDER") or "local").strip().lower()
    if provider == "local":
        return LocalCommunityMediaStorage()
    if provider in {"s3", "s3_compatible", "r2"}:
        return S3CommunityMediaStorage()
    return UnavailableCommunityMediaStorage(provider)
