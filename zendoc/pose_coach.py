from .db import get_db, now_iso


POSE_EXERCISES = ("squat", "push_up", "bicep_curl", "lunge", "jumping_jack", "plank")


def _value(user, key, default=None):
    if user is None:
        return default
    if hasattr(user, "keys") and key in user.keys():
        return user[key]
    return user.get(key, default) if isinstance(user, dict) else default


def save_pose_session(actor, data):
    if _value(actor, "role") != "patient":
        raise PermissionError("Only patients can save pose-coach sessions.")
    exercise = str(data.get("exercise") or "squat").strip().lower().replace("-", "_").replace(" ", "_")
    if exercise not in POSE_EXERCISES:
        raise ValueError("Unsupported pose-coach exercise.")
    reps = max(0, int(data.get("reps") or 0))
    sets = max(0, int(data.get("sets") or 0))
    duration_seconds = max(0, int(data.get("duration_seconds") or 0))
    confidence = data.get("confidence")
    confidence = float(confidence) if confidence not in (None, "") else None
    now = now_iso()
    cursor = get_db().execute(
        """
        INSERT INTO fitness_pose_sessions
        (user_id, exercise, reps, sets, duration_seconds, confidence, status, notes, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 'completed', ?, ?)
        """,
        (
            _value(actor, "id"),
            exercise,
            reps,
            sets,
            duration_seconds,
            confidence,
            str(data.get("notes") or "").strip()[:500] or None,
            now,
        ),
    )
    feedback = str(data.get("feedback") or "Camera session saved. Review form cues with a qualified trainer if pain occurs.").strip()
    get_db().execute(
        "INSERT INTO fitness_pose_feedback (pose_session_id, feedback_type, message, confidence, created_at) VALUES (?, 'basic_form', ?, ?, ?)",
        (cursor.lastrowid, feedback[:500], confidence, now),
    )
    get_db().commit()
    return get_pose_session(actor, cursor.lastrowid)


def get_pose_session(actor, session_id):
    row = get_db().execute(
        "SELECT * FROM fitness_pose_sessions WHERE id=? AND user_id=?",
        (int(session_id), _value(actor, "id")),
    ).fetchone()
    if not row:
        raise LookupError("Pose session not found.")
    return dict(row)


def list_pose_sessions(actor):
    rows = get_db().execute(
        "SELECT * FROM fitness_pose_sessions WHERE user_id=? ORDER BY created_at DESC LIMIT 50",
        (_value(actor, "id"),),
    ).fetchall()
    return [dict(row) for row in rows]
