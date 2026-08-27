"""
Workout Tracking — session lifecycle management.

START SESSION → LOG SETS → FINISH SESSION → HEALTH TIMELINE EVENT

The session structure is deliberately designed for Milestone 6 Camera Coach:
  session_item.completed_reps  — can be populated by pose estimation
  session_item.form_notes      — can receive form feedback
"""

from .db import get_db, now_iso
from .health_timeline import add_timeline_event


def _user_id(user):
    return int(user["id"] if hasattr(user, "__getitem__") else getattr(user, "id", 0))


def start_session(user, plan_id=None, label=None):
    """
    Create a new workout session (status='active').
    If plan_id is provided, pre-populate session items from plan items.
    Returns the session dict.
    """
    uid = _user_id(user)
    db = get_db()
    now = now_iso()
    name = label or "Workout Session"

    # Validate plan ownership if provided
    if plan_id is not None:
        plan_row = db.execute("SELECT id, user_id, name FROM workout_plans WHERE id=?", (plan_id,)).fetchone()
        if not plan_row:
            raise LookupError("Workout plan not found.")
        if plan_row["user_id"] != uid:
            raise PermissionError("You cannot start a session from another user's plan.")
        name = plan_row["name"]

    cursor = db.execute(
        """INSERT INTO workout_sessions
        (user_id, plan_id, name, status, started_at, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?)""",
        (uid, plan_id, name, "active", now, now, now),
    )
    session_id = cursor.lastrowid

    # Pre-populate items from plan
    if plan_id is not None:
        items = db.execute(
            """SELECT wpi.*, e.name exercise_name
               FROM workout_plan_items wpi
               JOIN exercises e ON e.id=wpi.exercise_id
               WHERE wpi.plan_id=?
               ORDER BY wpi.day_number, wpi.order_in_day""",
            (plan_id,),
        ).fetchall()
        for item in items:
            db.execute(
                """INSERT INTO workout_session_items
                (session_id, exercise_id, planned_sets, planned_reps, rest_seconds,
                 completed_sets, created_at)
                VALUES (?,?,?,?,?,0,?)""",
                (session_id, item["exercise_id"], item["sets"], item["reps"],
                 item["rest_seconds"], now),
            )

    db.commit()
    return get_session(user, session_id)


def log_set(user, session_id, exercise_id, completed_reps=None, duration_seconds=None, notes=None, set_number=None):
    """
    Record a completed set within an active session.
    Returns updated session item dict.
    """
    uid = _user_id(user)
    db = get_db()
    now = now_iso()

    session = db.execute(
        "SELECT id, user_id, status FROM workout_sessions WHERE id=?", (session_id,)
    ).fetchone()
    if not session:
        raise LookupError("Session not found.")
    if session["user_id"] != uid:
        raise PermissionError("You cannot modify another user's session.")
    if session["status"] != "active":
        raise ValueError("Cannot log sets to a completed or cancelled session.")

    # Find existing item or create ad-hoc item
    item = db.execute(
        "SELECT * FROM workout_session_items WHERE session_id=? AND exercise_id=?",
        (session_id, exercise_id),
    ).fetchone()

    if item:
        db.execute(
            """INSERT INTO workout_set_logs
            (session_id, session_item_id, exercise_id, set_number,
             completed_reps, duration_seconds, notes, logged_at)
            VALUES (?,?,?,?,?,?,?,?)""",
            (
                session_id, item["id"], exercise_id,
                set_number or (item["completed_sets"] + 1),
                completed_reps, duration_seconds,
                str(notes or "")[:400] or None, now,
            ),
        )
        db.execute(
            "UPDATE workout_session_items SET completed_sets=completed_sets+1, updated_at=? WHERE id=?",
            (now, item["id"]),
        )
    else:
        # Ad-hoc exercise not from plan
        cursor = db.execute(
            """INSERT INTO workout_session_items
            (session_id, exercise_id, planned_sets, planned_reps, rest_seconds,
             completed_sets, created_at, updated_at)
            VALUES (?,?,?,?,?,1,?,?)""",
            (session_id, exercise_id, 1, str(completed_reps or ""), 60, now, now),
        )
        item_id = cursor.lastrowid
        db.execute(
            """INSERT INTO workout_set_logs
            (session_id, session_item_id, exercise_id, set_number,
             completed_reps, duration_seconds, notes, logged_at)
            VALUES (?,?,?,?,?,?,?,?)""",
            (session_id, item_id, exercise_id, 1, completed_reps, duration_seconds,
             str(notes or "")[:400] or None, now),
        )

    db.execute("UPDATE workout_sessions SET updated_at=? WHERE id=?", (now, session_id))
    db.commit()
    return {"session_id": session_id, "exercise_id": exercise_id, "logged_at": now}


