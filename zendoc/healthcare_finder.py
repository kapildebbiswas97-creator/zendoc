import logging
import math

from .places_provider import PlacesResult, ShortLivedCache, configured_places_provider
from .provider_service import search_registered_providers
from .public_data_ingestion import search_public_healthcare_entities


import re

from .geospatial import haversine_km


CATEGORIES = {
    "hospital",
    "clinic",
    "doctor",
    "pharmacy",
    "diagnostic_centre",
    "laboratory",
    "emergency",
    "home_health",
    "mental_health",
    "physiotherapy",
    "ambulance",
    "government_facility",
    "specialist",
}

CATEGORY_ALIASES = {
    "doc": "doctor",
    "physician": "doctor",
    "gp": "doctor",
    "general_physician": "doctor",
    "specialist": "specialist",
    "super_specialist": "specialist",
    "hosp": "hospital",
    "medical_centre": "clinic",
    "medical_center": "clinic",
    "chemist": "pharmacy",
    "drugstore": "pharmacy",
    "meds": "pharmacy",
    "medicine": "pharmacy",
    "diagnostic": "diagnostic_centre",
    "diagnostics": "diagnostic_centre",
    "pathology": "diagnostic_centre",
    "lab": "laboratory",
    "labs": "laboratory",
    "blood_bank": "diagnostic_centre",
    "imaging": "diagnostic_centre",
    "nursing": "home_health",
    "nursing_home": "home_health",
    "home_care": "home_health",
    "elder_care": "home_health",
    "mental": "mental_health",
    "therapy": "mental_health",
    "counseling": "mental_health",
    "counselling": "mental_health",
    "psychology": "mental_health",
    "psychiatry": "mental_health",
    "psychologist": "mental_health",
    "psychiatrist": "mental_health",
    "physio": "physiotherapy",
    "physical_therapy": "physiotherapy",
    "rehab": "physiotherapy",
    "er": "emergency",
    "urgent_care": "emergency",
    "casualty": "emergency",
    "ambulance": "ambulance",
    "medical_transport": "ambulance",
    "transport": "ambulance",
    "gov": "government_facility",
    "govt": "government_facility",
    "government": "government_facility",
    "phc": "government_facility",
    "chc": "government_facility",
    "sub_centre": "government_facility",
    "health_centre": "government_facility",
}

SPECIALTY_NORMALIZATION = {
    "heart": "Cardiology",
    "cardio": "Cardiology",
    "cardiology": "Cardiology",
    "cardiologist": "Cardiology",
    "skin": "Dermatology",
    "derma": "Dermatology",
    "dermatology": "Dermatology",
    "dermatologist": "Dermatology",
    "child": "Pediatrics",
    "children": "Pediatrics",
    "pediatric": "Pediatrics",
    "pediatrics": "Pediatrics",
    "pediatrician": "Pediatrics",
    "paediatrics": "Pediatrics",
    "paediatrician": "Pediatrics",
    "bone": "Orthopedics",
    "bones": "Orthopedics",
    "ortho": "Orthopedics",
    "orthopedic": "Orthopedics",
    "orthopedics": "Orthopedics",
    "orthopaedic": "Orthopedics",
    "orthopaedics": "Orthopedics",
    "brain": "Neurology",
    "neuro": "Neurology",
    "neurology": "Neurology",
    "neurologist": "Neurology",
    "mental": "Psychiatry",
    "psychiatry": "Psychiatry",
    "psychiatrist": "Psychiatry",
    "eye": "Ophthalmology",
    "eyes": "Ophthalmology",
    "ophthalmology": "Ophthalmology",
    "ophthalmologist": "Ophthalmology",
    "ent": "ENT",
    "ear": "ENT",
    "nose": "ENT",
    "throat": "ENT",
    "women": "Gynecology",
    "gynecology": "Gynecology",
    "gynecologist": "Gynecology",
    "gynaecology": "Gynecology",
    "gynaecologist": "Gynecology",
    "obgyn": "Gynecology",
    "general": "General Medicine",
    "general_medicine": "General Medicine",
    "physician": "General Medicine",
}

