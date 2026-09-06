"""Provider organization tenancy and membership enforcement."""
from __future__ import annotations

import uuid

from .db import get_db, now_iso
from .security import is_owner


ORG_TYPES = {"hospital", "clinic", "pharmacy_network", "diagnostic_network", "care_provider", "other"}
MEMBERSHIP_ROLES = {"owner", "admin", "doctor", "staff", "pharmacy", "lab", "member"}


def _value(actor, key, default=None):
    if actor is None:
        return default
    if hasattr(actor, "keys") and key in actor.keys():
        return actor[key]
    return actor.get(key, default) if isinstance(actor, dict) else default


def _user_id(actor):
    return int(_value(actor, "id", 0) or 0)


def get_organization(organization_id):
    row = get_db().execute(
        "SELECT * FROM provider_organizations WHERE id=? AND active=1",
        (int(organization_id),),
    ).fetchone()
    if not row:
        raise LookupError("Provider organization not found.")
    return dict(row)


def create_organization(actor, data):
    if _value(actor, "role") not in {"hospital", "pharmacy", "doctor", "admin"}:
        raise PermissionError("This account type cannot create a provider organization.")
    if _value(actor, "role") == "admin" and not is_owner(actor):
        raise PermissionError("Only the configured ZENDOC owner may create organizations as admin.")

    name = str(data.get("name") or "").strip()
    if not name:
        raise ValueError("Organization name is required.")
    org_type = str(data.get("organization_type") or "other").strip().lower()
    if org_type not in ORG_TYPES:
        raise ValueError("Invalid organization_type.")

    now = now_iso()
    uid = f"org_{uuid.uuid4().hex[:16]}"
    db = get_db()
    cursor = db.execute(
        """
        INSERT INTO provider_organizations
        (organization_uid,name,organization_type,owner_user_id,verification_status,active,
         address,city,state,postal_code,created_at,updated_at)
        VALUES (?,?,?,?, 'pending',1,?,?,?,?,?,?)
        """,
        (
            uid, name, org_type, _user_id(actor),
            str(data.get("address") or "").strip() or None,
            str(data.get("city") or "").strip() or None,
            str(data.get("state") or "").strip() or None,
            str(data.get("postal_code") or "").strip() or None,
            now, now,
        ),
    )
    org_id = int(cursor.lastrowid)
    db.execute(
        """
        INSERT INTO organization_memberships
        (organization_id,user_id,membership_role,status,requested_by,approved_by,created_at,updated_at)
        VALUES (?,?, 'owner','active',?,?,?,?)
        """,
        (org_id, _user_id(actor), _user_id(actor), _user_id(actor), now, now),
    )
    db.commit()
    return get_organization(org_id)


def request_membership(actor, organization_id, membership_role="member"):
    role = str(membership_role or "member").strip().lower()
    if role not in MEMBERSHIP_ROLES - {"owner", "admin"}:
        raise ValueError("Invalid membership role.")
    org = get_organization(organization_id)
    uid = _user_id(actor)
    if not uid:
        raise PermissionError("Authentication required.")
    now = now_iso()
    db = get_db()
    existing = db.execute(
        "SELECT * FROM organization_memberships WHERE organization_id=? AND user_id=?",
        (org["id"], uid),
    ).fetchone()
    if existing:
        if existing["status"] == "active":
            return dict(existing)
        db.execute(
            "UPDATE organization_memberships SET membership_role=?, status='pending', requested_by=?, updated_at=? WHERE id=?",
            (role, uid, now, existing["id"]),
        )
    else:
        db.execute(
            """
            INSERT INTO organization_memberships
            (organization_id,user_id,membership_role,status,requested_by,created_at,updated_at)
            VALUES (?,?,?,'pending',?,?,?)
            """,
            (org["id"], uid, role, uid, now, now),
        )
    db.commit()
    return dict(db.execute(
        "SELECT * FROM organization_memberships WHERE organization_id=? AND user_id=?",
        (org["id"], uid),
    ).fetchone())


