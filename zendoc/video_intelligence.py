from .db import get_db, now_iso
from .video_provider import search_fitness_video
from .video_guidance import build_video_guidance


VIDEO_CATEGORIES = (
    "exercise",
    "fitness",
    "nutrition",
    "patient_education",
    "device_setup",
    "rehabilitation",
    "platform_help",
    "staff_training",
)


def _value(user, key, default=None):
    if user is None:
        return default
    if hasattr(user, "keys") and key in user.keys():
        return user[key]
    return user.get(key, default) if isinstance(user, dict) else default


def find_educational_video(actor, query, category="fitness", max_results=5):
    clean_query = str(query or "").strip()
    if not clean_query:
        raise ValueError("Video search query is required.")
    category = str(category or "fitness").strip().lower()
    if category not in VIDEO_CATEGORIES:
        category = "fitness"
    result = search_fitness_video(f"{clean_query} {category}", max_results=max_results)
    provider = result.get("provider") or "none"
    rows = []
    for item in result.get("results", []):
        enriched = dict(item)
        enriched["category"] = category
        enriched["why_recommended"] = (
            "Matched your ZENDOC request and category. This is educational content only and does not replace professional care."
        )
        enriched["guidance"] = build_video_guidance(clean_query, category, enriched)
        rows.append(enriched)
    result["results"] = rows
    result["category"] = category
    result["guidance"] = build_video_guidance(clean_query, category)
    get_db().execute(
        """
        INSERT INTO video_search_history (user_id, query, category, provider, available, result_count, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (_value(actor, "id"), clean_query[:300], category, provider, 1 if result.get("available") else 0, len(rows), now_iso()),
    )
    get_db().commit()
    return result
