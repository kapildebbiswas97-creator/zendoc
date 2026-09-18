from tests.test_milestone1 import make_app

import zendoc.universal_search as global_search


def _external_pharmacy(name="Fulia Medical Store"):
    return {
        "name": name,
        "category": "pharmacy",
        "specialty": "",
        "city": "Fulia",
        "source": "openstreetmap",
        "verification_status": "external_unverified",
        "bookable_in_zendoc": False,
    }


def test_legacy_search_routes_medical_store_fulia_through_canonical_healthcare_parser(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    captured = {}

    def fake_search(query):
        captured["query"] = query
        return {"results": [_external_pharmacy()]}

    monkeypatch.setattr(global_search, "search_healthcare", fake_search)
    with app.app_context():
        result = global_search.search_all(None, "medical store Fulia")

    assert captured["query"] == "medical store Fulia"
    provider_groups = [group for group in result["categories"] if group["category"] == "Healthcare Providers"]
    assert provider_groups
    item = provider_groups[0]["items"][0]
    assert item["title"] == "Fulia Medical Store"
    assert item["url"] == "/universal-search?q=medical store Fulia"
    assert item["verification_status"] == "external_unverified"
    assert item["bookable_in_zendoc"] is False
    assert "External/public discovery" in item["subtitle"]


def test_legacy_search_recognizes_rural_primary_care_and_global_locality_phrases(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    seen = []

    def fake_search(query):
        seen.append(query)
        return {"results": []}

    monkeypatch.setattr(global_search, "search_healthcare", fake_search)
    with app.app_context():
        global_search.search_all(None, "PHC Fulia")
        global_search.search_all(None, "clinic near Nairobi")
        global_search.search_all(None, "chemist Toronto")

    assert seen == ["PHC Fulia", "clinic near Nairobi", "chemist Toronto"]


def test_legacy_search_does_not_promote_external_listing_to_booking(tmp_path, monkeypatch):
    app = make_app(tmp_path)

    monkeypatch.setattr(
        global_search,
        "search_healthcare",
        lambda _query: {"results": [_external_pharmacy("Village Chemist")]},
    )
    with app.app_context():
        result = global_search.search_all(None, "chemist Fulia")

    item = next(group for group in result["categories"] if group["category"] == "Healthcare Providers")["items"][0]
    assert item["source"] == "openstreetmap"
    assert item["bookable_in_zendoc"] is False
