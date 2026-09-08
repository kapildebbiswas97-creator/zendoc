"""Claim workflow for imported public healthcare directory listings.

A claim associates a real ZENDOC provider profile with an imported public
directory entry. It does NOT itself verify the provider, connect booking,
prove live availability, or alter the source's public-directory truth state.
"""
from __future__ import annotations

from typing import Any

from .db import get_db, is_integrity_error, now_iso
from .provider_service import PROVIDER_ROLES, get_provider_profile_for_user
from .security import assert_owner


CLAIM_STATUSES = {"pending", "approved", "rejected", "revoked"}
CLAIMABLE_CATEGORIES_BY_ROLE = {
    "doctor": {"doctor", "clinic"},
    "hospital": {
        "hospital", "clinic", "health_centre", "nursing_home",
        "diagnostic_centre", "laboratory", "blood_bank",
    },
    "pharmacy": {"pharmacy"},
}


def submit_public_entity_claim(
    actor: Any,
    *,
    public_entity_id: int,
    claimant_note: str | None = None,
) -> dict:
    role = str(actor.get("role") if isinstance(actor, dict) else actor["role"])
    if role not in PROVIDER_ROLES:
        raise PermissionError("Only doctor, hospital, or pharmacy accounts may claim a public healthcare listing.")

    profile = get_provider_profile_for_user(int(actor["id"]))
    if not profile:
        raise LookupError("Create a provider profile before claiming a public healthcare listing.")

    db = get_db()
    entity = db.execute(
        "SELECT * FROM public_healthcare_entities WHERE id=? AND active=1",
        (int(public_entity_id),),
    ).fetchone()
    if not entity:
        raise LookupError(f"Active public healthcare entity #{public_entity_id} not found.")

    allowed_categories = CLAIMABLE_CATEGORIES_BY_ROLE.get(role, set())
    if str(entity["category"]) not in allowed_categories:
        raise PermissionError(
            f"A {role} account cannot claim a public {entity['category']} listing."
        )

    existing_approved = db.execute(
        """
        SELECT c.id,c.provider_profile_id
        FROM public_entity_claims c
        WHERE c.public_entity_id=? AND c.status='approved'
        LIMIT 1
        """,
        (int(public_entity_id),),
    ).fetchone()
    if existing_approved and int(existing_approved["provider_profile_id"]) != int(profile["id"]):
        raise PermissionError("This public listing is already linked to another approved provider profile.")

    existing = db.execute(
        """
        SELECT * FROM public_entity_claims
        WHERE public_entity_id=? AND provider_profile_id=?
        LIMIT 1
        """,
        (int(public_entity_id), int(profile["id"])),
    ).fetchone()
    now = now_iso()
    note = str(claimant_note or "").strip()[:1000] or None

    if existing:
        if existing["status"] in {"pending", "approved"}:
            return dict(existing)
        db.execute(
            """
            UPDATE public_entity_claims
            SET status='pending', claimant_note=?, review_note=NULL, reviewed_by=NULL,
                reviewed_at=NULL, updated_at=?
            WHERE id=?
            """,
            (note, now, int(existing["id"])),
        )
        claim_id = int(existing["id"])
    else:
        try:
            cursor = db.execute(
                """
                INSERT INTO public_entity_claims
                (public_entity_id,provider_profile_id,claimed_by,status,claimant_note,created_at,updated_at)
                VALUES (?,?,?,'pending',?,?,?)
                """,
                (
                    int(public_entity_id),
                    int(profile["id"]),
                    int(actor["id"]),
                    note,
                    now,
                    now,
                ),
            )
            claim_id = int(cursor.lastrowid)
        except Exception as exc:
            if not is_integrity_error(exc):
                raise
            db.rollback()
            row = db.execute(
                """
                SELECT * FROM public_entity_claims
                WHERE public_entity_id=? AND provider_profile_id=?
                LIMIT 1
                """,
                (int(public_entity_id), int(profile["id"])),
            ).fetchone()
            if not row:
                raise
            return dict(row)

    db.commit()
    return get_public_entity_claim(claim_id)


def review_public_entity_claim(
    actor: Any,
    claim_id: int,
    *,
    status: str,
    review_note: str | None = None,
) -> dict:
    assert_owner(actor)
    status = str(status or "").strip().lower()
    if status not in {"approved", "rejected", "revoked"}:
        raise ValueError("Claim review status must be approved, rejected, or revoked.")

    db = get_db()
    claim = get_public_entity_claim(claim_id)
    now = now_iso()

    if status == "approved":
        conflict = db.execute(
            """
            SELECT id,provider_profile_id
            FROM public_entity_claims
            WHERE public_entity_id=? AND status='approved' AND id<>?
            LIMIT 1
            """,
            (int(claim["public_entity_id"]), int(claim_id)),
        ).fetchone()
        if conflict:
            raise ValueError("Another provider profile already has an approved claim for this public listing.")

    db.execute(
        """
        UPDATE public_entity_claims
        SET status=?,review_note=?,reviewed_by=?,reviewed_at=?,updated_at=?
        WHERE id=?
        """,
        (
            status,
            str(review_note or "").strip()[:1000] or None,
            int(actor["id"]),
            now,
            now,
            int(claim_id),
        ),
    )
    db.commit()
    return get_public_entity_claim(claim_id)


def get_public_entity_claim(claim_id: int) -> dict:
    row = get_db().execute(
        """
        SELECT c.*,
               e.name AS public_entity_name,
               e.category AS public_entity_category,
               e.source_id AS public_entity_source_id,
               e.source_record_id AS public_entity_source_record_id,
               p.user_id AS provider_user_id,
               p.provider_type,
               p.organization,
               p.verification_status AS provider_verification_status
        FROM public_entity_claims c
        JOIN public_healthcare_entities e ON e.id=c.public_entity_id
        JOIN provider_profiles p ON p.id=c.provider_profile_id
        WHERE c.id=?
        """,
        (int(claim_id),),
    ).fetchone()
    if not row:
        raise LookupError(f"Public entity claim #{claim_id} not found.")
    result = dict(row)
    result["truth_notice"] = (
        "An approved claim links a ZENDOC provider profile to a public directory listing. "
        "It does not by itself verify the provider, prove live availability, or enable booking."
    )
    return result


def list_public_entity_claims(
    actor: Any,
    *,
    status: str | None = None,
    limit: int = 100,
) -> list[dict]:
    assert_owner(actor)
    limit = max(1, min(int(limit or 100), 500))
    params: list[Any] = []
    clause = ""
    if status:
        clean = str(status).strip().lower()
        if clean not in CLAIM_STATUSES:
            raise ValueError("Unsupported claim status.")
        clause = "WHERE c.status=?"
        params.append(clean)
    params.append(limit)

    rows = get_db().execute(
        f"""
        SELECT c.id
        FROM public_entity_claims c
        {clause}
        ORDER BY CASE c.status WHEN 'pending' THEN 0 WHEN 'approved' THEN 1 ELSE 2 END,
                 c.created_at DESC
        LIMIT ?
        """,
        params,
    ).fetchall()
    return [get_public_entity_claim(int(row["id"])) for row in rows]


def list_my_public_entity_claims(actor: Any, limit: int = 50) -> list[dict]:
    profile = get_provider_profile_for_user(int(actor["id"]))
    if not profile:
        return []
    rows = get_db().execute(
        """
        SELECT id FROM public_entity_claims
        WHERE provider_profile_id=?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (int(profile["id"]), max(1, min(int(limit or 50), 200))),
    ).fetchall()
    return [get_public_entity_claim(int(row["id"])) for row in rows]
