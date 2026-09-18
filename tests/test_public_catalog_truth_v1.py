from zendoc.marketplace import get_marketplace_catalog
from zendoc.universal_search import search_all


def _item(catalog, item_id):
    return next(item for item in catalog if item["id"] == item_id)


def test_marketplace_does_not_overclaim_iot_pharmacy_or_home_health():
    catalog = get_marketplace_catalog()

    iot = _item(catalog, "iot_hub")
    assert iot["badge"] == "Registration Only"
    assert "Integration Required" in iot["description"]
    assert "trusted device evidence" in iot["description"]

    pharmacy = _item(catalog, "pharmacy")
    assert "Stock" in pharmacy["description"]
    assert "require pharmacy confirmation" in pharmacy["description"]

    home = _item(catalog, "home_health")
    assert home["badge"] == "Request Workflow"
    assert "provider assignment and acceptance" in home["description"]


def test_marketplace_ai_and_records_use_bounded_truthful_language():
    catalog = get_marketplace_catalog()
    ai = _item(catalog, "ai_assistant")
    records = _item(catalog, "health_records")

    assert "non-diagnostic" in ai["description"]
    assert "symptom evaluation" not in ai["description"].lower()
    assert "automated structured extraction" not in records["description"].lower()
    assert "unavailable" in records["description"].lower()


def test_universal_search_transport_and_ai_labels_are_not_fulfilment_claims():
    transport = search_all(None, "ambulance")
    body = str(transport)
    assert "no ZENDOC dispatch confirmation" in body
    assert "Request Medical Transport / Ambulance" not in body

    ai = search_all(None, "headache")
    ai_items = [
        item
        for category in ai["categories"]
        if category["category"] == "ZENDOC AI"
        for item in category["items"]
    ]
    assert ai_items
    assert any(category["label"] == "AI Health Guidance" for category in ai["categories"] if category["category"] == "ZENDOC AI")