def finish_session(user, session_id, notes=None):
    """
    Mark session as completed.
    Calculates duration, writes to health_timeline_events, returns summary.
    """
    uid = _user_id(user)
    db = get_db()
    now = now_iso()

    session = db.execute("SELECT * FROM workout_sessions WHERE id=?", (session_id,)).fetchone()
    if not session:
        raise LookupError("Session not found.")
    if session["user_id"] != uid:
        raise PermissionError("You cannot modify another user's session.")
    if session["status"] != "active":
        raise ValueError("Session is already completed or cancelled.")

    # Calculate duration in minutes
    try:
        from datetime import datetime, timezone
        started = datetime.fromisoformat(str(session["started_at"]).replace("Z", "+00:00"))
        finished = datetime.now(timezone.utc)
        duration_minutes = max(1, int((finished - started).total_seconds() / 60))
    except Exception:
        duration_minutes = 0

    items = db.execute(
        """SELECT wsi.*, e.name exercise_name, e.category
           FROM workout_session_items wsi
           JOIN exercises e ON e.id=wsi.exercise_id
           WHERE wsi.session_id=?""",
        (session_id,),
    ).fetchall()

    exercise_count = len(items)
    sets_completed = sum(i["completed_sets"] for i in items)

    db.execute(
        """UPDATE workout_sessions SET
        status='completed', finished_at=?, duration_minutes=?,
        notes=?, updated_at=? WHERE id=?""",
        (now, duration_minutes, str(notes or "")[:1000] or None, now, session_id),
    )
    db.commit()

    # Write health timeline event
    categories = list({i["category"] for i in items}) if items else []
    category_label = ", ".join(categories[:3]) if categories else "Mixed"
    timeline_summary = (
        f"{exercise_count} exercise{'s' if exercise_count != 1 else ''}, "
        f"{sets_completed} set{'s' if sets_completed != 1 else ''} completed. "
        f"{duration_minutes} min."
    )
    if notes:
        timeline_summary += f" Notes: {str(notes)[:200]}"

    try:
        add_timeline_event(
            patient_id=uid,
            event_type="fitness",
            title=f"Workout: {session['name']}",
            event_at=now,
            summary=timeline_summary,
            source="workout_tracking",
            source_ref=str(session_id),
            created_by=uid,
        )
    except Exception:
        pass  # Timeline write failure must not block session completion

    return {
        "session_id": session_id,
        "status": "completed",
        "duration_minutes": duration_minutes,
        "exercise_count": exercise_count,
        "sets_completed": sets_completed,
        "finished_at": now,
        "timeline_event_written": True,
    }


def get_session(user, session_id):
    """Return full session with items. Raises LookupError / PermissionError."""
    uid = _user_id(user)
    db = get_db()
    row = db.execute("SELECT * FROM workout_sessions WHERE id=?", (session_id,)).fetchone()
    if not row:
        raise LookupError("Session not found.")
    if row["user_id"] != uid:
        raise PermissionError("You cannot access another user's session.")
    session = dict(row)
    items = db.execute(
        """SELECT wsi.*, e.name exercise_name, e.category, e.muscle_group,
                  e.difficulty, e.instructions, e.camera_ready
           FROM workout_session_items wsi
           JOIN exercises e ON e.id=wsi.exercise_id
           WHERE wsi.session_id=?
           ORDER BY wsi.id""",
        (session_id,),
    ).fetchall()
    session["items"] = [dict(i) for i in items]
    return session


def list_sessions(user, page=1, per_page=20, start_date=None, end_date=None):
    """Return paginated session list (newest first)."""
    uid = _user_id(user)
    db = get_db()
    conditions = ["user_id=?"]
    params = [uid]
    if start_date:
        conditions.append("started_at>=?")
        params.append(str(start_date))
    if end_date:
        conditions.append("started_at<?")
        params.append(f"{end_date}T23:59:59")
    where = " WHERE " + " AND ".join(conditions)
    page = max(1, int(page))
    per_page = max(1, min(int(per_page), 50))
    total = db.execute(f"SELECT COUNT(*) n FROM workout_sessions{where}", params).fetchone()["n"]
    rows = db.execute(
        f"SELECT * FROM workout_sessions{where} ORDER BY started_at DESC LIMIT ? OFFSET ?",
        params + [per_page, (page - 1) * per_page],
    ).fetchall()
    return {
        "sessions": [dict(r) for r in rows],
        "page": page, "per_page": per_page, "total": total,
    }
