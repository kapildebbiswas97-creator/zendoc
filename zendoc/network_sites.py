"""
ZENDOC Network Sites Multi-Tenant Runtime & Site Provisioning Agent.
Powers public digital fronts for doctors, clinics, hospitals, diagnostic centres,
pharmacies, and organizations with truthful provenance, branding, services, and booking.
"""
from __future__ import annotations

import json
import re
import uuid
from typing import Any

from .db import get_db, now_iso
from .event_bus import publish_event


PROVENANCE_TIERS = ("VERIFIED", "PROVIDER_SUPPLIED", "OFFICIAL_SOURCE")
SITE_ENTITY_TYPES = (
    "doctor",
    "clinic",
    "hospital",
    "diagnostic_centre",
    "pharmacy",
    "health_program",
    "organization",
)


def _slugify(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", str(text or "").strip().lower()).strip("-")
    return cleaned[:80] or f"site-{uuid.uuid4().hex[:8]}"


def get_site_by_slug(slug: str) -> dict[str, Any] | None:
    clean_slug = str(slug or "").strip().lower()
    row = get_db().execute("SELECT * FROM network_sites WHERE slug=?", (clean_slug,)).fetchone()
    if not row:
        return None
    item = dict(row)
    item["theme"] = json.loads(item.get("theme_json") or "{}")
    item["services"] = json.loads(item.get("services_json") or "[]")
    item["hours"] = json.loads(item.get("hours_json") or "{}")
    item["location"] = json.loads(item.get("location_json") or "{}")
    item["contact"] = json.loads(item.get("contact_json") or "{}")
    return item


def list_network_sites(
    entity_type: str | None = None,
    city: str | None = None,
    verified_only: bool = False,
    limit: int = 50,
) -> list[dict[str, Any]]:
    db = get_db()
    clauses = ["status='active'"]
    params = []
    if entity_type:
        clauses.append("entity_type=?")
        params.append(str(entity_type).strip().lower())
    if verified_only:
        clauses.append("provenance='VERIFIED'")
    where = f"WHERE {' AND '.join(clauses)}"
    rows = db.execute(f"SELECT * FROM network_sites {where} ORDER BY id DESC LIMIT ?", tuple(params + [max(1, min(limit, 100))])).fetchall()
    sites = []
    for r in rows:
        item = dict(r)
        item["theme"] = json.loads(item.get("theme_json") or "{}")
        item["services"] = json.loads(item.get("services_json") or "[]")
        item["hours"] = json.loads(item.get("hours_json") or "{}")
        item["location"] = json.loads(item.get("location_json") or "{}")
        item["contact"] = json.loads(item.get("contact_json") or "{}")
        if city:
            site_city = (item.get("location") or {}).get("city", "")
            if str(city).lower() not in site_city.lower():
                continue
        sites.append(item)
    return sites


class SiteProvisioningAgent:
    """
    Autonomous and provider-directed provisioning agent for multi-tenant network sites.
    Grafts official public records or verified provider profiles into branded network sites
    while strictly preserving provenance and truthful availability boundaries.
    """

    @classmethod
    def provision_site(
        cls,
        actor: Any,
        entity_type: str,
        entity_id: int | None = None,
        slug: str | None = None,
        custom_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        entity_type = str(entity_type or "").strip().lower()
        if entity_type not in SITE_ENTITY_TYPES:
            raise ValueError(f"Invalid entity_type '{entity_type}'. Allowed: {', '.join(SITE_ENTITY_TYPES)}")

        custom_data = custom_data or {}
        db = get_db()

        title = custom_data.get("title")
        tagline = custom_data.get("tagline")
        description = custom_data.get("description")
        services = custom_data.get("services") or []
        hours = custom_data.get("hours") or {
            "monday_friday": "09:00 - 18:00",
            "saturday": "09:00 - 14:00",
            "sunday": "Closed",
        }
        location = custom_data.get("location") or {}
        contact = custom_data.get("contact") or {}
        emergency_guidance = custom_data.get(
            "emergency_guidance",
            "For acute or life-threatening emergencies, call national emergency services (102/108) or proceed immediately to the nearest casualty department.",
        )
        theme = custom_data.get("theme") or {
            "primary_color": "#0d9488",
            "accent_color": "#0284c7",
            "font_family": "Inter, sans-serif",
        }
        provenance = "PROVIDER_SUPPLIED"
        trust_tier = "COMMUNITY"
        booking_enabled = 1

        # Introspect existing entity if provided
        if entity_id:
            if entity_type in {"doctor", "clinic", "hospital", "pharmacy"}:
                prov_row = db.execute(
                    """
                    SELECT p.*, u.name as user_name, u.email as user_email
                    FROM provider_profiles p
                    JOIN users u ON u.id=p.user_id
                    WHERE p.id=?
                    """,
                    (entity_id,),
                ).fetchone()
                if prov_row:
                    prov_row = dict(prov_row)
                    title = title or prov_row.get("organization") or prov_row.get("user_name")
                    tagline = tagline or f"Quality healthcare by {prov_row.get('user_name')}"
                    location = location or {
                        "address": prov_row.get("address"),
                        "city": prov_row.get("city"),
                        "state": prov_row.get("state"),
                        "postal_code": prov_row.get("postal_code"),
                        "latitude": prov_row.get("latitude"),
                        "longitude": prov_row.get("longitude"),
                    }
                    contact = contact or {
                        "phone": prov_row.get("public_phone"),
                        "email": prov_row.get("user_email"),
                    }
                    if prov_row.get("verification_status") == "verified":
                        provenance = "VERIFIED"
                        trust_tier = "ZENDOC_VERIFIED"
                        booking_enabled = 1
                    else:
                        provenance = "PROVIDER_SUPPLIED"
                        trust_tier = "UNVERIFIED"

            # Check official public directory
            if not title:
                pub_row = db.execute("SELECT * FROM public_healthcare_entities WHERE id=?", (entity_id,)).fetchone()
                if pub_row:
                    pub_row = dict(pub_row)
                    title = title or pub_row.get("name")
                    tagline = tagline or f"Official directory listing ({pub_row.get('source_id') or 'Public Health'})"
                    location = location or {
                        "address": pub_row.get("address"),
                        "city": pub_row.get("city"),
                        "state": pub_row.get("state"),
                        "postal_code": pub_row.get("postal_code"),
                        "latitude": pub_row.get("latitude"),
                        "longitude": pub_row.get("longitude"),
                    }
                    contact = contact or {"phone": pub_row.get("public_phone")}
                    provenance = "OFFICIAL_SOURCE"
                    trust_tier = "PUBLIC_DIRECTORY"
                    booking_enabled = 0

        title = str(title or f"ZENDOC Care Site {entity_type.capitalize()}").strip()
        final_slug = _slugify(slug or title)

        # Ensure slug uniqueness
        existing_slug = db.execute("SELECT id FROM network_sites WHERE slug=?", (final_slug,)).fetchone()
        if existing_slug:
            final_slug = f"{final_slug}-{uuid.uuid4().hex[:4]}"

        now = now_iso()
        cursor = db.execute(
            """
            INSERT INTO network_sites
            (slug, entity_type, entity_id, title, tagline, description, theme_json, services_json, hours_json, location_json, contact_json, emergency_guidance, provenance, trust_tier, booking_enabled, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
            """,
            (
                final_slug,
                entity_type,
                entity_id,
                title,
                tagline,
                description,
                json.dumps(theme),
                json.dumps(services),
                json.dumps(hours),
                json.dumps(location),
                json.dumps(contact),
                emergency_guidance,
                provenance,
                trust_tier,
                booking_enabled,
                now,
                now,
            ),
        )
        db.commit()
        site_id = cursor.lastrowid

        publish_event(
            "site.provisioned",
            actor=actor,
            entity_type="network_site",
            entity_id=str(site_id),
            status="success",
            payload={"site_id": site_id, "slug": final_slug, "provenance": provenance},
        )

        return get_site_by_slug(final_slug) or {}
