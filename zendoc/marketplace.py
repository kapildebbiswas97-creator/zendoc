"""
ZENDOC Unified Services Marketplace.

Central catalog of all ZENDOC ecosystem services with clear status indicators:
Working Now, Beta, Verified Provider, Integration Required, Coming Soon.
"""

MARKETPLACE_CATEGORIES = [
    {
        "id": "doctors_hospitals",
        "title": "Doctors & Hospitals",
        "badge": "Working Now",
        "badge_color": "success",
        "icon": "user-md",
        "description": "Discover healthcare options and, for active verified ZENDOC providers with published schedules, request connected appointments. External/public listings remain discovery-only.",
        "url": "/finder",
    },
    {
        "id": "family_care",
        "title": "Family Care & Remote Parents",
        "badge": "Working Now",
        "badge_color": "success",
        "icon": "users",
        "description": "Manage healthcare for parents, children, and remote dependents with proxy authorization.",
        "url": "/family",
    },
    {
        "id": "health_hub",
        "title": "Health Hub",
        "badge": "Competition Beta",
        "badge_color": "primary",
        "icon": "heartbeat",
        "description": (
            "Daily health learning, child-development continuity, real video discovery and truthful "
            "health-product search handoffs. Creator publishing, cross-posting and affiliate attribution "
            "remain disabled until real integrations are configured."
        ),
        "url": "/health-hub",
    },
    {
        "id": "mental_wellness",
        "title": "Mental Wellness & Awareness",
        "badge": "Working Now",
        "badge_color": "success",
        "icon": "brain",
        "description": "A dedicated non-diagnostic wellbeing check-in, life-stage awareness and safe routes to support.",
        "url": "/mental-wellness",
    },
    {
        "id": "health_community",
        "title": "Health Community",
        "badge": "Working Beta",
        "badge_color": "primary",
        "icon": "users",
        "description": "Health-only posts, 24-hour stories, follows, likes, comments, reporting and blocking. Community content is user-generated, not verified medical advice.",
        "url": "/community",
    },
    {
        "id": "health_shop",
        "title": "Health Shop",
        "badge": "External Handoffs",
        "badge_color": "warning",
        "icon": "shopping-bag",
        "description": "Food, fitness, eyewear, wellness and health-device discovery across external merchants with truthful referral/affiliate status.",
        "url": "/health-shop",
    },
    {
        "id": "payments",
        "title": "Connected Care Payments",
        "badge": "Gateway Integration",
        "badge_color": "warning",
        "icon": "credit-card",
        "description": "Verified connected providers and pharmacies can issue care invoices. Live checkout activates only with configured gateway credentials and signed webhook verification.",
        "url": "/payments",
    },
    {
        "id": "zendoc_business",
        "title": "ZENDOC for Business",
        "badge": "B2B + B2C",
        "badge_color": "primary",
        "icon": "briefcase",
        "description": "Patient/family B2C services plus provider, institution, pharmacy and partner workflow readiness for B2B operations.",
        "url": "/business",
    },
    {
        "id": "home_health",
        "title": "Home Healthcare",
        "badge": "Request Workflow",
        "badge_color": "warning",
        "icon": "home",
        "description": "Record home-care requests. Real provider assignment and acceptance appear only when an active verified ZENDOC provider has published that service capability.",
        "url": "/home-health",
    },
    {
        "id": "ambulance",
        "title": "Ambulance & Transport",
        "badge": "Integration Required",
        "badge_color": "warning",
        "icon": "ambulance",
        "description": "108 emergency guidance and nearest emergency department routing. Real-time ambulance dispatch requires a verified external dispatch service integration (INTEGRATION_REQUIRED).",
        "url": "/ambulance",
    },
    {
        "id": "pharmacy",
        "title": "Pharmacy & Medicines",
        "badge": "Verified Request Workflow",
        "badge_color": "primary",
        "icon": "pills",
        "description": "Medicine reference search, verified-pharmacy discovery, reminders, and pharmacy-request tracking. Stock, price, prescription acceptance and delivery require pharmacy confirmation.",
        "url": "/pharmacy",
    },
    {
        "id": "iot_hub",
        "title": "IoT Health Device Hub",
        "badge": "Registration Only",
        "badge_color": "warning",
        "icon": "laptop-medical",
        "description": "Register personal device inventory records. Live pairing and automatic manufacturer/device sync are Integration Required; manual values are not labelled as trusted device evidence.",
        "url": "/iot-hub",
    },
    {
        "id": "fitness",
        "title": "AI Fitness Coach",
        "badge": "Working Now",
        "badge_color": "success",
        "icon": "running",
        "description": "Personalised workout plans, 40+ exercise instructions, tutorial videos, and progress trends.",
        "url": "/fitness",
    },
    {
        "id": "health_records",
        "title": "Health Records & Intelligence",
        "badge": "Working Now",
        "badge_color": "success",
        "icon": "file-medical-alt",
        "description": "Upload health records, maintain report metadata and manually structured results, review longitudinal trends, and use the Health Timeline. Extraction status stays explicit when automation is unavailable.",
        "url": "/records",
    },
    {
        "id": "ai_assistant",
        "title": "ZENDOC AI Health Assistant",
        "badge": "Working Now",
        "badge_color": "success",
        "icon": "robot",
        "description": "Bounded educational health guidance, deterministic emergency-first safety checks, non-diagnostic symptom guidance, and permissioned service navigation.",
        "url": "/ai",
    },
]


def get_marketplace_catalog():
    """Return full services marketplace catalog."""
    return MARKETPLACE_CATEGORIES
