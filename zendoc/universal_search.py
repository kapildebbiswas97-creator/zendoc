"""
Universal Search Engine for ZENDOC.

Classifies search queries across doctors, symptoms, diagnostic reports, pharmacies,
ambulance, fitness, family records, and direct platform features.
"""

from flask import has_app_context

from .exercise_library import list_exercises
from .family_care import list_family_members
from .universal_health_search import universal_search as search_healthcare


PLATFORM_TOOL_CATALOG = (
    {
        "keywords": ("find care", "nearby care", "care near me", "doctor", "hospital", "clinic"),
        "title": "Find Care",
        "subtitle": "Discover doctors, hospitals, clinics and other care with source and availability boundaries",
        "url": "/finder",
        "type": "find_care",
    },
    {
        "keywords": ("government opd", "ors", "government hospital appointment", "opd appointment"),
        "title": "Government OPD · ORS",
        "subtitle": "Discover government care in ZENDOC and continue official OPD booking on the NIC ORS portal",
        "url": "/finder#government-ors-handoff",
        "type": "government_opd",
    },
    {
        "keywords": ("appointment", "appointments", "visit", "booking"),
        "title": "Appointments",
        "subtitle": "Review ZENDOC appointment requests, provider-confirmed status and recorded external visits",
        "url": "/appointments",
        "type": "appointments",
    },
    {
        "keywords": ("diagnostic", "diagnostics", "lab test", "blood test", "cbc", "home collection"),
        "title": "Diagnostics & Labs",
        "subtitle": "Browse diagnostic catalog information and provider-backed verified lab offers",
        "url": "/connected-care/diagnostics",
        "type": "diagnostics",
    },
    {
        "keywords": ("mental wellness", "mental health", "stress", "mood", "journal", "wellbeing", "self care", "self-care"),
        "title": "Mental Wellness & Awareness",
        "subtitle": "Private check-ins, private journal and life-stage-aware non-diagnostic support",
        "url": "/mental-wellness",
        "type": "mental_wellness",
    },
    {
        "keywords": ("family", "parent care", "child care", "dependent", "caregiver"),
        "title": "Family Care",
        "subtitle": "Consent-aware family coordination, dependents, tasks and remote parent care",
        "url": "/family",
        "type": "family_care",
    },
    {
        "keywords": ("fitness", "workout", "exercise", "hydration", "nutrition", "camera coach"),
        "title": "Fitness Hub",
        "subtitle": "Workouts, progress, nutrition, hydration and supported camera coaching",
        "url": "/fitness",
        "type": "fitness",
    },
    {
        "keywords": ("community", "post", "posts", "social", "story", "stories", "feed", "follow"),
        "title": "ZENDOC Health Community",
        "subtitle": "Health-focused posts, stories, comments, media and moderation controls",
        "url": "/community",
        "type": "community",
    },
    {
        "keywords": ("shop", "shopping", "amazon", "flipkart", "meesho", "blinkit", "zomato", "swiggy", "fitness product", "health product", "device"),
        "title": "ZENDOC Health Shop",
        "subtitle": "Health-focused external product discovery with truthful merchant/referral status",
        "url": "/health-shop",
        "type": "health_shop",
    },
    {
        "keywords": ("message", "messages", "chat", "conversation", "call", "video call", "voice call", "whatsapp", "telegram"),
        "title": "ZENDOC Connect",
        "subtitle": "Private policy-aware messages, media sharing and authorized voice/video calls",
        "url": "/messages",
        "type": "messages",
    },
    {
        "keywords": ("payment", "payments", "invoice", "razorpay"),
        "title": "ZENDOC Payments",
        "subtitle": "Connected payment workflow with real gateway verification only when configured",
        "url": "/payments",
        "type": "payments",
    },
    {
        "keywords": ("health memory", "timeline", "my records", "records", "report", "prescription", "vitals"),
        "title": "Health Memory",
        "subtitle": "Longitudinal records, timeline, reports, vitals and consent-controlled access",
        "url": "/health-summary",
        "type": "health_memory",
    },
    {
        "keywords": ("benefit", "benefits", "carefin", "insurance", "scheme", "pmjay", "swasthya sathi", "financial support"),
        "title": "Care Benefits · CareFin",
        "subtitle": "Discover possible government, insurance and charitable support without claiming approval",
        "url": "/carefin",
        "type": "carefin",
    },
    {
        "keywords": ("care journey", "follow up", "continuity", "next step"),
        "title": "Care Journey",
        "subtitle": "Connect discovery, diagnostics, benefits, fulfilment and longitudinal Health Memory",
        "url": "/connected-care/journey",
        "type": "care_journey",
    },
    {
        "keywords": ("video", "videos", "health video", "education", "tutorial", "rehab"),
        "title": "Health Videos",
        "subtitle": "Educational health and exercise video discovery with non-diagnostic boundaries",
        "url": "/videos",
        "type": "health_videos",
    },
    {
        "keywords": ("ai", "assistant", "ask zendoc", "chatgpt", "doctor ai"),
        "title": "ZENDOC AI",
        "subtitle": "Conversation-first educational health guidance and safe next-step support",
        "url": "/ai",
        "type": "ai_assistant",
    },
)

