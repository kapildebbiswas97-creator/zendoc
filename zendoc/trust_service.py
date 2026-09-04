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


PROVIDER_ROLES = {"doctor", "hospital", "pharmacy"}
INTERACTION_ALIASES = {
    "appointment": "appointment",
    "doctor_appointment": "appointment",
    "pharmacy": "pharmacy_order",
    "order": "pharmacy_order",
    "pharmacy_order": "pharmacy_order",
    "diagnostic": "diagnostic",
    "diagnostic_booking": "diagnostic",
    "home_health": "home_health",
    "homecare": "home_health",
}


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


def _canonical_interaction_type(interaction_type: str) -> str:
    value = str(interaction_type or "").strip().lower()
    return INTERACTION_ALIASES.get(value, value)


def _table_columns(db, table: str) -> set[str]:
    """Read optional additive columns without assuming a schema migration."""
    try:
        return {row["name"] for row in db.execute(f"PRAGMA table_info({table})").fetchall()}
    except Exception:
        return set()


def _interaction_provider(
    user_id: int,
    interaction_type: str,
    interaction_id: str,
) -> dict[str, Any] | None:
    """Resolve the provider actually attached to a completed interaction.

    Returning the provider from the persisted interaction, instead of trusting
    a caller-supplied provider_id, prevents a user from reviewing an unrelated
    provider after completing an interaction with somebody else.
    """
    db = get_db()
    itype = _canonical_interaction_type(interaction_type)

    if itype == "appointment":
        row = db.execute(
            """
            SELECT id, provider_id AS provider_id
            FROM appointments
            WHERE id=? AND patient_id=? AND provider_id IS NOT NULL
              AND LOWER(status)='completed'
            """,
            (interaction_id, user_id),
        ).fetchone()
        return dict(row) if row else None

    if itype == "pharmacy_order":
        row = db.execute(
            """
            SELECT id, pharmacy_id AS provider_id
            FROM medicine_orders
            WHERE id=? AND pharmacy_id IS NOT NULL
              AND (patient_id=? OR ordered_by=?)
              AND (UPPER(COALESCE(tracking_status, ''))='DELIVERED'
                   OR UPPER(COALESCE(status, ''))='DELIVERED')
            """,
            (interaction_id, user_id, user_id),
        ).fetchone()
        return dict(row) if row else None

    if itype == "diagnostic":
        row = db.execute(
            """
            SELECT id, lab_id AS provider_id, patient_id
            FROM diagnostic_bookings
            WHERE id=? AND patient_id=? AND lab_id IS NOT NULL
              AND LOWER(status)='completed'
            """,
            (interaction_id, user_id),
        ).fetchone()
        if not row:
            return None
        # A status flag alone is not proof that a lab completed the test.  The
        # completion service writes a provider-authored, provenance-tagged
        # event when the assigned verified lab confirms completion.
        completion = db.execute(
            """
            SELECT id
            FROM health_timeline_events
            WHERE patient_id=? AND event_type='DIAGNOSTIC_COMPLETED'
              AND source='PROVIDER_RECORDED'
              AND source_ref=? AND created_by=?
            ORDER BY id DESC LIMIT 1
            """,
            (row["patient_id"], f"diagnostic:{interaction_id}", row["provider_id"]),
        ).fetchone()
        return dict(row) if completion else None

    if itype == "home_health":
        # The current request schema intentionally has no provider assignment.
        # If a future integration adds one, use it; otherwise this interaction
        # is not reviewable and no provider may be inferred from service text.
        columns = _table_columns(db, "home_health_requests")
        provider_column = next(
            (name for name in ("assigned_provider_id", "provider_id", "assigned_staff_id") if name in columns),
            None,
        )
        if not provider_column:
            return None
        row = db.execute(
            f"""
            SELECT id, {provider_column} AS provider_id
            FROM home_health_requests
            WHERE id=? AND patient_id=? AND {provider_column} IS NOT NULL
              AND LOWER(status)='completed'
            """,
            (interaction_id, user_id),
        ).fetchone()
        return dict(row) if row else None

    return None