POSTAL_CODE_PATTERN = re.compile(r"\b([1-9][0-9]{5}|[0-9]{5})\b")
_PLACES_CACHE = ShortLivedCache(ttl_seconds=300)
LOGGER = logging.getLogger(__name__)


def extract_postal_code(text: str | None) -> str | None:
    if not text:
        return None
    match = POSTAL_CODE_PATTERN.search(str(text))
    return match.group(1) if match else None


def normalize_query(category=None, specialty=None, location=None, latitude=None, longitude=None, radius_km=10, postal_code=None, **kwargs):
    raw_cat = (category or "doctor").strip().lower().replace(" ", "_")
    category = CATEGORY_ALIASES.get(raw_cat, raw_cat)
    if category not in CATEGORIES:
        category = "doctor"
    try:
        radius_km = max(1, min(50, int(radius_km or 10)))
    except (TypeError, ValueError, OverflowError):
        radius_km = 10
    lat = parse_coordinate(latitude, -90, 90)
    lng = parse_coordinate(longitude, -180, 180)
    if lat is None or lng is None:
        lat = lng = None
    spec = (specialty or "").strip()
    norm_spec = SPECIALTY_NORMALIZATION.get(spec.lower(), spec)
    loc = (location or "").strip()
    code = (str(postal_code or "").strip() or extract_postal_code(loc))
    return {
        "category": category,
        "specialty": norm_spec,
        "location": loc,
        "postal_code": code,
        "latitude": lat,
        "longitude": lng,
        "radius_km": radius_km,
    }


def parse_coordinate(value, minimum, maximum):
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < minimum or number > maximum:
        return None
    return number


