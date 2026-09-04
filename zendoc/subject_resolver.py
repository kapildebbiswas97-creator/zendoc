"""
Subject & Relationship Resolver for ZENDOC Healthcare Orchestration — Milestone 11

Determines whether a healthcare request is for the authenticated user ('self')
or on behalf of a family member ('mother', 'father', 'parent', 'child', etc.).
Verifies relationship links and active family access grants before permitting data access.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .db import get_db
from .family_care import _parse_scopes, has_family_access


RELATIONSHIP_PATTERNS = [
    (re.compile(r"\b(?:my\s+)?(?:mother|mom|mum|mummy|amma|maa)\b", re.IGNORECASE), "mother"),
    (re.compile(r"\b(?:my\s+)?(?:father|dad|daddy|appa|pitaji)\b", re.IGNORECASE), "father"),
    (re.compile(r"\b(?:my\s+)?(?:parents?)\b", re.IGNORECASE), "mother"),  # default parent to mother/father
    (re.compile(r"\b(?:my\s+)?(?:wife|husband|spouse|partner)\b", re.IGNORECASE), "spouse"),
    (re.compile(r"\b(?:my\s+)?(?:son|beta)\b", re.IGNORECASE), "son"),
    (re.compile(r"\b(?:my\s+)?(?:daughter|beti)\b", re.IGNORECASE), "daughter"),
    (re.compile(r"\b(?:my\s+)?(?:child|kid|baby)\b", re.IGNORECASE), "child"),
    (re.compile(r"\b(?:my\s+)?(?:grandfather|grandpa|dada|nana)\b", re.IGNORECASE), "grandfather"),
    (re.compile(r"\b(?:my\s+)?(?:grandmother|grandma|dadi|nani)\b", re.IGNORECASE), "grandmother"),
]


@dataclass
class SubjectResolution:
    is_self: bool
    patient_id: int | None
    relationship: str
    subject_name: str | None
    authorized: bool
    requires_consent: bool
    message: str
    family_member_id: int | None = None
    grantor_user_id: int | None = None
    missing_scope: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_self": self.is_self,
            "patient_id": self.patient_id,
            "relationship": self.relationship,
            "subject_name": self.subject_name,
            "authorized": self.authorized,
            "requires_consent": self.requires_consent,
            "message": self.message,
            "family_member_id": self.family_member_id,
            "grantor_user_id": self.grantor_user_id,
            "missing_scope": self.missing_scope,
        }


def _user_id(actor: Any) -> int:
    if actor is None:
        return 0
    uid = actor["id"] if hasattr(actor, "__getitem__") else getattr(actor, "id", None)
    return int(uid or 0)


def resolve_request_subject(actor: Any, text: str, requested_scope: str = "pharmacy") -> SubjectResolution:
    """
    Resolve the intended subject of a healthcare request from text and context.
    
    If the request is for a family member, checks whether an active, unrevoked
    family_access_grant exists with the required scope.
    """
    actor_id = _user_id(actor)
    if not actor_id:
        return SubjectResolution(
            is_self=True,
            patient_id=None,
            relationship="self",
            subject_name=None,
            authorized=False,
            requires_consent=False,
            message="Authentication required to resolve patient context.",
        )

    text_clean = str(text or "").strip()
    detected_rel = None

    for pattern, rel in RELATIONSHIP_PATTERNS:
        if pattern.search(text_clean):
            detected_rel = rel
            break

    # If no family relationship is detected, this is a self request
    if not detected_rel:
        return SubjectResolution(
            is_self=True,
            patient_id=actor_id,
            relationship="self",
            subject_name=actor.get("name") if isinstance(actor, dict) else getattr(actor, "name", "Self"),
            authorized=True,
            requires_consent=False,
            message="Request resolved for authenticated user.",
        )

    # Family member detected: look up family relationships for this user
    db = get_db()
    family_rows = db.execute(
        """
        SELECT * FROM family_members
        WHERE user_id=? AND LOWER(relationship)=LOWER(?)
        ORDER BY id DESC
        """,
        (actor_id, detected_rel),
    ).fetchall()

    member_row = family_rows[0] if family_rows else None
    family_member_id = int(member_row["id"]) if member_row else None
    subject_name = member_row["member_name"] if member_row else detected_rel.capitalize()

    # Look up active grants where this user is the grantee (caregiver)
    # 1. Matching family_member_id directly
    grant_row = None
    if family_member_id:
        grant_row = db.execute(
            """
            SELECT * FROM family_access_grants
            WHERE grantee_id=? AND family_member_id=? AND revoked_at IS NULL
            ORDER BY created_at DESC
            """,
            (actor_id, family_member_id),
        ).fetchone()

    # 2. Or any active grant from another user whose name/relationship corresponds
    if not grant_row:
        active_grants = db.execute(
            """
            SELECT g.*, u.name as grantor_name, u.email as grantor_email
            FROM family_access_grants g
            JOIN users u ON u.id=g.grantor_id
            WHERE g.grantee_id=? AND g.revoked_at IS NULL
            ORDER BY g.created_at DESC
            """,
            (actor_id,),
        ).fetchall()

        for g_row in active_grants:
            if family_member_id and g_row["family_member_id"] == family_member_id:
                grant_row = g_row
                break
            if member_row and str(member_row["member_name"]).lower() in str(g_row["grantor_name"]).lower():
                grant_row = g_row
                break
        
        if not grant_row and active_grants:
            if len(active_grants) == 1:
                grant_row = active_grants[0]

    if not grant_row:
        return SubjectResolution(
            is_self=False,
            patient_id=None,
            relationship=detected_rel,
            subject_name=subject_name,
            authorized=False,
            requires_consent=True,
            family_member_id=family_member_id,
            message=(
                f"You requested care for your {detected_rel} ({subject_name}), "
                f"but an active family consent grant is required to access their health records. "
                f"Please ask your {detected_rel} to authorize family care access under Settings > Family Care."
            ),
        )

    # Grant exists: verify required scope
    scopes = _parse_scopes(grant_row["scopes"])
    grantor_id = int(grant_row["grantor_id"])

    # Scope mapping: pharmacy, appointments, reports, diagnostics, care_tasks
    if requested_scope and requested_scope not in scopes and "care_tasks" not in scopes:
        return SubjectResolution(
            is_self=False,
            patient_id=grantor_id,
            relationship=detected_rel,
            subject_name=subject_name,
            authorized=False,
            requires_consent=True,
            family_member_id=family_member_id,
            grantor_user_id=grantor_id,
            missing_scope=requested_scope,
            message=(
                f"Your active family consent for your {detected_rel} does not include the '{requested_scope}' scope. "
                f"Existing permissions: {', '.join(scopes)}."
            ),
        )

    return SubjectResolution(
        is_self=False,
        patient_id=grantor_id,
        relationship=detected_rel,
        subject_name=subject_name,
        authorized=True,
        requires_consent=False,
        family_member_id=family_member_id,
        grantor_user_id=grantor_id,
        message=f"Authorized family care access verified for {subject_name} ({detected_rel}).",
    )
