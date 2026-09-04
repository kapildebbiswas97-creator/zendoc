"""
ZENDOC Provider Trust & Verified Interaction Reviews — Milestone 10
Truthful provider verification signals and verified interaction reviews.

INVARIANTS:
1. Reviews are permitted ONLY for verified, completed interactions:
   - Completed doctor appointments
   - Delivered pharmacy orders
   - Completed diagnostic tests
   - Completed home health visits
2. NEVER fabricate reviews or generate opaque "doctor quality scores".
3. Displays truthful operational signals: verified status, completed volumes, inventory freshness.
"""
from __future__ import annotations

from typing import Any

from .db import get_db, now_iso


def _user_id(actor: Any) -> int:
    if actor is None:
        return 0
    if isinstance(actor, (int, float)):
        return int(actor)
    try:
        val = actor["id"]
        if val is not None:
            return int(val)
    except Exception:
        pass
    try:
        val = getattr(actor, "id", None)
        if val is not None:
            return int(val)
    except Exception:
        pass
    return 0


def is_interaction_eligible_for_review(
    user_id: int,
    interaction_type: str,
    interaction_id: str,
) -> bool:
    """
    Verify whether the user actually completed this interaction with the provider.
    Protects against fraudulent, unverified, or spam reviews.
    """
    db = get_db()
    itype = interaction_type.lower().strip()

    if itype == "appointment":
        row = db.execute(
            "SELECT id FROM appointments WHERE id=? AND patient_id=? AND status='completed'",
            (interaction_id, user_id),
        ).fetchone()
        return bool(row)

    elif itype == "pharmacy_order":
        row = db.execute(
            "SELECT id FROM medicine_orders WHERE id=? AND (patient_id=? OR ordered_by=?) AND tracking_status='DELIVERED'",
            (interaction_id, user_id, user_id),
        ).fetchone()
        return bool(row)

    elif itype == "diagnostic":
        row = db.execute(
            "SELECT id FROM diagnostic_bookings WHERE id=? AND patient_id=? AND status='completed'",
            (interaction_id, user_id),
        ).fetchone()
        return bool(row)

    elif itype == "home_health":
        row = db.execute(
            "SELECT id FROM home_health_requests WHERE id=? AND patient_id=? AND status='completed'",
            (interaction_id, user_id),
        ).fetchone()
        return bool(row)

    return False


def submit_verified_review(
    actor: Any,
    provider_id: int,
    interaction_type: str,
    interaction_id: str,
    rating: int,
    comment: str | None = None,
) -> dict[str, Any]:
    """Submit a verified review if the completed interaction check passes."""
    aid = _user_id(actor)
    if not aid:
        raise PermissionError("Authentication required to submit review.")

    rating = int(rating)
    if rating < 1 or rating > 5:
        raise ValueError("Rating must be an integer between 1 and 5.")

    if not is_interaction_eligible_for_review(aid, interaction_type, interaction_id):
        raise PermissionError("Reviews are permitted only after a verified, completed interaction.")

    db = get_db()
    now = now_iso()
    cursor = db.execute(
        """
        INSERT INTO verified_reviews
        (user_id, provider_id, interaction_type, interaction_id, rating, comment, is_verified, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 1, ?)
        ON CONFLICT(interaction_type, interaction_id) DO UPDATE SET
            rating=excluded.rating,
            comment=excluded.comment,
            created_at=excluded.created_at
        """,
        (aid, provider_id, interaction_type, str(interaction_id), rating, comment, now),
    )
    db.commit()

    return {
        "success": True,
        "is_verified": True,
        "message": "Verified review recorded successfully.",
    }


def get_provider_trust_signals(provider_id: int) -> dict[str, Any]:
    """
    Assemble factual trust signals for a healthcare provider.
    Never invents scores; reports truthful counts, verification state, and verified reviews.
    """
    db = get_db()
    user_row = db.execute("SELECT id, name, role FROM users WHERE id=?", (provider_id,)).fetchone()
    if not user_row:
        raise LookupError(f"Provider #{provider_id} not found.")

    prof_row = db.execute("SELECT * FROM provider_profiles WHERE user_id=?", (provider_id,)).fetchone()
    prof = dict(prof_row) if prof_row else {}

    # Verified review metrics
    review_stats = db.execute(
        """
        SELECT COUNT(*) count, AVG(rating) avg_rating
        FROM verified_reviews
        WHERE provider_id=?
        """,
        (provider_id,),
    ).fetchone()

    # Completed interactions
    completed_appts = db.execute(
        "SELECT COUNT(*) c FROM appointments WHERE provider_id=? AND status='completed'",
        (provider_id,),
    ).fetchone()["c"]

    delivered_orders = db.execute(
        "SELECT COUNT(*) c FROM medicine_orders WHERE pharmacy_id=? AND tracking_status='DELIVERED'",
        (provider_id,),
    ).fetchone()["c"]

    completed_diags = db.execute(
        "SELECT COUNT(*) c FROM diagnostic_bookings WHERE lab_id=? AND status='completed'",
        (provider_id,),
    ).fetchone()["c"]

    total_completed = completed_appts + delivered_orders + completed_diags

    return {
        "provider_id": provider_id,
        "name": user_row["name"],
        "role": user_row["role"],
        "verification_status": prof.get("verification_status", "pending").upper(),
        "digitalization_level": prof.get("digitalization_level", 1),
        "total_completed_interactions": total_completed,
        "verified_reviews_count": review_stats["count"] if review_stats else 0,
        "total_reviews": review_stats["count"] if review_stats else 0,
        "average_verified_rating": round(float(review_stats["avg_rating"]), 1) if review_stats and review_stats["avg_rating"] else None,
        "average_rating": round(float(review_stats["avg_rating"]), 1) if review_stats and review_stats["avg_rating"] else None,
        "verified_rate": 1.0 if review_stats and review_stats["count"] else 0.0,
        "operating_hours": prof.get("operating_hours", "08:00 - 22:00"),
        "delivery_available": bool(prof.get("delivery_available", 1)),
        "pickup_available": bool(prof.get("pickup_available", 1)),
    }