"""
ZENDOC Healthcare Context Engine — Milestone 10
Enforces privacy-aware, task-scoped, minimum necessary health context.

Core Invariant:
AI/tool/service access receives strictly what is required for the authorized action.
Never leaks complete lifetime memory, mental health discussions, or unrelated records.

Flow:
CONTEXT REQUEST → AUTHORIZATION → CONSENT VALIDATION → MINIMUM NECESSARY BUNDLE → CALLER
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from .db import get_db, now_iso


# M10 uses two compatible consent stores: the original family-care grant
# (coarse service scopes) and the connected-care grant (purpose + resource
# scopes).  Keep the mapping explicit so that a grant for one job can never be
# reused as blanket access to another job.
CONTEXT_PURPOSE_ALIASES: dict[str, set[str]] = {
    "pharmacy": {"pharmacy"},
    "prescriptions": {"prescriptions", "prescription_view", "pharmacy"},
    "pharmacy_fulfilment": {"pharmacy_fulfilment", "pharmacy", "find_prescribed_medicines"},
    "find_prescribed_medicines": {"find_prescribed_medicines", "pharmacy", "pharmacy_fulfilment"},
    "prescription_view": {"prescription_view", "prescriptions", "pharmacy", "pharmacy_fulfilment"},
    "prescription_item_confirm": {"prescription_item_confirm", "prescriptions", "pharmacy", "pharmacy_fulfilment"},
    "diagnostic_booking": {"diagnostic_booking", "diagnostics", "find_lab_tests"},
    "diagnostics": {"diagnostics", "diagnostic_booking", "find_lab_tests"},
    "find_lab_tests": {"find_lab_tests", "diagnostic_booking", "diagnostics"},
    "health_memory_view": {"health_memory_view", "timeline", "health_memory"},
    "care_graph_view": {"care_graph_view", "timeline", "health_memory"},
    "care_graph": {"care_graph", "care_graph_view", "timeline", "health_memory"},
    "care_continuity": {"care_continuity", "timeline", "health_memory"},
    "next_safe_action": {"next_safe_action", "timeline", "health_memory"},
}

# Fine-grained connected-care scopes.  These are data capabilities, not roles.
CONNECTED_CARE_SCOPES = {
    "prescriptions",
    "delivery_address",
    "saved_locations",
    "allergies",
    "diagnostics",
    "timeline",
    "reports",
}

PURPOSE_REQUIRED_SCOPES: dict[str, set[str]] = {
    "pharmacy": {"prescriptions"},
    "prescriptions": {"prescriptions"},
    "pharmacy_fulfilment": {"prescriptions", "delivery_address"},
    "find_prescribed_medicines": {"prescriptions"},
    "prescription_view": {"prescriptions"},
    "prescription_item_confirm": {"prescriptions"},
    "diagnostic_booking": {"diagnostics", "delivery_address"},
    "diagnostics": {"diagnostics"},
    "find_lab_tests": {"diagnostics"},
    "health_memory_view": {"timeline"},
    "care_graph_view": {"timeline"},
    "care_graph": {"timeline"},
    "care_continuity": {"timeline"},
    "next_safe_action": {"timeline"},
}

FAMILY_SCOPE_BY_PURPOSE = {
    "pharmacy": "pharmacy",
    "prescriptions": "pharmacy",
    "pharmacy_fulfilment": "pharmacy",
    "find_prescribed_medicines": "pharmacy",
    "prescription_view": "pharmacy",
    "prescription_item_confirm": "pharmacy",
    "diagnostic_booking": "diagnostics",
    "diagnostics": "diagnostics",
    "find_lab_tests": "diagnostics",
    "health_memory_view": "timeline",
    "care_graph_view": "timeline",
    "care_graph": "timeline",
    "care_continuity": "timeline",
    "next_safe_action": "timeline",
}


@dataclass
class ProvenanceRecord:
    source: str  # USER_REPORTED | DOCUMENT_EXTRACTED | PROVIDER_RECORDED | DEVICE_RECORDED
    verification_status: str  # UNVERIFIED | USER_CONFIRMED | PROVIDER_VERIFIED
    confidence: float = 1.0
    recorded_at: str = ""
    source_ref: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ContextBundle:
    actor_id: int
    patient_id: int
    purpose: str
    action: str
    consent_status: str  # ACTIVE | NOT_REQUIRED_SELF | REVOKED | EXPIRED | DENIED
    included_fields: list[str] = field(default_factory=list)
    excluded_fields: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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


def create_or_update_consent_grant(
    subject_id: int,
    grantee_id: int,
    purpose: str,
    scopes: list[str],
    expires_at: str | None = None,
    actor: Any = None,
) -> dict[str, Any]:
    """Create or update a granular, task-scoped consent grant."""
    if actor is not None and _user_id(actor) != int(subject_id):
        from .security import is_owner
        if not is_owner(actor):
            raise PermissionError("Only the patient can grant connected-care consent.")
    if not int(subject_id) or not int(grantee_id) or int(subject_id) == int(grantee_id):
        raise ValueError("A consent grant must identify a different active grantee.")
    purpose = str(purpose or "").strip().lower()
    if purpose not in CONTEXT_PURPOSE_ALIASES:
        raise ValueError(f"Unsupported connected-care consent purpose: {purpose or 'missing'}.")
    normalized_scopes = sorted({str(s).strip().lower() for s in (scopes or []) if str(s).strip()})
    invalid_scopes = sorted(set(normalized_scopes) - CONNECTED_CARE_SCOPES)
    if invalid_scopes:
        raise ValueError(f"Unsupported connected-care consent scope: {', '.join(invalid_scopes)}")
    if not normalized_scopes:
        raise ValueError("At least one connected-care consent scope is required.")
    db = get_db()
    subject = db.execute("SELECT id, active FROM users WHERE id=?", (int(subject_id),)).fetchone()
    if not subject or not bool(subject["active"]):
        raise LookupError("Consent subject is not an active account.")
    grantee = db.execute("SELECT id, active FROM users WHERE id=?", (int(grantee_id),)).fetchone()
    if not grantee or not bool(grantee["active"]):
        raise LookupError("Consent grantee is not an active account.")
    required = PURPOSE_REQUIRED_SCOPES.get(purpose, set())
    if required and not required.issubset(set(normalized_scopes)):
        raise ValueError(
            f"Consent purpose '{purpose}' requires scopes: {', '.join(sorted(required))}."
        )
    now = now_iso()
    scopes_json = json.dumps(normalized_scopes)

    existing = db.execute(
        """
        SELECT id FROM consent_grants
        WHERE subject_id=? AND grantee_id=? AND purpose=? AND status='active' AND revoked_at IS NULL
        """,
        (subject_id, grantee_id, purpose),
    ).fetchone()

    if existing:
        db.execute(
            """
            UPDATE consent_grants
            SET scopes_json=?, expires_at=?, updated_at=?
            WHERE id=?
            """,
            (scopes_json, expires_at, now, existing["id"]),
        )
        db.commit()
        grant_id = existing["id"]
    else:
        cursor = db.execute(
            """
            INSERT INTO consent_grants
            (subject_id, grantee_id, purpose, scopes_json, status, expires_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'active', ?, ?, ?)
            """,
            (subject_id, grantee_id, purpose, scopes_json, expires_at, now, now),
        )
        db.commit()
        grant_id = cursor.lastrowid

    row = db.execute("SELECT * FROM consent_grants WHERE id=?", (grant_id,)).fetchone()
    res = dict(row)
    res["scopes"] = json.loads(res["scopes_json"])
    return res


def revoke_consent_grant(grant_id: int, actor_id: int) -> bool:
    """Revoke a consent grant. The grantor (subject) or admin can revoke."""
    db = get_db()
    row = db.execute("SELECT * FROM consent_grants WHERE id=?", (grant_id,)).fetchone()
    if not row:
        return False
    # Subject or admin can revoke
    from .security import is_owner
    actor_row = db.execute("SELECT * FROM users WHERE id=?", (actor_id,)).fetchone()
    if int(row["subject_id"]) != actor_id and not is_owner(actor_row):
        raise PermissionError("Only the patient or system owner can revoke consent.")

    now = now_iso()
    db.execute(
        "UPDATE consent_grants SET status='revoked', revoked_at=?, updated_at=? WHERE id=?",
        (now, now, grant_id),
    )
    db.commit()
    return True


def get_active_consent_grant(subject_id: int, grantee_id: int, purpose: str) -> dict[str, Any] | None:
    """Return the active consent grant if valid, or None."""
    db = get_db()
    now = now_iso()
    row = db.execute(
        """
        SELECT * FROM consent_grants
        WHERE subject_id=? AND grantee_id=? AND purpose=? AND status='active' AND revoked_at IS NULL
          AND (expires_at IS NULL OR expires_at > ?)
        ORDER BY id DESC LIMIT 1
        """,
        (subject_id, grantee_id, purpose, now),
    ).fetchone()
    if not row:
        return None
    res = dict(row)
    res["scopes"] = json.loads(res.get("scopes_json") or "[]")
    return res


def verify_context_authorization(actor: Any, patient_id: int, purpose: str) -> str:
    """
    Verify whether actor may access patient data for the given purpose.
    Returns: 'SELF' | 'DELEGATED_CONSENT' | 'OWNER_OVERRIDE'
    Raises: PermissionError if unauthorized or consent is revoked/missing.
    """
    aid = _user_id(actor)
    if not aid:
        raise PermissionError("Authentication required for context resolution.")

    if aid == int(patient_id):
        return "SELF"

    from .security import is_owner
    if is_owner(actor):
        return "OWNER_OVERRIDE"

    purpose = str(purpose or "").strip().lower()
    purpose_aliases = CONTEXT_PURPOSE_ALIASES.get(purpose, {purpose})
    required_scopes = PURPOSE_REQUIRED_SCOPES.get(purpose, set())

    # Check connected-care delegation first.  A grant for an adjacent purpose
    # is accepted only when its explicit data scopes cover this request.
    missing_scope_grant = False
    for candidate_purpose in [purpose] + sorted(purpose_aliases - {purpose}):
        active_consent = get_active_consent_grant(int(patient_id), aid, candidate_purpose)
        if active_consent:
            granted_scopes = set(active_consent.get("scopes") or [])
            if required_scopes and not required_scopes.issubset(granted_scopes):
                missing_scope_grant = True
                continue
            return "DELEGATED_CONSENT"

    # Check Family Care delegation / access grant.  The old implementation
    # treated any active family relationship as blanket access; scope it to the
    # requested service instead.
    from .family_care import get_family_grant
    fam_grant = get_family_grant(patient_id, aid)
    family_scope = FAMILY_SCOPE_BY_PURPOSE.get(purpose)
    family_scopes: set[str] = set()
    if fam_grant:
        try:
            family_scopes = {str(s).strip().lower() for s in json.loads(fam_grant.get("scopes") or "[]")}
        except (TypeError, json.JSONDecodeError):
            family_scopes = set()

    if not fam_grant or (family_scope and family_scope not in family_scopes):
        if missing_scope_grant:
            raise PermissionError(
                f"Access denied: consent does not include the required context scopes for '{purpose}'."
            )
        raise PermissionError(f"Access denied: No active consent or care grant for patient #{patient_id}.")

    return "DELEGATED_CONSENT"


def _delegated_scopes(actor: Any, patient_id: int, purpose: str) -> set[str] | None:
    """Return explicit connected-care scopes for delegated access, if any."""
    aid = _user_id(actor)
    if aid == int(patient_id):
        return None  # self access is not narrowed by a caregiver grant
    aliases = CONTEXT_PURPOSE_ALIASES.get(str(purpose or "").strip().lower(), {str(purpose or "").strip().lower()})
    scopes: set[str] = set()
    for candidate in aliases:
        grant = get_active_consent_grant(int(patient_id), aid, candidate)
        if grant:
            scopes.update(grant.get("scopes") or [])
    if scopes:
        return scopes
    from .family_care import get_family_grant
    family_grant = get_family_grant(int(patient_id), aid)
    if family_grant:
        try:
            family_scopes = {str(s).strip().lower() for s in json.loads(family_grant.get("scopes") or "[]")}
            # Family Care uses service scopes; connected-care bundles use
            # resource scopes.  Expand only the corresponding, minimum set.
            expanded = set(family_scopes)
            if "pharmacy" in family_scopes:
                expanded.update({"prescriptions", "delivery_address"})
            if "diagnostics" in family_scopes:
                expanded.update({"diagnostics", "delivery_address"})
            if "timeline" in family_scopes:
                expanded.update({"timeline", "reports"})
            if "home_health" in family_scopes:
                expanded.add("delivery_address")
            return expanded & CONNECTED_CARE_SCOPES
        except (TypeError, json.JSONDecodeError):
            return set()
    return set()


def build_minimum_context_bundle(
    actor: Any,
    patient_id: int,
    purpose: str,
    action: str,
    requested_fields: list[str] | None = None,
) -> ContextBundle:
    """
    Build a privacy-minimized context bundle tailored exclusively for the requested task.
    Includes explicit inclusions and exclusions, with provenance attached to all facts.
    """
    auth_type = verify_context_authorization(actor, patient_id, purpose)
    aid = _user_id(actor)
    db = get_db()
    now = now_iso()

    # Base patient profile
    patient_row = db.execute(
        "SELECT id, name, city, emergency_contact, phone, age, gender FROM users WHERE id=?",
        (patient_id,),
    ).fetchone()
    if not patient_row:
        raise LookupError(f"Patient #{patient_id} not found.")

    patient_dict = dict(patient_row)

    loc_rows = db.execute(
        "SELECT id, label, address, city, state, latitude, longitude, is_default FROM saved_locations WHERE user_id=? ORDER BY is_default DESC",
        (patient_id,),
    ).fetchall()
    saved_locations = [dict(r) for r in loc_rows]
    default_address = saved_locations[0]["address"] if saved_locations else None

    # Allergies from patient health profile
    prof_row = db.execute("SELECT allergies FROM patient_health_profiles WHERE patient_id=?", (patient_id,)).fetchone()
    allergies = []
    if prof_row and prof_row["allergies"]:
        try:
            allergies = json.loads(prof_row["allergies"])
        except Exception:
            allergies = []

    included_fields: list[str] = []
    excluded_fields: list[str] = []
    data: dict[str, Any] = {}
    provenance: dict[str, Any] = {}

    purpose = str(purpose or "").strip().lower()
    delegated_scopes = _delegated_scopes(actor, patient_id, purpose)

    if purpose in {"pharmacy", "pharmacy_fulfilment", "find_prescribed_medicines"}:
        # Minimum necessary context for pharmacy fulfilment
        included_fields = [
            "patient_name",
            "patient_city",
            "delivery_address",
            "allergies",
            "prescriptions",
            "saved_locations",
        ]
        excluded_fields = [
            "mental_wellness_conversations",
            "unrelated_medical_records",
            "biometric_vitals_history",
            "fitness_workout_logs",
            "consultation_messages",
            "doctor_confidential_notes",
        ]

        # Fetch active authorized prescription
        presc_rows = db.execute(
            """
            SELECT p.*, r.original_filename
            FROM prescriptions p
            LEFT JOIN medical_records r ON r.id=p.record_id
            WHERE p.patient_id=? AND p.status='active'
            ORDER BY p.issue_date DESC, p.id DESC LIMIT 1
            """,
            (patient_id,),
        ).fetchall()

        prescriptions_data = []
        for pr in presc_rows:
            p_item = dict(pr)
            items = db.execute(
                "SELECT * FROM prescription_items WHERE prescription_id=? ORDER BY id ASC",
                (p_item["id"],),
            ).fetchall()
            p_item["items"] = [dict(i) for i in items]
            prescriptions_data.append(p_item)

        data = {
            "patient_id": patient_id,
            "patient_name": patient_dict["name"],
            "city": patient_dict["city"],
            "delivery_address": default_address,
            "saved_locations": saved_locations,
            "allergies": allergies,
            "prescriptions": prescriptions_data,
        }

        verified_prescriber = False
        if prescriptions_data:
            # A prescriber_id is only an identifier.  Do not promote it to a
            # verified provider claim unless the referenced active doctor has
            # a verified provider profile.
            verified_prescriber = bool(db.execute(
                """
                SELECT 1
                FROM prescriptions p
                JOIN users u ON u.id=p.prescriber_id AND u.active=1 AND u.role='doctor'
                JOIN provider_profiles pp ON pp.user_id=u.id AND LOWER(pp.verification_status)='verified'
                WHERE p.id=?
                """,
                (prescriptions_data[0]["id"],),
            ).fetchone())

        provenance = {
            "prescriptions": ProvenanceRecord(
                source="DOCUMENT_EXTRACTED",
                verification_status="PROVIDER_VERIFIED" if verified_prescriber else "UNVERIFIED",
                recorded_at=now,
                source_ref=f"prescription:{prescriptions_data[0]['id']}" if prescriptions_data else "",
            ).to_dict(),
            "allergies": ProvenanceRecord(
                source="USER_REPORTED",
                verification_status="USER_CONFIRMED",
                recorded_at=now,
            ).to_dict(),
            "delivery_address": ProvenanceRecord(
                source="USER_REPORTED",
                verification_status="USER_CONFIRMED",
                recorded_at=now,
            ).to_dict(),
        }

    elif purpose in {"diagnostic_booking", "find_lab_tests"}:
        included_fields = ["patient_name", "age", "gender", "collection_address", "city"]
        excluded_fields = [
            "mental_wellness_conversations",
            "lifestyle_notes",
            "unrelated_prescriptions",
            "fitness_workout_logs",
        ]
        data = {
            "patient_id": patient_id,
            "patient_name": patient_dict["name"],
            "age": patient_dict["age"],
            "gender": patient_dict["gender"],
            "collection_address": default_address,
            "city": patient_dict["city"],
        }
        provenance = {
            "demographics": ProvenanceRecord(
                source="USER_REPORTED",
                verification_status="USER_CONFIRMED",
                recorded_at=now,
            ).to_dict(),
        }

    else:
        # General safe minimized context
        included_fields = ["patient_name", "city", "allergies"]
        excluded_fields = ["complete_lifetime_memory", "raw_messages", "unrelated_reports"]
        data = {
            "patient_id": patient_id,
            "patient_name": patient_dict["name"],
            "city": patient_dict["city"],
            "allergies": allergies,
        }
        provenance = {
            "base_profile": ProvenanceRecord(
                source="USER_REPORTED",
                verification_status="USER_CONFIRMED",
                recorded_at=now,
            ).to_dict(),
        }

    # Apply caller-requested minimization and delegated scope minimization at
    # the final boundary.  Never return a field merely because it was present
    # in the patient's profile.
    if requested_fields is not None:
        requested = {str(f).strip() for f in requested_fields}
        included_fields = [f for f in included_fields if f in requested]
        data = {k: v for k, v in data.items() if k in set(included_fields) or k == "patient_id"}
        provenance = {k: v for k, v in provenance.items() if k in set(included_fields) or k in {"base_profile", "demographics"}}

    if delegated_scopes is not None:
        field_scopes = {
            "prescriptions": "prescriptions",
            "delivery_address": "delivery_address",
            "saved_locations": "saved_locations",
            "allergies": "allergies",
            "collection_address": "delivery_address",
            "age": "diagnostics",
            "gender": "diagnostics",
        }
        allowed_fields = {field for field, scope in field_scopes.items() if scope in delegated_scopes}
        included_fields = [f for f in included_fields if f in allowed_fields or f in {"patient_name", "patient_city", "city"}]
        data = {k: v for k, v in data.items() if k in set(included_fields) or k == "patient_id"}
        provenance = {k: v for k, v in provenance.items() if k in set(included_fields)}

    return ContextBundle(
        actor_id=aid,
        patient_id=patient_id,
        purpose=purpose,
        action=action,
        consent_status="NOT_REQUIRED_SELF" if auth_type == "SELF" else "ACTIVE",
        included_fields=included_fields,
        excluded_fields=excluded_fields,
        data=data,
        provenance=provenance,
        created_at=now,
    )
