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
        "description": "Find verified clinicians, search specialties, check schedules, and book direct consultations.",
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
        "id": "home_health",
        "title": "Home Healthcare",
        "badge": "Beta",
        "badge_color": "primary",
        "icon": "home",
        "description": "Doctor home visits, nursing care, physiotherapy, elder attendants, and medical equipment rental.",
        "url": "/home-health",
    },
    {
        "id": "ambulance",
        "title": "Ambulance & Transport",
        "badge": "Working Now",
        "badge_color": "success",
        "icon": "ambulance",
        "description": "Emergency ambulance dispatch (108), Basic Life Support, ICU transport, and wheelchair vans.",
        "url": "/ambulance",
    },
    {
        "id": "pharmacy",
        "title": "Pharmacy & Medicines",
        "badge": "Working Now",
        "badge_color": "success",
        "icon": "pills",
        "description": "Medicine catalog search, nearby pharmacy finder, delivery requests, and refill reminders.",
        "url": "/pharmacy",
    },
    {
        "id": "iot_hub",
        "title": "IoT Health Device Hub",
        "badge": "Working Now",
        "badge_color": "success",
        "icon": "laptop-medical",
        "description": "Connect smartwatches, BP monitors, glucometers, scales, and pulse oximeters with provenance tracking.",
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
        "description": "Upload lab reports, automated structured extraction, lab trends, and longitudinal health timeline.",
        "url": "/records",
    },
    {
        "id": "ai_assistant",
        "title": "ZENDOC AI Health Assistant",
        "badge": "Working Now",
        "badge_color": "success",
        "icon": "robot",
        "description": "24/7 AI health guidance with emergency safety checks, symptom evaluation, and instant service routing.",
        "url": "/ai",
    },
]


def get_marketplace_catalog():
    """Return full services marketplace catalog."""
    return MARKETPLACE_CATEGORIES
