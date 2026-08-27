"""
Fitness Analytics — progress metrics computed from real user data only.

Never fabricates data.  Returns zero/empty state truthfully.
Weight trend is delegated to existing health_analytics to avoid duplication.
"""

from datetime import datetime, timedelta, timezone

from .db import get_db


def _user_id(user):
    return int(user["id"] if hasattr(user, "__getitem__") else getattr(user, "id", 0))


def _parse_period(period):
    days = {"7d": 7, "30d": 30, "90d": 90}.get(str(period or "30d"), 30)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    return days, cutoff


def get_fitness_progress(user, period="30d"):
    """
    Return workout progress metrics for the requested period.
    All values are computed from real session data only.
    """
    uid = _user_id(user)
    days, cutoff = _parse_period(period)
    db = get_db()

    sessions = db.execute(
        """SELECT id, started_at, finished_at, duration_minutes, status, name
           FROM workout_sessions
           WHERE user_id=? AND status='completed' AND started_at>=?
           ORDER BY started_at ASC""",
        (uid, cutoff),
    ).fetchall()

    if not sessions:
        return {
            "period": period,
            "workouts_completed": 0,
            "total_duration_minutes": 0,
            "average_duration_minutes": 0,
            "weekly_activity": [],
            "current_streak_days": 0,
            "longest_streak_days": 0,
            "last_workout_at": None,
        }

    total_duration = sum(s["duration_minutes"] or 0 for s in sessions)
    count = len(sessions)
    avg_duration = round(total_duration / count) if count else 0

    # Weekly buckets (ISO week)
    weekly = {}
    for s in sessions:
        try:
            dt = datetime.fromisoformat(str(s["started_at"]).replace("Z", "+00:00"))
            week_key = dt.strftime("%Y-W%W")
            weekly[week_key] = weekly.get(week_key, 0) + 1
        except Exception:
            pass
    weekly_activity = [{"week": k, "count": v} for k, v in sorted(weekly.items())]

    # Streak calculation (consecutive days with ≥1 completed workout)
    workout_days = set()
    for s in sessions:
        try:
            dt = datetime.fromisoformat(str(s["started_at"]).replace("Z", "+00:00"))
            workout_days.add(dt.date())
        except Exception:
            pass

    current_streak = 0
    longest_streak = 0
    today = datetime.now(timezone.utc).date()
    check = today
    while check in workout_days:
        current_streak += 1
        check -= timedelta(days=1)
    # Longest streak
    if workout_days:
        sorted_days = sorted(workout_days)
        streak = 1
        max_streak = 1
        for i in range(1, len(sorted_days)):
            if (sorted_days[i] - sorted_days[i - 1]).days == 1:
                streak += 1
                max_streak = max(max_streak, streak)
            else:
                streak = 1
        longest_streak = max_streak

    last_workout = sessions[-1]["started_at"] if sessions else None

    return {
        "period": period,
        "workouts_completed": count,
        "total_duration_minutes": total_duration,
        "average_duration_minutes": avg_duration,
        "weekly_activity": weekly_activity,
        "current_streak_days": current_streak,
        "longest_streak_days": longest_streak,
        "last_workout_at": last_workout,
    }


def get_weight_trend_for_fitness(user, period="30d"):
    """
    Delegate weight trend to existing health_analytics module.
    No duplication — reuses the authoritative measurement service.
    """
    from .health_analytics import get_health_trend
    return get_health_trend(user, "weight", period=period)