class HealthcareFinder:
    def __init__(self, places_provider=None):
        self.places_provider = places_provider or configured_places_provider()

    def search(self, query):
        normalized = normalize_query(**query)
        invalid_gps_only = (
            not normalized["location"]
            and normalized["latitude"] is None
            and any(query.get(key) not in (None, "") for key in ("latitude", "longitude"))
        )
        warnings = []

        registered = []
        registered_source_available = not invalid_gps_only
        if not invalid_gps_only:
            try:
                registered = search_registered_providers(
                    category="doctor" if normalized["category"] in {"doctor", "clinic"} else normalized["category"],
                    specialty=normalized["specialty"],
                    location=normalized["location"],
                    latitude=normalized["latitude"],
                    longitude=normalized["longitude"],
                    radius_km=normalized["radius_km"],
                )
            except Exception:
                registered_source_available = False
                LOGGER.exception("Registered-provider Finder source failed.")
                warnings.append(
                    "ZENDOC registered-provider search is temporarily unavailable. "
                    "Other available healthcare sources are still shown."
                )

        public_directory = []
        public_directory_source_available = not invalid_gps_only
        if not invalid_gps_only:
            try:
                public_directory = search_public_healthcare_entities(
                    category=normalized["category"],
                    specialty=normalized["specialty"],
                    location=normalized["location"],
                    limit=25,
                    latitude=normalized["latitude"],
                    longitude=normalized["longitude"],
                    radius_km=normalized["radius_km"],
                )
            except Exception:
                public_directory_source_available = False
                LOGGER.exception("Official public-directory Finder source failed.")
                warnings.append(
                    "The official/public healthcare directory is temporarily unavailable. "
                    "Other available healthcare sources are still shown."
                )

        registered, public_directory, claimed_links = merge_registered_with_approved_public_claims(
            registered,
            public_directory,
        )

        places_cache_key = (
            getattr(self.places_provider, "source", self.places_provider.__class__.__name__),
            tuple(sorted(normalized.items())),
        )
        places_result = _PLACES_CACHE.get(places_cache_key)
        if places_result is None:
            try:
                places_result = self.places_provider.search(normalized)
            except Exception:
                LOGGER.exception("External places Finder source failed.")
                places_result = PlacesResult(
                    available=False,
                    results=[],
                    message=(
                        "External healthcare map search is temporarily unavailable. "
                        "ZENDOC did not fabricate replacement listings."
                    ),
                    source=getattr(self.places_provider, "source", "external"),
                )
            if places_result.available:
                _PLACES_CACHE.set(places_cache_key, places_result)

        external_results = [
            dict(item)
            for item in (places_result.results or [])
            if isinstance(item, dict)
        ]
        if not places_result.available:
            warnings.append(
                str(places_result.message or "").strip()
                or "An external healthcare map source is temporarily unavailable."
            )

        ordered_registered, ordered_public, ordered_external, results = deduplicate_and_rank_results(
            registered,
            public_directory,
            external_results,
            user_lat=normalized["latitude"],
            user_lng=normalized["longitude"],
        )

        warnings = list(dict.fromkeys(
            warning.strip()
            for warning in warnings
            if str(warning or "").strip()
        ))
        search_status = "partial" if warnings and results else "degraded" if warnings else "complete"

        zero_result_context = None
        if not results:
            zero_result_context = {
                "sources_checked": [
                    {
                        "source": "ZENDOC Verified Providers",
                        "status": "AVAILABLE" if registered_source_available else "FAILED",
                        "results_found": len(registered),
                    },
                    {
                        "source": "Official Public Directory",
                        "status": "AVAILABLE" if public_directory_source_available else "FAILED",
                        "results_found": len(public_directory),
                    },
                    {
                        "source": "External Healthcare Maps",
                        "status": "AVAILABLE" if places_result.available else "FAILED",
                        "results_found": len(external_results),
                        "provider": getattr(places_result, "source", "external"),
                    },
                ],
                "what_failed": [w for w in warnings if "unavailable" in w.lower()],
                "what_returned_zero": [
                    s["source"] for s in [
                        {"source": "ZENDOC Verified Providers", "count": len(registered)},
                        {"source": "Official Public Directory", "count": len(public_directory)},
                        {"source": "External Healthcare Maps", "count": len(external_results)},
                    ] if s["count"] == 0
                ],
                "location_understood": {
                    "location_query": normalized["location"] or None,
                    "postal_code": normalized.get("postal_code"),
                    "coordinates": {"lat": normalized["latitude"], "lng": normalized["longitude"]} if normalized["latitude"] is not None else None,
                    "radius_km": normalized["radius_km"],
                },
                "expansion_suggestions": [
                    {
                        "action": "expand_radius",
                        "label": f"Expand search radius to {min(50, normalized['radius_km'] * 2)} km",
                        "radius_km": min(50, normalized["radius_km"] * 2),
                    },
                    {
                        "action": "broaden_category",
                        "label": "Search all healthcare facilities in this area",
                        "category": "hospital",
                    },
                ] + ([{
                    "action": "clear_specialty",
                    "label": f"Search '{normalized['category']}' without specialty filter",
                    "specialty": "",
                }] if normalized["specialty"] else []),
            }

        response = {
            "query": normalized,
            "registered_providers": ordered_registered,
            "official_public_directory": ordered_public,
            "claimed_public_directory_links": claimed_links,
            "external_places": {
                **places_result.to_dict(),
                "results": ordered_external,
            },
            "results": results,
            "source_tiers": {
                "zendoc_verified": len(ordered_registered),
                "official_public_directory_not_zendoc_verified": len(ordered_public),
                "approved_public_listings_merged_into_verified": len(claimed_links),
                "external_unverified": len(ordered_external),
            },
            "source_health": {
                "zendoc_verified": {
                    "available": bool(registered_source_available),
                    "result_count": len(registered),
                },
                "official_public_directory": {
                    "available": bool(public_directory_source_available),
                    "result_count": len(public_directory),
                },
                "external_places": {
                    "available": bool(places_result.available),
                    "result_count": len(external_results),
                    "source": str(places_result.source or "external"),
                    "message": str(places_result.message or "").strip() or None,
                },
            },
            "zero_result_context": zero_result_context,
            "search_status": search_status,
            "warnings": warnings,
            "message": None,
        }
        if not response["results"]:
            response["message"] = (
                warnings[0]
                if warnings
                else places_result.message
                or "No healthcare providers were found for this search."
            )
        if invalid_gps_only:
            response["search_status"] = "degraded"
            response["message"] = (
                "Enter a city, area, or PIN code, or allow a valid current location to search nearby care."
            )
            response["warnings"] = [response["message"]]
        return response


