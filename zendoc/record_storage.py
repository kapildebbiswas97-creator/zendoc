"""Medical-record storage provider abstraction.

Local storage is real and available for development. External object storage is
never reported as working until a concrete adapter is installed and tested.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from pathlib import Path

from flask import current_app, send_from_directory


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
    return UnavailableExternalRecordStorage(provider)
