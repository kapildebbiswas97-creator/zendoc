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

    def save(self, upload, original_filename: str) -> StoredRecord:
        storage_key = f"{secrets.token_hex(16)}-{original_filename}"
        root = self._root()
        destination = (root / storage_key).resolve()
        if destination.parent != root:
            raise ValueError("Upload destination is invalid.")
        upload.save(destination)
        return StoredRecord(self.name, storage_key, destination.stat().st_size)

    def delete(self, storage_key: str):
        root = self._root()
        target = (root / str(storage_key)).resolve()
        if target.parent != root:
            raise ValueError("Storage key is invalid.")
        target.unlink(missing_ok=True)

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

    def response(self, storage_key: str, download_name: str):
        self._raise()

    def status(self) -> dict:
        return {"provider": self.name, "status": "integration_required"}


def get_record_storage():
    provider = str(current_app.config.get("STORAGE_PROVIDER") or "local").strip().lower()
    if provider == "local":
        return LocalRecordStorage()
    return UnavailableExternalRecordStorage(provider)
