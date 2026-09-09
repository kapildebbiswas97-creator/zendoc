from .places_provider import ShortLivedCache, configured_places_provider
from .provider_service import search_registered_providers
from .public_data_ingestion import search_public_healthcare_entities


CATEGORIES = {"hospital", "clinic", "doctor", "pharmacy", "diagnostic_centre", "laboratory", "emergency"}
_PLACES_CACHE = ShortLivedCache(ttl_seconds=300)


def normalize_query(category=None, specialty=None, location=None, latitude=None, longitude=None, radius_km=10):
    category = (category or "doctor").strip().lower().replace(" ", "_")
    if category not in CATEGORIES:
        category = "doctor"
    try:
        radius_km = max(1, min(50, int(radius_km or 10)))
    except (TypeError, ValueError):
        radius_km = 10
    lat = parse_coordinate(latitude, -90, 90)
    lng = parse_coordinate(longitude, -180, 180)
    return {
        "category": category,
        "specialty": (specialty or "").strip(),
        "location": (location or "").strip(),
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
    if number < minimum or number > maximum:
        return None
    return number


class HealthcareFinder:
    def __init__(self, places_provider=None):
        self.places_provider = places_provider or configured_places_provider()

    def search(self, query):
        normalized = normalize_query(**query)

        registered = search_registered_providers(
            category="doctor" if normalized["category"] in {"doctor", "clinic"} else normalized["category"],
            specialty=normalized["specialty"],
            location=normalized["location"],
        )
        public_directory = search_public_healthcare_entities(
            category=normalized["category"],
            specialty=normalized["specialty"],
            location=normalized["location"],
            limit=25,
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
            places_result = self.places_provider.search(normalized)
            # Keep successful/empty searches briefly for rate protection, but
            # never cache an external outage. This allows a later request to
            # recover when Google/Nominatim comes back.
            if places_result.available:
                _PLACES_CACHE.set(places_cache_key, places_result)

        response = {
            "query": normalized,
            "registered_providers": registered,
            "official_public_directory": public_directory,
            "claimed_public_directory_links": claimed_links,
            "external_places": places_result.to_dict(),
            "results": registered + public_directory + places_result.results,
            "source_tiers": {
                "zendoc_verified": len(registered),
                "official_public_directory_not_zendoc_verified": len(public_directory),
                "approved_public_listings_merged_into_verified": len(claimed_links),
                "external_unverified": len(places_result.results),
            },
            "message": None,
        }
        if not response["results"]:
            response["message"] = places_result.message or "No healthcare providers were found for this search."
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