def is_interaction_eligible_for_review(
    user_id: int,
    interaction_type: str,
    interaction_id: str,
    provider_id: int | None = None,
) -> bool:
    """
    Verify whether the user actually completed this interaction with the provider.
    Protects against fraudulent, unverified, or spam reviews.
    """
    interaction = _interaction_provider(user_id, interaction_type, interaction_id)
    if not interaction or not interaction.get("provider_id"):
        return False
    if provider_id is not None:
        try:
            return int(provider_id) == int(interaction["provider_id"])
        except (TypeError, ValueError):
            return False
    return True


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

    canonical_type = _canonical_interaction_type(interaction_type)
    try:
        provider_id = int(provider_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("provider_id must identify the provider from the completed interaction.") from exc
    interaction = _interaction_provider(aid, canonical_type, str(interaction_id))
    if not interaction or not interaction.get("provider_id"):
        raise PermissionError("Reviews are permitted only after a verified, completed interaction.")
    if int(interaction["provider_id"]) != provider_id:
        raise PermissionError("provider_id must match the provider recorded on the completed interaction.")

    db = get_db()
    existing = db.execute(
        """
        SELECT user_id, provider_id
        FROM verified_reviews
        WHERE interaction_type=? AND interaction_id=?
        """,
        (canonical_type, str(interaction_id)),
    ).fetchone()
    if existing and int(existing["user_id"]) != aid:
        raise PermissionError("This completed interaction already has a review from another user.")
    if existing and int(existing["provider_id"]) != provider_id:
        raise PermissionError("The existing review is bound to a different provider.")
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
        (aid, provider_id, canonical_type, str(interaction_id), rating, comment, now),
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
    try:
        provider_id = int(provider_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("provider_id must identify a provider account.") from exc
    db = get_db()
    user_row = db.execute(
        "SELECT id, name, role, active FROM users WHERE id=?", (provider_id,)
    ).fetchone()
    if not user_row:
        raise LookupError(f"Provider #{provider_id} not found.")
    if user_row["role"] not in PROVIDER_ROLES:
        raise LookupError(f"User #{provider_id} is not a healthcare provider.")
    if not user_row["active"]:
        raise LookupError(f"Provider #{provider_id} is inactive.")

    prof_row = db.execute("SELECT * FROM provider_profiles WHERE user_id=?", (provider_id,)).fetchone()
    prof = dict(prof_row) if prof_row else {}

    # Verified review metrics
    review_stats = db.execute(
        """
        SELECT COUNT(*) count, AVG(rating) avg_rating
        FROM verified_reviews
        WHERE provider_id=? AND is_verified=1
        """,
        (provider_id,),
    ).fetchone()

    # Completed interactions
    completed_appts = db.execute(
        "SELECT COUNT(*) c FROM appointments WHERE provider_id=? AND LOWER(status)='completed'",
        (provider_id,),
    ).fetchone()["c"]

    delivered_orders = db.execute(
        """
        SELECT COUNT(*) c FROM medicine_orders
        WHERE pharmacy_id=?
          AND (UPPER(COALESCE(tracking_status, ''))='DELIVERED'
               OR UPPER(COALESCE(status, ''))='DELIVERED')
        """,
        (provider_id,),
    ).fetchone()["c"]

    completed_diags = db.execute(
        """
        SELECT COUNT(*) c
        FROM diagnostic_bookings dbk
        WHERE dbk.lab_id=? AND LOWER(dbk.status)='completed'
          AND EXISTS (
              SELECT 1 FROM health_timeline_events hte
              WHERE hte.patient_id=dbk.patient_id
                AND hte.event_type='DIAGNOSTIC_COMPLETED'
                AND hte.source='PROVIDER_RECORDED'
                AND hte.source_ref=('diagnostic:' || dbk.id)
                AND hte.created_by=dbk.lab_id
          )
        """,
        (provider_id,),
    ).fetchone()["c"]

    home_health_completed = 0
    home_health_columns = _table_columns(db, "home_health_requests")
    provider_column = next(
        (name for name in ("assigned_provider_id", "provider_id", "assigned_staff_id") if name in home_health_columns),
        None,
    )
    if provider_column:
        home_health_completed = db.execute(
            f"SELECT COUNT(*) c FROM home_health_requests WHERE {provider_column}=? AND LOWER(status)='completed'",
            (provider_id,),
        ).fetchone()["c"]

    total_completed = completed_appts + delivered_orders + completed_diags + home_health_completed
    verification_status = str(prof.get("verification_status") or "UNVERIFIED").strip().upper()
    if verification_status not in {"PENDING", "VERIFIED", "REJECTED", "SUSPENDED", "UNVERIFIED"}:
        verification_status = "UNVERIFIED"
    profile_verified = verification_status == "VERIFIED"

    return {
        "provider_id": provider_id,
        "name": user_row["name"],
        "role": user_row["role"],
        "verification_status": verification_status,
        "digitalization_level": prof.get("digitalization_level") if prof else None,
        "total_completed_interactions": total_completed,
        "verified_reviews_count": review_stats["count"] if review_stats else 0,
        "total_reviews": review_stats["count"] if review_stats else 0,
        "average_verified_rating": round(float(review_stats["avg_rating"]), 1) if review_stats and review_stats["avg_rating"] else None,
        "average_rating": round(float(review_stats["avg_rating"]), 1) if review_stats and review_stats["avg_rating"] else None,
        "verified_rate": 1.0 if review_stats and review_stats["count"] else 0.0,
        # Operational signals are not inferred from the absence of a profile
        # (or from a pending/unverified profile).  A profile must explicitly
        # carry verified values before the public trust response exposes them.
        "operating_hours": prof.get("operating_hours") if profile_verified else None,
        "delivery_available": (
            bool(prof["delivery_available"])
            if profile_verified and prof.get("delivery_available") is not None
            else None
        ),
        "pickup_available": (
            bool(prof["pickup_available"])
            if profile_verified and prof.get("pickup_available") is not None
            else None
        ),
    }
