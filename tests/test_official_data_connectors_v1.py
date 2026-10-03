import json
from urllib.parse import parse_qs, urlparse

import pytest

from zendoc import official_data_connectors as connectors


class _FakeResponse:
    def __init__(self, payload):
        self._raw = json.dumps(payload).encode("utf-8")
        self.status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _size=-1):
        return self._raw


def test_ogd_connector_requires_server_side_api_key(monkeypatch):
    monkeypatch.delenv("ZENDOC_DATA_GOV_IN_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ZENDOC_DATA_GOV_IN_API_KEY"):
        connectors.fetch_data_gov_hospitals()


def test_normalize_ogd_hospital_preserves_public_provenance_fields():
    record = {
        "sr_no": "42",
        "hospital_name": "Example District Hospital",
        "hospital_category": "Public",
        "hospital_care_type": "Secondary",
        "address_original_first_line": "Main Road",
        "town": "Kalyani",
        "district": "Nadia",
        "state": "West Bengal",
        "pincode": "741235",
        "location_coordinates": "22.975,88.434",
        "telephone": "03300000000",
        "hospital_primary_email_id": "public@example.gov.in",
        "website": "https://example.gov.in",
        "facilities": "Emergency",
        "emergency_services": "Yes",
    }

    item = connectors.normalize_data_gov_hospital(record)

    assert item["source_record_id"] == "42"
    assert item["name"] == "Example District Hospital"
    assert item["category"] == "hospital"
    assert item["district"] == "Nadia"
    assert item["state"] == "West Bengal"
    assert item["latitude"] == pytest.approx(22.975)
    assert item["longitude"] == pytest.approx(88.434)
    assert item["public_phone"] == "03300000000"
    assert item["metadata"]["resource_id"] == connectors.DATA_GOV_HOSPITAL_RESOURCE_ID
    assert item["metadata"]["emergency_services"] == "Yes"


def test_normalize_ogd_hospital_rejects_missing_name_and_bad_coordinates():
    assert connectors.normalize_data_gov_hospital({"sr_no": "1"}) is None

    item = connectors.normalize_data_gov_hospital(
        {
            "sr_no": "2",
            "hospital_name": "Coordinates Unknown Hospital",
            "location_coordinates": "999,999",
        }
    )
    assert item["latitude"] is None
    assert item["longitude"] is None


def test_fetch_ogd_hospitals_is_bounded_and_does_not_return_api_key(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        return _FakeResponse(
            {
                "total": 123,
                "records": [
                    {
                        "sr_no": "7",
                        "hospital_name": "Public Hospital",
                        "state": "West Bengal",
                        "district": "Nadia",
                        "telephone": "0",
                        "location_coordinates": "23.0,88.5",
                    }
                ],
            }
        )

    monkeypatch.setattr(connectors.urllib.request, "urlopen", fake_urlopen)

    result = connectors.fetch_data_gov_hospitals(
        api_key="super-secret-test-key",
        state="West Bengal",
        district="Nadia",
        limit=9999,
        offset=-10,
        timeout_seconds=99,
    )

    parsed = urlparse(captured["url"])
    query = parse_qs(parsed.query)
    assert parsed.path.endswith(connectors.DATA_GOV_HOSPITAL_RESOURCE_ID)
    assert query["api-key"] == ["super-secret-test-key"]
    assert query["filters[state]"] == ["West Bengal"]
    assert query["filters[district]"] == ["Nadia"]
    assert query["limit"] == ["500"]
    assert query["offset"] == ["0"]
    assert captured["timeout"] == 30
    assert result["upstream_total"] == 123
    assert result["record_count"] == 1
    assert result["records"][0]["public_phone"] is None
    assert "super-secret-test-key" not in repr(result)


def test_ingest_ogd_hospitals_delegates_to_reviewed_pipeline(monkeypatch):
    monkeypatch.setattr(
        connectors,
        "fetch_data_gov_hospitals",
        lambda **_kwargs: {
            "source_id": connectors.DATA_GOV_HOSPITAL_SOURCE_ID,
            "resource_id": connectors.DATA_GOV_HOSPITAL_RESOURCE_ID,
            "records": [{"source_record_id": "1", "name": "Example", "category": "hospital"}],
            "record_count": 1,
            "upstream_count": 1,
            "upstream_total": 1,
            "offset": 0,
            "limit": 100,
            "filters": {"state": None, "district": None},
            "truth_notice": "official public data",
        },
    )
    captured = {}

    def fake_ingest(actor, **kwargs):
        captured["actor"] = actor
        captured.update(kwargs)
        return {"dry_run": kwargs["dry_run"], "accepted": 1}

    monkeypatch.setattr(connectors, "ingest_public_records", fake_ingest)
    actor = {"id": 1, "role": "admin"}

    result = connectors.ingest_data_gov_hospitals(actor)

    assert captured["actor"] is actor
    assert captured["source_id"] == "data_gov_hospitals"
    assert captured["ingestion_type"] == "public_healthcare_entities"
    assert captured["dry_run"] is True
    assert result["ingestion"]["accepted"] == 1
    assert "records" not in result["fetch"]