def _can_manage_org(actor, organization_id):
    if is_owner(actor):
        return True
    uid = _user_id(actor)
    row = get_db().execute(
        """
        SELECT 1 FROM organization_memberships
        WHERE organization_id=? AND user_id=? AND status='active'
          AND membership_role IN ('owner','admin')
        """,
        (int(organization_id), uid),
    ).fetchone()
    return bool(row)


def approve_membership(actor, membership_id, status="active"):
    status = str(status or "").strip().lower()
    if status not in {"active", "rejected", "suspended"}:
        raise ValueError("Invalid membership status.")
    db = get_db()
    row = db.execute("SELECT * FROM organization_memberships WHERE id=?", (int(membership_id),)).fetchone()
    if not row:
        raise LookupError("Organization membership not found.")
    if not _can_manage_org(actor, row["organization_id"]):
        raise PermissionError("You cannot manage memberships for this organization.")
    now = now_iso()
    db.execute(
        "UPDATE organization_memberships SET status=?, approved_by=?, updated_at=? WHERE id=?",
        (status, _user_id(actor), now, row["id"]),
    )
    db.commit()
    return dict(db.execute("SELECT * FROM organization_memberships WHERE id=?", (row["id"],)).fetchone())


def active_membership(user_id, organization_id=None):
    db = get_db()
    if organization_id is not None:
        row = db.execute(
            """
            SELECT * FROM organization_memberships
            WHERE user_id=? AND organization_id=? AND status='active'
            """,
            (int(user_id), int(organization_id)),
        ).fetchone()
    else:
        row = db.execute(
            """
            SELECT * FROM organization_memberships
            WHERE user_id=? AND status='active'
            ORDER BY CASE membership_role WHEN 'owner' THEN 0 WHEN 'admin' THEN 1 ELSE 2 END, id
            LIMIT 1
            """,
            (int(user_id),),
        ).fetchone()
    return dict(row) if row else None


def verify_organization(actor, organization_id, status="verified"):
    if not is_owner(actor):
        raise PermissionError("Only the configured ZENDOC owner may verify provider organizations.")
    status = str(status or "").strip().lower()
    if status not in {"pending", "verified", "rejected", "suspended"}:
        raise ValueError("Invalid organization verification status.")
    org = get_organization(organization_id)
    get_db().execute(
        "UPDATE provider_organizations SET verification_status=?, updated_at=? WHERE id=?",
        (status, now_iso(), org["id"]),
    )
    get_db().commit()
    return get_organization(org["id"])


def create_location(actor, organization_id, data):
    org = get_organization(organization_id)
    if not _can_manage_org(actor, org["id"]):
        raise PermissionError("You cannot create locations for this organization.")
    if org["verification_status"] != "verified" and not is_owner(actor):
        raise PermissionError("Organization must be verified before provider locations are activated.")
    name = str(data.get("name") or "").strip()
    if not name:
        raise ValueError("Location name is required.")
    now = now_iso()
    location_uid = f"loc_{uuid.uuid4().hex[:16]}"
    db = get_db()
    cursor = db.execute(
        """
        INSERT INTO organization_locations
        (organization_id,location_uid,name,location_type,address,city,state,postal_code,latitude,longitude,active,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,1,?,?)
        """,
        (
            org["id"], location_uid, name,
            str(data.get("location_type") or "branch").strip().lower(),
            str(data.get("address") or "").strip() or None,
            str(data.get("city") or "").strip() or None,
            str(data.get("state") or "").strip() or None,
            str(data.get("postal_code") or "").strip() or None,
            data.get("latitude"), data.get("longitude"), now, now,
        ),
    )
    db.commit()
    return dict(db.execute("SELECT * FROM organization_locations WHERE id=?", (cursor.lastrowid,)).fetchone())


