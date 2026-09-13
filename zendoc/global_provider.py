from __future__ import annotations

from .db import get_db, now_iso
from .global_source_registry import COUNTRIES


def set_provider_country(user, country_code: str) -> dict:
    if not user or user["role"] not in {"doctor", "hospital", "pharmacy"}:
        raise PermissionError("Only provider accounts may set provider jurisdiction.")
    code = str(country_code or "").strip().upper()
    country = COUNTRIES.get(code)
    if not country:
        raise ValueError("Unsupported provider country.")
    db = get_db()
    profile = db.execute("SELECT * FROM provider_profiles WHERE user_id=?", (int(user["id"]),)).fetchone()
    if not profile:
        raise LookupError("Create the provider profile before setting its country.")
    changed = str(profile["country_code"] or "").upper() != code
    db.execute(
        """
        UPDATE provider_profiles
        SET country_code=?,country_name=?,verification_status=CASE WHEN ? THEN 'pending' ELSE verification_status END,updated_at=?
        WHERE user_id=?
        """,
        (code, country["country_name"], 1 if changed else 0, now_iso(), int(user["id"])),
    )
    db.commit()
    row = db.execute("SELECT * FROM provider_profiles WHERE user_id=?", (int(user["id"]),)).fetchone()
    return dict(row)


def supported_provider_countries() -> list[dict]:
    return [
        {"country_code": code, "country_name": COUNTRIES[code]["country_name"]}
        for code in sorted(COUNTRIES)
    ]