def merge_registered_with_approved_public_claims(registered, public_directory):
    """Merge only explicit owner-approved public listing links into verified providers."""
    registered_by_profile = {
        int(item["id"]): dict(item)
        for item in registered
        if item.get("id") is not None
    }
    remaining_public = []
    claimed_links = []

    for public in public_directory:
        profile_id = public.get("approved_provider_profile_id")
        if profile_id is None or public.get("claim_link_conflict"):
            remaining_public.append(public)
            continue

        try:
            profile_id = int(profile_id)
        except (TypeError, ValueError):
            remaining_public.append(public)
            continue

        provider = registered_by_profile.get(profile_id)
        if provider is None:
            # Approved claim alone does not verify/promote a provider.
            remaining_public.append(public)
            continue

        provenance = list(provider.get("public_directory_provenance") or [])
        provenance.extend(public.get("provenance_sources") or [])
        provider["public_directory_provenance"] = provenance
        provider["public_listing_claim_linked"] = True
        approved_entity_ids = [
            int(value)
            for value in public.get("approved_public_entity_ids", [])
        ]
        provider["approved_public_listing_ids"] = sorted(set(
            list(provider.get("approved_public_listing_ids") or []) + approved_entity_ids
        ))
        provider["approved_public_claim_ids"] = sorted(set(
            list(provider.get("approved_public_claim_ids") or []) +
            [int(value) for value in public.get("approved_claim_ids", [])]
        ))
        provider["truth_notice"] = (
            "ZENDOC-verified provider profile with owner-approved public-directory linkage. "
            "The public claim preserves provenance but does not itself create verification or live availability."
        )
        registered_by_profile[profile_id] = provider
        claimed_links.append({
            "provider_profile_id": profile_id,
            "public_entity_id": approved_entity_ids[0] if len(approved_entity_ids) == 1 else None,
            "approved_public_entity_ids": approved_entity_ids,
            "public_entity_name": public.get("name"),
            "provenance_sources": list(public.get("provenance_sources") or []),
            "approved_claim_ids": list(public.get("approved_claim_ids") or []),
        })

    ordered_registered = []
    for item in registered:
        profile_id = int(item["id"]) if item.get("id") is not None else None
        ordered_registered.append(registered_by_profile.get(profile_id, item))

    return ordered_registered, remaining_public, claimed_links


def _normalize_entity_name(name: str | None) -> str:
    if not name:
        return ""
    cleaned = str(name).lower().strip()
    for prefix in ("dr.", "dr ", "doctor ", "hospital ", "clinic ", "pharmacy ", "centre ", "center ", "the "):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
    return re.sub(r"[^a-z0-9]", "", cleaned)