def bind_provider_profile(actor, organization_id, location_id=None):
    organization = get_organization(organization_id)
    if organization["verification_status"] != "verified":
        raise PermissionError("Organization must be verified before a provider profile can be formally bound to it.")
    membership = active_membership(_user_id(actor), organization_id)
    if not membership:
        raise PermissionError("An active organization membership is required before binding a provider profile.")
    if location_id is not None:
        loc = get_db().execute(
            "SELECT id FROM organization_locations WHERE id=? AND organization_id=? AND active=1",
            (int(location_id), int(organization_id)),
        ).fetchone()
        if not loc:
            raise PermissionError("Location does not belong to this organization.")
    db = get_db()
    profile = db.execute("SELECT id FROM provider_profiles WHERE user_id=?", (_user_id(actor),)).fetchone()
    if not profile:
        raise LookupError("Provider profile not found.")
    db.execute(
        "UPDATE provider_profiles SET organization_id=?, organization_location_id=?, updated_at=? WHERE user_id=?",
        (int(organization_id), int(location_id) if location_id else None, now_iso(), _user_id(actor)),
    )
    db.commit()
    return dict(db.execute("SELECT * FROM provider_profiles WHERE user_id=?", (_user_id(actor),)).fetchone())


def same_organization(actor, other_user_id):
    if is_owner(actor):
        return True
    uid = _user_id(actor)
    db = get_db()
    return bool(db.execute(
        """
        SELECT 1
        FROM organization_memberships a
        JOIN organization_memberships b ON b.organization_id=a.organization_id
        WHERE a.user_id=? AND b.user_id=?
          AND a.status='active' AND b.status='active'
        LIMIT 1
        """,
        (uid, int(other_user_id)),
    ).fetchone())


def assert_same_organization(actor, other_user_id):
    if not same_organization(actor, other_user_id):
        raise PermissionError("Cross-organization access is not permitted.")
    return True


def provider_resource_context(user_id):
    """Return verified provider organization/location context or standalone NULLs."""
    db = get_db()
    profile = db.execute(
        """
        SELECT pp.organization_id, pp.organization_location_id, po.verification_status
        FROM provider_profiles pp
        LEFT JOIN provider_organizations po ON po.id=pp.organization_id
        WHERE pp.user_id=?
        """,
        (int(user_id),),
    ).fetchone()
    if not profile or not profile["organization_id"]:
        return {"organization_id": None, "organization_location_id": None}
    membership = active_membership(int(user_id), int(profile["organization_id"]))
    if not membership or str(profile["verification_status"] or "").lower() != "verified":
        return {"organization_id": None, "organization_location_id": None}
    location_id = profile["organization_location_id"]
    if location_id:
        location = db.execute(
            """
            SELECT id FROM organization_locations
            WHERE id=? AND organization_id=? AND active=1
            """,
            (int(location_id), int(profile["organization_id"])),
        ).fetchone()
        if not location:
            location_id = None
    return {
        "organization_id": int(profile["organization_id"]),
        "organization_location_id": int(location_id) if location_id else None,
    }


def assert_resource_tenant(actor, resource):
    """Fail closed on cross-tenant access for tenant-bound provider resources."""
    if is_owner(actor):
        return True
    resource_org = resource.get("organization_id") if isinstance(resource, dict) else resource["organization_id"]
    if not resource_org:
        return True
    membership = active_membership(_user_id(actor), int(resource_org))
    if not membership:
        raise PermissionError("Cross-organization resource access is not permitted.")
    resource_location = (
        resource.get("organization_location_id")
        if isinstance(resource, dict)
        else resource["organization_location_id"]
    )
    if resource_location:
        profile = get_db().execute(
            "SELECT organization_location_id FROM provider_profiles WHERE user_id=?",
            (_user_id(actor),),
        ).fetchone()
        actor_location = profile["organization_location_id"] if profile else None
        if actor_location and int(actor_location) != int(resource_location):
            raise PermissionError("Cross-branch resource access is not permitted.")
    return True
