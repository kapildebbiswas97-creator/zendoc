"""Telehealth room provider boundary with a real local beta workflow."""
from __future__ import annotations

import secrets

from flask import current_app

from .security import hash_token


class LocalDemoTelehealthProvider:
    def __init__(self, name: str = "local_demo"):
        self.name = name

    def create_room(self, consultation_id: int) -> dict:
        room_token = secrets.token_urlsafe(32)
        return {
            "provider": self.name,
            "room_token_hash": hash_token(room_token),
            "status": "waiting",
            "integration_status": (
                "zendoc_browser_webrtc_beta"
                if self.name in {"internal_webrtc", "internal_chat"}
                else "beta_local_only"
            ),
        }

    def status(self):
        webrtc_enabled = self.name in {"internal_webrtc", "internal_chat"}
        return {
            "provider": self.name,
            "status": "beta",
            "supports_chat": True,
            "supports_voice": webrtc_enabled,
            "supports_video": webrtc_enabled,
            "message": (
                "ZENDOC consultation chat plus authenticated browser WebRTC voice/video are available. "
                "Public-network reliability still depends on configured STUN/TURN infrastructure and end-to-end browser testing."
                if webrtc_enabled else
                "Local consultation state and chat work; voice/video WebRTC is not enabled for this provider."
            ),
        }


class UnavailableTelehealthProvider:
    def __init__(self, name: str):
        self.name = name

    def create_room(self, consultation_id: int):
        raise RuntimeError(f"Telehealth provider '{self.name}' is Integration Required.")

    def status(self):
        return {
            "provider": self.name,
            "status": "integration_required",
            "supports_chat": False,
            "supports_voice": False,
            "supports_video": False,
        }


def get_telehealth_provider():
    provider = str(current_app.config.get("TELEHEALTH_PROVIDER") or "local_demo").strip().lower()
    if provider == "local_demo":
        return LocalDemoTelehealthProvider("local_demo")
    if provider in {"internal_chat", "internal_webrtc"}:
        return LocalDemoTelehealthProvider(provider)
    return UnavailableTelehealthProvider(provider)