def deduplicate_and_rank_results(registered, public_directory, external_results, user_lat=None, user_lng=None):
    """
    Ranks results truthfully:
    1. ZENDOC Verified Providers
    2. Official Public Directory records
    3. External Map listings (unverified)
    Cross-source duplicates are linked and deduplicated so patients do not see duplicate cards.
    Truthful Haversine distance is calculated for items with coordinates.
    """
    seen_entity_keys = {}
    ordered_registered = []
    for reg in registered:
        item = dict(reg)
        if user_lat is not None and user_lng is not None and item.get("latitude") is not None and item.get("longitude") is not None:
            if item.get("distance_km") is None:
                dist = haversine_km(user_lat, user_lng, item["latitude"], item["longitude"])
                if dist is not None:
                    item["distance_km"] = round(dist, 1)
        item["verification_tier"] = "ZENDOC_VERIFIED"
        item["availability_truth"] = "LIVE_BOOKING"
        name_key = _normalize_entity_name(item.get("name"))
        provider_name_key = _normalize_entity_name(item.get("provider_name"))
        city_key = str(item.get("city") or "").lower().strip()
        if name_key:
            seen_entity_keys[(name_key, city_key)] = item
            if not city_key:
                seen_entity_keys[(name_key, "")] = item
        if provider_name_key:
            seen_entity_keys[(provider_name_key, city_key)] = item
            if not city_key:
                seen_entity_keys[(provider_name_key, "")] = item
        ordered_registered.append(item)

    ordered_public = []
    for pub in public_directory:
        item = dict(pub)
        if user_lat is not None and user_lng is not None and item.get("latitude") is not None and item.get("longitude") is not None:
            if item.get("distance_km") is None:
                dist = haversine_km(user_lat, user_lng, item["latitude"], item["longitude"])
                if dist is not None:
                    item["distance_km"] = round(dist, 1)
        item["verification_tier"] = "OFFICIAL_PUBLIC_DIRECTORY"
        item["availability_truth"] = "REQUEST_INTAKE_ONLY"
        name_key = _normalize_entity_name(item.get("name"))
        provider_name_key = _normalize_entity_name(item.get("provider_name"))
        city_key = str(item.get("city") or "").lower().strip()
        matched_reg = seen_entity_keys.get((name_key, city_key)) or (seen_entity_keys.get((provider_name_key, city_key)) if provider_name_key else None)
        if matched_reg:
            matched_reg["public_directory_match"] = True
        if name_key:
            seen_entity_keys[(name_key, city_key)] = item
            if not city_key:
                seen_entity_keys[(name_key, "")] = item
        if provider_name_key:
            seen_entity_keys[(provider_name_key, city_key)] = item
            if not city_key:
                seen_entity_keys[(provider_name_key, "")] = item
        ordered_public.append(item)

    ordered_external = []
    for ext in external_results:
        item = dict(ext)
        if user_lat is not None and user_lng is not None and item.get("latitude") is not None and item.get("longitude") is not None:
            if item.get("distance_km") is None:
                dist = haversine_km(user_lat, user_lng, item["latitude"], item["longitude"])
                if dist is not None:
                    item["distance_km"] = round(dist, 1)
        item["verification_tier"] = "EXTERNAL_UNVERIFIED"
        item["availability_truth"] = "UNVERIFIED_LISTING"
        name_key = _normalize_entity_name(item.get("name") or item.get("displayName"))
        city_key = str(item.get("city") or "").lower().strip()
        matched_item = (
            seen_entity_keys.get((name_key, city_key))
            or (seen_entity_keys.get((name_key, "")) if not city_key else None)
        )
        if not matched_item and item.get("latitude") is not None and item.get("longitude") is not None:
            # Check coordinate proximity (< 0.1km) and name similarity
            for (seen_name, _), candidate in seen_entity_keys.items():
                if seen_name and (seen_name in name_key or name_key in seen_name):
                    c_lat = candidate.get("latitude")
                    c_lng = candidate.get("longitude")
                    if c_lat is not None and c_lng is not None:
                        if haversine_km(item["latitude"], item["longitude"], c_lat, c_lng) < 0.1:
                            matched_item = candidate
                            break

        if matched_item:
            matched_item["external_map_match"] = True
            continue
        ordered_external.append(item)

    def _dist_sort_key(record):
        d = record.get("distance_km")
        return (0 if d is not None else 1, d if d is not None else 999999.0)

    if user_lat is not None and user_lng is not None:
        ordered_registered.sort(key=_dist_sort_key)
        ordered_public.sort(key=_dist_sort_key)
        ordered_external.sort(key=_dist_sort_key)

    all_results = ordered_registered + ordered_public + ordered_external
    return ordered_registered, ordered_public, ordered_external, all_results