COMMERCE_QUERY_TERMS = (
    "shop", "shopping", "buy", "amazon", "flipkart", "meesho", "blinkit", "zomato",
    "swiggy", "instamart", "yoga mat", "fitness equipment", "health product",
    "wellness product", "bp monitor", "blood pressure monitor", "wearable",
)

COMMUNITY_QUERY_TERMS = (
    "community", "post", "posts", "story", "stories", "feed", "social",
)


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


def _platform_tool_matches(lower):
    matches = []
    for item in PLATFORM_TOOL_CATALOG:
        if any(keyword in lower for keyword in item["keywords"]):
            matches.append({
                key: value for key, value in item.items() if key != "keywords"
            })
    return matches


def _community_matches(user, clean_q, limit=5):
    if not user or not has_app_context() or not any(term in clean_q.lower() for term in COMMUNITY_QUERY_TERMS):
        return []
    try:
        from .db import get_db
        from .health_social import blocked_user_ids, ensure_health_social_schema
        ensure_health_social_schema()
        blocked = blocked_user_ids(user)
        params = [f"%{clean_q.lower()}%"]
        blocked_sql = ""
        if blocked:
            placeholders = ",".join("?" for _ in blocked)
            blocked_sql = f" AND p.author_id NOT IN ({placeholders})"
            params.extend(sorted(int(uid) for uid in blocked))
        params.append(max(1, min(int(limit), 10)))
        rows = get_db().execute(
            f"""
            SELECT p.id,p.body,p.lane,p.created_at,u.name author_name
            FROM health_social_posts p
            JOIN users u ON u.id=p.author_id
            WHERE p.moderation_status='published'
              AND LOWER(p.body) LIKE ?
              {blocked_sql}
            ORDER BY p.created_at DESC,p.id DESC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()
        return [
            {
                "title": f"{row['author_name']} · {str(row['lane']).replace('_', ' ').title()}",
                "subtitle": str(row["body"])[:180],
                "url": f"/community/posts/{row['id']}",
                "type": "community_post",
            }
            for row in rows
        ]
    except Exception:
        return []


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
                    "title": "Medical Transport Request Intake",
                    "subtitle": "Request categories and emergency guidance · no ZENDOC dispatch confirmation",
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
    # Direct service-level callers may use search_all without a Flask app
    # context (for example truth-boundary/unit tests). DB-backed exercise
    # lookup is optional in that case; real web/API requests always have an
    # app context and retain the full exercise search.
    ex_res = list_exercises(q=clean_q, limit=5) if has_app_context() else {"exercises": []}
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

    # 9. Restored product surfaces. These direct links keep major working
    # capabilities discoverable even when their data stores have no matches.
    platform_items = _platform_tool_matches(lower)
    if platform_items:
        results.append({
            "category": "ZENDOC Tools",
            "label": "Platform Features",
            "items": platform_items,
        })

    community_items = _community_matches(user, clean_q)
    if community_items:
        results.append({
            "category": "Health Community",
            "label": "Community Posts",
            "items": community_items,
        })

    if any(term in lower for term in COMMERCE_QUERY_TERMS):
        try:
            from .health_commerce import search_health_products
            commerce = search_health_products(clean_q, "general_wellness")
            merchant_items = [
                {
                    "title": item["label"],
                    "subtitle": "External discovery only · stock and price not verified",
                    "url": f"/health-shop?q={clean_q}&category=general_wellness",
                    "type": "external_merchant_discovery",
                }
                for item in commerce.get("results", [])[:6]
            ]
            if merchant_items:
                results.append({
                    "category": "Health Shop",
                    "label": "External Merchant Discovery",
                    "items": merchant_items,
                })
        except Exception:
            pass

    # 10. AI Health Assistant
    results.append({
        "category": "ZENDOC AI",
        "label": "AI Health Guidance",
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
