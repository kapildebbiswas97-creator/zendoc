"""Telehealth room provider boundary with a real local beta workflow."""
from __future__ import annotations

import secrets

from flask import current_app

from .security import hash_token


class LocalDemoTelehealthProvider:
    name = "local_demo"

    def create_room(self, consultation_id: int) -> dict:
        room_token = secrets.token_urlsafe(32)
        return {
            "provider": self.name,
            "room_token_hash": hash_token(room_token),
            "status": "waiting",
            "integration_status": "beta_local_only",
        }

    def status(self):
        return {
            "provider": self.name,
            "status": "beta",
            "message": "Local consultation state and chat work; production WebRTC is Integration Required.",
        }


class UnavailableTelehealthProvider:
    def __init__(self, name: str):
        self.name = name

    def create_room(self, consultation_id: int):
        raise RuntimeError(f"Telehealth provider '{self.name}' is Integration Required.")

    def status(self):
        return {"provider": self.name, "status": "integration_required"}


def get_telehealth_provider():
    provider = str(current_app.config.get("TELEHEALTH_PROVIDER") or "local_demo").strip().lower()
    if provider == "local_demo":
        return LocalDemoTelehealthProvider()
    return UnavailableTelehealthProvider(provider)
