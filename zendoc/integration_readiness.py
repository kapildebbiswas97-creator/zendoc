"""Owner-facing external integration readiness without secret disclosure."""
from __future__ import annotations

import os

from .capability_registry import get_capability_registry
from .carefin_cases import carefin_partner_status
from .health_shop import affiliate_readiness
from .identity_verification import identity_provider_status
from .notification_providers import notification_provider_status
from .payments import payment_gateway_status
from .community_media import get_community_media_storage
from .record_storage import get_record_storage
from .jev_system_one import jev_runtime_status
from .agentic_integration_mesh import integration_ownership
from .places_provider import places_configuration_status
from .db import get_db
from .operational_fulfilment import ensure_operational_fulfilment_schema


def _present(*keys):
    return all(bool(str(os.environ.get(key) or "").strip()) for key in keys)


def _item(key,label,status,software_ready,external_required,required_config,notes,href=None):
    ownership = integration_ownership(key)
    return {
        "key":key,
        "label":label,
        "status":status,
        "software_ready":bool(software_ready),
        "external_required":bool(external_required),
        "required_config":list(required_config),
        "configuration_present":all(_present(name) for name in required_config) if required_config else True,
        "notes":notes,
        "href":href,
        **ownership,
    }


def _care_provider_runtime():
    """Return non-clinical provider-availability counts only."""
    ensure_operational_fulfilment_schema()
    db=get_db()
    home_health=int(db.execute(
        """
        SELECT COUNT(DISTINCT s.provider_id) c
        FROM home_health_provider_services s
        JOIN users u ON u.id=s.provider_id AND u.active=1
        JOIN provider_profiles pp ON pp.user_id=u.id
        WHERE s.active=1 AND LOWER(COALESCE(pp.verification_status,''))='verified'
        """
    ).fetchone()["c"] or 0)
    pharmacies=int(db.execute(
        """
        SELECT COUNT(DISTINCT u.id) c
        FROM users u
        JOIN provider_profiles pp ON pp.user_id=u.id
        WHERE u.active=1 AND u.role='pharmacy'
          AND LOWER(COALESCE(pp.verification_status,''))='verified'
        """
    ).fetchone()["c"] or 0)
    return {
        "home_health_verified_providers": home_health,
        "verified_pharmacies": pharmacies,
    }


