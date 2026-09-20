"""Private, non-diagnostic mental-wellness tracking for ZENDOC.

This module stores only user-entered wellbeing check-ins and private journal
entries. It deliberately does not infer diagnoses, personality traits, risk
scores, medication decisions, or clinical conclusions from those entries.
"""
from __future__ import annotations

from .db import get_db, now_iso


def ensure_mental_wellness_schema():
    get_db().executescript(
        """
        CREATE TABLE IF NOT EXISTS mental_wellness_checkins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            mood_level INTEGER NOT NULL,
            stress_level INTEGER NOT NULL,
            energy_level INTEGER NOT NULL,
            sleep_quality INTEGER NOT NULL,
            note TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_mental_wellness_checkins_user
            ON mental_wellness_checkins(user_id, created_at, id);

        CREATE TABLE IF NOT EXISTS mental_wellness_journal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title TEXT,
            body TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_mental_wellness_journal_user
            ON mental_wellness_journal(user_id, created_at, id);
        """
    )


def _user_id(user) -> int:
    if user is None:
        raise PermissionError("Authentication required.")
    if hasattr(user, "keys") and "id" in user.keys():
        return int(user["id"])
    return int(user.get("id") or 0)


def _score(value, label: str) -> int:
    try:
        score = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a number from 0 to 10.") from exc
    if score < 0 or score > 10:
        raise ValueError(f"{label} must be between 0 and 10.")
    return score


def _clean_text(value, limit: int) -> str:
    return " ".join(str(value or "").strip().split())[:limit]


def record_checkin(user, data) -> dict:
    ensure_mental_wellness_schema()
    uid = _user_id(user)
    now = now_iso()
    mood = _score(data.get("mood_level"), "Mood")
    stress = _score(data.get("stress_level"), "Stress")
    energy = _score(data.get("energy_level"), "Energy")
    sleep = _score(data.get("sleep_quality"), "Sleep quality")
    note = _clean_text(data.get("note"), 1000) or None
    cursor = get_db().execute(
        """
        INSERT INTO mental_wellness_checkins
        (user_id,mood_level,stress_level,energy_level,sleep_quality,note,created_at)
        VALUES (?,?,?,?,?,?,?)
        """,
        (uid, mood, stress, energy, sleep, note, now),
    )
    get_db().commit()
    return {
        "id": int(cursor.lastrowid),
        "mood_level": mood,
        "stress_level": stress,
        "energy_level": energy,
        "sleep_quality": sleep,
        "note": note,
        "created_at": now,
    }


def list_checkins(user, limit: int = 14) -> list[dict]:
    ensure_mental_wellness_schema()
    rows = get_db().execute(
        """
        SELECT id,mood_level,stress_level,energy_level,sleep_quality,note,created_at
        FROM mental_wellness_checkins
        WHERE user_id=?
        ORDER BY created_at DESC,id DESC
        LIMIT ?
        """,
        (_user_id(user), max(1, min(int(limit or 14), 60))),
    ).fetchall()
    return [dict(row) for row in rows]


def create_journal_entry(user, data) -> dict:
    ensure_mental_wellness_schema()
    uid = _user_id(user)
    title = _clean_text(data.get("title"), 140) or None
    body = str(data.get("body") or "").strip()
    if not body:
        raise ValueError("Write something before saving your private journal entry.")
    if len(body) > 6000:
        raise ValueError("Journal entries must be 6000 characters or fewer.")
    now = now_iso()
    cursor = get_db().execute(
        """
        INSERT INTO mental_wellness_journal
        (user_id,title,body,created_at,updated_at)
        VALUES (?,?,?,?,?)
        """,
        (uid, title, body, now, now),
    )
    get_db().commit()
    return {
        "id": int(cursor.lastrowid),
        "title": title,
        "body": body,
        "created_at": now,
        "updated_at": now,
    }


def list_journal_entries(user, limit: int = 20) -> list[dict]:
    ensure_mental_wellness_schema()
    rows = get_db().execute(
        """
        SELECT id,title,body,created_at,updated_at
        FROM mental_wellness_journal
        WHERE user_id=?
        ORDER BY created_at DESC,id DESC
        LIMIT ?
        """,
        (_user_id(user), max(1, min(int(limit or 20), 100))),
    ).fetchall()
    return [dict(row) for row in rows]


def delete_journal_entry(user, entry_id: int) -> None:
    ensure_mental_wellness_schema()
    cursor = get_db().execute(
        "DELETE FROM mental_wellness_journal WHERE id=? AND user_id=?",
        (int(entry_id), _user_id(user)),
    )
    if int(cursor.rowcount or 0) != 1:
        get_db().rollback()
        raise LookupError("Private journal entry not found.")
    get_db().commit()


def wellness_summary(user) -> dict:
    """Return descriptive user-entered history only; never a diagnosis or risk score."""
    checkins = list_checkins(user, 7)
    if not checkins:
        return {"count": 0, "latest": None, "averages": None}
    keys = ("mood_level", "stress_level", "energy_level", "sleep_quality")
    averages = {
        key: round(sum(int(item[key]) for item in checkins) / len(checkins), 1)
        for key in keys
    }
    return {"count": len(checkins), "latest": checkins[0], "averages": averages}
