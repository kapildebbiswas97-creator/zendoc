"""
Universal Search Engine for ZENDOC.

Classifies search queries across doctors, symptoms, diagnostic reports, pharmacies,
ambulance, fitness, family records, and direct platform features.
"""

from .exercise_library import list_exercises
from .family_care import list_family_members
from .universal_health_search import universal_search as search_healthcare


HEALTHCARE_QUERY_TERMS = (
    "doctor", "doctors", "cardiologist", "dermatologist", "physician", "specialist",
    "hospital", "hospitals", "clinic", "clinics", "pharmacy", "pharmacies", "chemist",
    "medical store", "medical shop", "diagnostic", "diagnostics", "laboratory", "lab",
    "health centre", "health center", "phc", "chc", "nursing home", "blood bank",
    "emergency care",
)


def _healthcare_search_items(clean_q):
    """Reuse the canonical healthcare discovery parser for the legacy global search.

    This keeps shorthand such as ``medical store Fulia`` or ``clinic near Nairobi``
    aligned with the dedicated Universal Healthcare Search. Results retain their
    source/verification truth and public/external listings are never promoted to
    connected ZENDOC booking.
    """
    result = search_healthcare(clean_q)
    items = []
    for item in result.get("results", [])[:8]:
        location = item.get("city") or item.get("district") or item.get("state") or item.get("address") or ""
        source = item.get("source") or "healthcare discovery"
        verification = item.get("verification_status") or "not_verified"
        detail = item.get("specialty") or item.get("category") or "Healthcare"
        subtitle_parts = [str(detail).replace("_", " ").title()]
        if location:
            subtitle_parts.append(str(location))
        if source != "zendoc_provider_network":
            subtitle_parts.append("External/public discovery")
        elif verification == "verified":
            subtitle_parts.append("ZENDOC verified")
        items.append({
            "title": item.get("name") or item.get("provider_name") or item.get("organization") or "Healthcare provider",
            "subtitle": " • ".join(subtitle_parts),
            "url": f"/universal-search?q={clean_q}",
            "type": "provider",
            "source": source,
            "verification_status": verification,
            "bookable_in_zendoc": bool(item.get("bookable_in_zendoc")),
        })
    return items


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

    # 2. Healthcare discovery. Use the same parser/data tiers as the dedicated
    # Universal Healthcare Search instead of maintaining a weaker duplicate.
    if any(term in lower for term in HEALTHCARE_QUERY_TERMS):
        healthcare_items = _healthcare_search_items(clean_q)
        if healthcare_items:
            results.append({
                "category": "Healthcare Providers",
                "label": "Doctors & Facilities",
                "items": healthcare_items,
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
    if any(k in lower for k in ("medicine", "pharmacy", "chemist", "medical store", "medical shop", "drug", "tablet", "pill", "prescription")):
        results.append({
            "category": "Pharmacy & Medicines",
            "label": "Medicine Services",
            "items": [
                {
                    "title": f"Search Medicines for '{clean_q}'",
                    "subtitle": "Medicine safety flow & nearby pharmacy discovery",
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

    # 7. Permitted Contacts (ZENDOC Connect)
    if user:
        try:
            from .connect import discover_contacts, list_conversations
            permitted_contacts = discover_contacts(user, query=clean_q, limit=4)
            if permitted_contacts:
                results.append({
                    "category": "Care Contacts",
                    "label": "Permitted Contacts",
                    "items": [
                        {
                            "title": contact["name"],
                            "subtitle": f"{contact['role'].title()}{' • ' + contact['city'] if contact.get('city') else ''} • {contact['reason']}",
                            "url": f"/messages?q={clean_q}",
                            "type": "contact",
                        }
                        for contact in permitted_contacts
                    ],
                })

            user_conversations = list_conversations(user, limit=20)
            matched_conversations = [
                conv for conv in user_conversations
                if lower in (conv.get("title") or "").lower()
                or any(lower in p["name"].lower() for p in conv.get("participants", []))
            ]
            if matched_conversations:
                results.append({
                    "category": "Messages",
                    "label": "Conversations",
                    "items": [
                        {
                            "title": conv.get("title") or "Conversation",
                            "subtitle": f"{conv.get('context_type', 'Direct').replace('_', ' ').title()} • {len(conv.get('participants', []))} participants",
                            "url": f"/messages?conversation_id={conv['id']}",
                            "type": "conversation",
                        }
                        for conv in matched_conversations[:4]
                    ],
                })
        except Exception:
            pass

    # 8. Educational Videos
    if any(k in lower for k in ("video", "exercise", "squat", "pushup", "plank", "rehab", "technique", "mobility")):
        results.append({
            "category": "Video Guidance",
            "label": "Educational Videos",
            "items": [
                {
                    "title": f"Watch Guidance & Videos for '{clean_q}'",
                    "subtitle": "Truthful video finder & step-by-step exercise instructions",
                    "url": f"/videos?q={clean_q}",
                    "type": "video",
                }
            ],
        })

    # 9. AI Health Assistant
    results.append({
        "category": "ZENDOC AI",
        "label": "AI Health Consultation",
        "items": [
            {
                "title": f"Ask ZENDOC AI about '{clean_q}'",
                "subtitle": "Get educational health guidance with deterministic safety boundaries",
                "url": f"/ai?prompt={clean_q}",
                "type": "ai_assistant",
            }
        ],
    })

    total_matches = sum(len(c["items"]) for c in results)
    return {"query": clean_q, "categories": results, "total_matches": total_matches}