def integration_readiness_snapshot():
    registry=get_capability_registry()
    gateway=payment_gateway_status()
    affiliate=affiliate_readiness()
    identity=identity_provider_status()
    carefin=carefin_partner_status()
    media=get_community_media_storage().status()
    records=get_record_storage().status()
    notifications=notification_provider_status()
    jev=jev_runtime_status()
    places=places_configuration_status()
    care_runtime=_care_provider_runtime()
    configured_places_provider=str(places.get("configured_provider") or "none").strip().lower()
    if configured_places_provider=="google":
        places_required_config=("ZENDOC_PLACES_PROVIDER","ZENDOC_GOOGLE_PLACES_API_KEY")
    elif configured_places_provider in {"nominatim","openstreetmap","osm"}:
        places_required_config=("ZENDOC_PLACES_PROVIDER",)
    elif places.get("production_fallback_active"):
        places_required_config=()
    else:
        places_required_config=("ZENDOC_PLACES_PROVIDER",)

    rows=[
        _item(
            "jev_decisions","Jev / System One agent decisions",
            jev["status"].upper(),True,not bool(jev["configured"]),
            (),
            (
                "The bounded Jev decision adapter and per-agent control profiles are implemented. "
                "A real TypeSafe API key or an approved local Jev-compatible endpoint is still required before live Jev decisions run. "
                "Configuration never grants tool permission and does not prove provider uptime or decision quality."
            ),
            "/agent-os",
        ),
        _item(
            "payments","Care payments / UPI-capable gateway",
            registry["connected_payments_gateway"]["status"],True,not gateway["ready_for_live_payment"],
            ("ZENDOC_RAZORPAY_KEY_ID","ZENDOC_RAZORPAY_KEY_SECRET","ZENDOC_RAZORPAY_WEBHOOK_SECRET"),
            "Invoice, checkout signature and webhook-confirmed paid state are implemented. BHIM/Paytm/PhonePe/Google Pay-style UPI methods depend on the real gateway/account capabilities.",
            "/payments",
        ),
        _item(
            "external_ekyc","External eKYC",
            registry["external_ekyc"]["status"],True,not identity["operator_verified"],
            ("ZENDOC_EKYC_PROVIDER","ZENDOC_EKYC_WEBHOOK_SECRET","ZENDOC_EKYC_VERIFIED"),
            identity["truth_notice"],"/admin/identity-verification",
        ),
        _item(
            "carefin_partner","Insurance / scheme authoritative verification",
            registry["carefin_live_verification"]["status"],True,not carefin["operator_verified"],
            ("ZENDOC_CAREFIN_PARTNER_NAME","ZENDOC_CAREFIN_WEBHOOK_SECRET","ZENDOC_CAREFIN_PARTNER_VERIFIED"),
            carefin["truth_notice"],"/admin/carefin-cases",
        ),
        _item(
            "durable_media","Durable image/video & record storage",
            registry["object_storage"]["status"],True,not bool(media.get("durable_public_ready")),
            ("ZENDOC_S3_BUCKET","ZENDOC_S3_ACCESS_KEY_ID","ZENDOC_S3_SECRET_ACCESS_KEY","ZENDOC_STORAGE_VERIFIED"),
            f"Community media: {media.get('status')}. Medical records: {records.get('status')}. Local storage is not treated as durable public hosting.",
        ),
        _item(
            "webrtc","Voice/video call network reachability",
            registry["voice_video_calling"]["status"],True,not _present("ZENDOC_WEBRTC_ICE_SERVERS_JSON"),
            ("ZENDOC_WEBRTC_ICE_SERVERS_JSON",),
            "Authenticated WebRTC signaling and browser media controls are implemented. TURN/STUN configuration plus two-device testing is needed for reliable public-network calls.",
            "/messages",
        ),
        _item(
            "affiliate","Affiliate / referral revenue",
            registry["affiliate_referral_revenue"]["status"],True,not bool(affiliate["configured_merchants"]),
            (),
            "Health Shop discovery and click attribution work. Revenue claims require approved merchant programs and configured merchant templates; conversion/settlement still needs merchant evidence.",
            "/admin/commerce-referrals",
        ),
        _item(
            "maps","Live map/places discovery",
            registry["external_places_discovery"]["status"],True,
            registry["external_places_discovery"]["status"]!="WORKING",
            places_required_config,
            (
                "Local/official healthcare discovery is a separate working software path. "
                f"External discovery mode={places.get('mode')}; configuration/fallback availability does not prove "
                "runtime reachability, quota, result availability or ZENDOC booking connectivity."
            ),
        ),
        _item(
            "home_health_fulfilment","Home-health real provider fulfilment",
            "BETA" if care_runtime["home_health_verified_providers"] else "INTEGRATION_REQUIRED",
            True,not bool(care_runtime["home_health_verified_providers"]),(),
            (
                f"{care_runtime['home_health_verified_providers']} active verified ZENDOC provider account(s) currently publish at least one home-health capability. "
                "Assignment and provider-controlled acceptance/progress are implemented; an intake request alone never confirms a visit."
                if care_runtime["home_health_verified_providers"]
                else
                "Home-health request intake works, but no active verified ZENDOC provider currently publishes a home-health capability. "
                "A request remains unconfirmed until a real provider is assigned and accepts it."
            ),
            "/home-health",
        ),
        _item(
            "pharmacy_fulfilment","Pharmacy provider fulfilment",
            "BETA" if care_runtime["verified_pharmacies"] else "INTEGRATION_REQUIRED",
            True,not bool(care_runtime["verified_pharmacies"]),(),
            (
                f"{care_runtime['verified_pharmacies']} active verified ZENDOC pharmacy account(s) are available for provider-side workflows. "
                "Order acknowledgement and tracking are provider-recorded; stock, dispensing and delivery are never inferred from account verification alone."
                if care_runtime["verified_pharmacies"]
                else
                "Pharmacy request software exists, but no active verified ZENDOC pharmacy account is currently available for provider-side fulfilment."
            ),
            "/pharmacy",
        ),
        _item(
            "medical_transport_dispatch","Medical transport live dispatch",
            "INTEGRATION_REQUIRED",True,True,(),
            "Medical-transport request intake is implemented, but ZENDOC has no live vehicle/ambulance dispatch provider adapter. "
            "A recorded request does not confirm dispatch, vehicle, ETA, equipment, price or provider acceptance.",
            "/ambulance",
        ),
        _item(
            "video_search","Live YouTube educational discovery",
            registry["video_intelligence"]["status"],True,registry["video_intelligence"]["status"]!="WORKING",
            ("ZENDOC_VIDEO_PROVIDER","ZENDOC_YOUTUBE_API_KEY"),
            "ZENDOC video/community posting is separate. Live YouTube search results require the configured YouTube provider/key.",
            "/videos",
        ),
        _item(
            "external_notifications","Email / SMS / WhatsApp / push delivery",
            registry["external_notifications"]["status"],True,True,(),
            "In-app notifications work. External WhatsApp/SMS/push require authorized provider APIs; SMTP/email has its own configured delivery path.",
            "/notifications",
        ),
        _item(
            "database","Durable PostgreSQL",
            registry["postgresql"]["status"],True,registry["postgresql"]["status"]!="WORKING",
            ("DATABASE_URL","ZENDOC_PERSISTENCE_VERIFIED"),
            registry["postgresql"]["description"],
        ),
    ]

    blocking=[row for row in rows if row["external_required"]]
    working=[row for row in rows if not row["external_required"]]
    return {
        "integrations":rows,
        "external_blockers":blocking,
        "external_blocker_count":len(blocking),
        "ready_count":len(working),
        "total_count":len(rows),
        "truth_notice":"A green software boundary does not prove a third-party account, credential, partnership, network, quota, settlement, or real-world fulfilment is active.",
        "notification_status":notifications,
    }
