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


def _present(*keys):
    return all(bool(str(os.environ.get(key) or "").strip()) for key in keys)


def _item(key,label,status,software_ready,external_required,required_config,notes,href=None):
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
            registry["healthcare_finder"]["status"],True,registry["healthcare_finder"]["status"]!="WORKING",
            ("ZENDOC_PLACES_PROVIDER","ZENDOC_GOOGLE_PLACES_API_KEY"),
            "Local/official healthcare discovery always remains available. OpenStreetMap/Nominatim can provide external unverified discovery without a Google key; Google Places remains an optional server-side upgrade.",
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
