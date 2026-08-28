"""
Universal Search Engine for ZENDOC.

Classifies search queries across doctors, symptoms, diagnostic reports, pharmacies,
ambulance, fitness, family records, and direct platform features.
"""

from .db import get_db
from .exercise_library import list_exercises
from .family_care import list_family_members
from .healthcare_finder import HealthcareFinder
from .healthcare_finder import normalize_query


def search_all(user, query):
    """
    Execute universal search across ZENDOC ecosystem.
    Returns categorized results with direct destination URLs.
    """
    clean_q = str(query or "").strip()
    if not clean_q:
        return {"query": "", "categories": [], "total_matches": 0}

    lower = clean_q.lower()
    results = []

    # 1. Family member matching
    if user:
        family_members = list_family_members(user)
        matched_family = [fm for fm in family_members if lower in fm["member_name"].lower() or lower in fm["relationship"].lower()]
        if matched_family:
            results.append({
                "category": "Family Care",
                "label": "Family Members",
                "items": [
                    {
                        "title": fm["member_name"],
                        "subtitle": f"{fm['relationship'].title()} • {fm['city'] or 'Home'}",
                        "url": f"/family?member_id={fm['id']}",
                        "type": "family_member",
                    }
                    for fm in matched_family
                ],
            })

    # 2. Healthcare Provider Search (Doctor, Specialist, Hospital, Pharmacy)
    if any(k in lower for k in ("doctor", "cardiologist", "dermatologist", "physician", "hospital", "pharmacy", "clinic", "specialist")):
        category = "pharmacy" if "pharmacy" in lower else "hospital" if "hospital" in lower else "doctor"
        specialty = clean_q if category == "doctor" and clean_q.lower() not in {"doctor", "specialist"} else ""
        finder_results = HealthcareFinder().search(normalize_query(category=category, specialty=specialty))
        external_places = finder_results.get("external_places", {})
        items = finder_results.get("registered_providers", []) + external_places.get("results", [])
        if items:
            results.append({
                "category": "Healthcare Providers",
                "label": "Doctors & Facilities",
                "items": [
                    {
                        "title": item.get("name") or item.get("organization", "Provider"),
                        "subtitle": f"{item.get('specialty') or item.get('provider_type', 'Healthcare')} • {item.get('city', '')}",
                        "url": f"/finder?q={clean_q}",
                        "type": "provider",
                    }
                    for item in items[:5]
                ],
            })

    # 3. Emergency / Transport
    if any(k in lower for k in ("ambulance", "transport", "108", "icu van", "wheelchair")):
        results.append({
            "category": "Emergency & Transport",
            "label": "Ambulance Services",
            "items": [
                {
                    "title": "Request Medical Transport / Ambulance",
                    "subtitle": "Emergency 108, BLS, ALS, & Patient Transport",
                    "url": "/ambulance",
                    "type": "ambulance",
                }
            ],
        })

    # 4. Medicine / Pharmacy
    if any(k in lower for k in ("medicine", "pharmacy", "drug", "tablet", "pill", "prescription")):
        results.append({
            "category": "Pharmacy & Medicines",
            "label": "Medicine Services",
            "items": [
                {
                    "title": f"Search Medicines for '{clean_q}'",
                    "subtitle": "Order delivery & locate nearby pharmacies",
                    "url": f"/pharmacy?q={clean_q}",
                    "type": "pharmacy",
                }
            ],
        })

    # 5. Fitness & Exercises
    ex_res = list_exercises(q=clean_q, limit=5)
    if ex_res.get("exercises"):
        results.append({
            "category": "Fitness & Exercises",
            "label": "Exercise Library",
            "items": [
                {
                    "title": ex["name"],
                    "subtitle": f"{ex['category'].title()} • {ex['muscle_group']}",
                    "url": f"/fitness/exercises/{ex['id']}",
                    "type": "exercise",
                }
                for ex in ex_res["exercises"]
            ],
        })

    # 6. Health Records / Reports
    if user and any(k in lower for k in ("report", "blood test", "lab", "record", "scan", "xray", "mri", "my reports")):
        results.append({
            "category": "Health Memory",
            "label": "Medical Records",
            "items": [
                {
                    "title": "View Stored Medical Reports",
                    "subtitle": "Longitudinal health records & report intelligence",
                    "url": "/records",
                    "type": "record",
                }
            ],
        })

    # 7. AI Health Assistant
    results.append({
        "category": "ZENDOC AI",
        "label": "AI Health Consultation",
        "items": [
            {
                "title": f"Ask ZENDOC AI about '{clean_q}'",
                "subtitle": "Get instant educational advice & symptom guidance",
                "url": f"/ai?prompt={clean_q}",
                "type": "ai_assistant",
            }
        ],
    })

    total_matches = sum(len(c["items"]) for c in results)
    return {"query": clean_q, "categories": results, "total_matches": total_matches}
