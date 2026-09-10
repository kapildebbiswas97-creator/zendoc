import hashlib
import io
import json
import zipfile

import pytest

from tests.test_milestone1 import make_app
from zendoc.data_acquisition import (
    AcquisitionError,
    acquire_source_bytes,
    inspect_bytes,
)
from zendoc.healthcare_finder import HealthcareFinder
from zendoc.nadia_pilot import nadia_data_quality_gate, nadia_source_plan
from zendoc.public_data_ingestion import ingest_public_records


def _kwargs(**overrides):
    values = {
        "storage_root": overrides.pop("storage_root"),
        "usage_basis": "official_public_download",
        "license_or_terms": "Published official public terms for pilot testing.",
        "dataset_version": "2026-09-11",
        "retrieved_at": "2026-09-11T00:30:00+05:30",
        "file_name": "nadia-hospitals.csv",
    }
    values.update(overrides)
    return values


def test_acquisition_is_content_addressed_and_returns_snapshot_manifest(tmp_path):
    payload = b"source_record_id,category,name\nN-1,hospital,Nadia Hospital\n"
    result = acquire_source_bytes(
        "data_gov_hospitals",
        "https://www.data.gov.in/resource/hospitals?b=2&a=1",
        payload,
        **_kwargs(storage_root=tmp_path),
    )

    assert result["acquisition_status"] == "ACQUIRED"
    assert result["file_sha256"] == hashlib.sha256(payload).hexdigest()
    assert result["source_url"].endswith("?a=1&b=2")
    assert result["dataset_snapshot"]["snapshot_uid"] == result["snapshot_uid"]
    assert result["storage_ref"].startswith("raw/data_gov_hospitals/")
    assert (tmp_path / result["storage_ref"]).read_bytes() == payload

    repeated = acquire_source_bytes(
        "data_gov_hospitals",
        "https://www.data.gov.in/resource/hospitals?a=1&b=2",
        payload,
        **_kwargs(storage_root=tmp_path),
    )
    assert repeated["acquisition_status"] == "ALREADY_PRESENT"
    assert repeated["snapshot_uid"] == result["snapshot_uid"]


def test_acquisition_rejects_secrets_paths_and_oversized_payloads(tmp_path):
    with pytest.raises(AcquisitionError, match="API keys|credentials"):
        acquire_source_bytes(
            "data_gov_hospitals",
            "https://www.data.gov.in/resource/hospitals?api_key=secret",
            b"x",
            **_kwargs(storage_root=tmp_path),
        )
    with pytest.raises(AcquisitionError, match="base filename"):
        acquire_source_bytes(
            "data_gov_hospitals",
            "https://www.data.gov.in/resource/hospitals",
            b"x",
            **_kwargs(storage_root=tmp_path, file_name="../hospitals.csv"),
        )
    with pytest.raises(AcquisitionError, match="safe .* byte limit"):
        acquire_source_bytes(
            "data_gov_hospitals",
            "https://www.data.gov.in/resource/hospitals",
            b"12345",
            **_kwargs(storage_root=tmp_path, max_bytes=4),
        )


def test_schema_inspection_supports_csv_json_and_xlsx_without_row_values():
    csv_result = inspect_bytes(b"name,category\nNadia Hospital,hospital\n", file_name="hospitals.csv")
    assert csv_result == {
        "file_format": "csv",
        "schema_status": "VALID",
        "columns": ["name", "category"],
        "row_count": 1,
    }

    json_result = inspect_bytes(
        json.dumps({"data": [{"name": "Nadia Hospital", "district": "Nadia"}]}).encode(),
        file_name="hospitals.json",
    )
    assert json_result["columns"] == ["district", "name"]
    assert json_result["row_count"] == 1
    assert "Nadia Hospital" not in json.dumps(json_result)

    xlsx = io.BytesIO()
    with zipfile.ZipFile(xlsx, "w") as archive:
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            (
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
                '<row r="1"><c r="A1" t="inlineStr"><is><t>name</t></is></c>'
                '<c r="B1" t="inlineStr"><is><t>district</t></is></c></row>'
                '<row r="2"><c r="A2" t="inlineStr"><is><t>Nadia Hospital</t></is></c></row>'
                '</sheetData></worksheet>'
            ),
        )
    xlsx_result = inspect_bytes(xlsx.getvalue(), file_name="hospitals.xlsx")
    assert xlsx_result["schema_status"] == "VALID"
    assert xlsx_result["columns"] == ["name", "district"]
    assert xlsx_result["row_count"] == 1
    assert "Nadia Hospital" not in json.dumps(xlsx_result)


def test_zip_inspection_lists_supported_members_and_rejects_traversal():
    safe = io.BytesIO()
    with zipfile.ZipFile(safe, "w") as archive:
        archive.writestr("nadia/hospitals.csv", "name\nNadia Hospital\n")
        archive.writestr("README.txt", "metadata")
    result = inspect_bytes(safe.getvalue(), file_name="nadia-data.zip")
    assert result["supported_members"] == ["nadia/hospitals.csv"]

    unsafe = io.BytesIO()
    with zipfile.ZipFile(unsafe, "w") as archive:
        archive.writestr("../private.csv", "secret")
    with pytest.raises(AcquisitionError, match="unsafe member path"):
        inspect_bytes(unsafe.getvalue(), file_name="nadia-data.zip")


def test_nadia_plan_is_explicit_and_quality_gate_does_not_fake_green():
    plan = {item["source_id"]: item for item in nadia_source_plan()}
    assert plan["lgd"]["classification"] == "DOWNLOADABLE_SNAPSHOT"
    assert plan["swasthya_sathi_hospitals"]["classification"] == "PUBLIC_LOOKUP_ONLY"
    assert all(item["status"] in {"NOT_ACQUIRED", "LOOKUP_ONLY"} for item in plan.values())

    blocked = nadia_data_quality_gate({"source_valid": True, "snapshot_uid": "snapshot_x"})
    assert blocked["status"] == "BLOCKED"
    assert "POSTGRESQL_TESTS" in blocked["failed_checks"]


def test_acquired_nadia_public_record_is_consumed_by_finder_as_unverified(tmp_path):
    app = make_app(tmp_path)

    class EmptyPlaces:
        source = "test-map"

        def search(self, _query):
            from zendoc.places_provider import PlacesResult

            return PlacesResult(available=True, results=[], source=self.source)

    with app.app_context():
        actor = {"id": 1, "role": "admin", "email": "admin@example.com", "active": 1}
        ingest_public_records(
            actor,
            source_id="data_gov_hospitals",
            ingestion_type="public_healthcare_entities",
            records=[
                {
                    "source_record_id": "NADIA-H-001",
                    "category": "hospital",
                    "name": "Nadia Pilot Hospital",
                    "district": "Nadia",
                    "state": "West Bengal",
                }
            ],
            dry_run=False,
        )
        result = HealthcareFinder(places_provider=EmptyPlaces()).search(
            {"category": "hospital", "location": "Nadia", "specialty": "", "latitude": None, "longitude": None}
        )
        assert len(result["official_public_directory"]) == 1
        item = result["official_public_directory"][0]
        assert item["source_id"] == "data_gov_hospitals"
        assert item["verification_status"] == "not_verified"
        assert item["bookable_in_zendoc"] is False

