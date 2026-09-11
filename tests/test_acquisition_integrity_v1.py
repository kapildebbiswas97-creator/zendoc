import csv
import io
import json
from pathlib import Path
import sys
import zipfile

import pytest

from tests.test_milestone1 import make_app
from zendoc import data_acquisition
from zendoc.data_acquisition import AcquisitionError, acquire_source_bytes, acquire_source_file, inspect_artifact, inspect_bytes
from zendoc.dataset_snapshot_ingestion import ingest_public_snapshot, normalize_dataset_snapshot
from zendoc.db import get_db
from zendoc.healthcare_finder import HealthcareFinder


def owner_actor():
    return {"id": 1, "role": "admin", "email": "admin@example.com", "active": 1}


def test_acquired_manifest_round_trips_through_exact_preview_and_apply(tmp_path):
    app = make_app(tmp_path)
    payload = b"source_record_id,category,name,district,state\nNADIA-001,hospital,Nadia Pilot Hospital,Nadia,West Bengal\n"

    with app.app_context():
        acquired = acquire_source_bytes(
            "data_gov_hospitals",
            "https://www.data.gov.in/resource/hospitals?b=2&a=1",
            payload,
            storage_root=tmp_path / "raw",
            usage_basis="official_public_download",
            license_or_terms="Official public terms retained for this controlled test snapshot.",
            license_url="https://www.data.gov.in/terms-of-use",
            dataset_version="2026-09-11",
            retrieved_at="2026-09-11T00:30:00+05:30",
            file_name="nadia-hospitals.csv",
        )
        manifest = acquired["dataset_snapshot"]
        normalized = normalize_dataset_snapshot("data_gov_hospitals", manifest)
        assert normalized["snapshot_uid"] == acquired["snapshot_uid"]
        assert normalized["manifest_sha256"] == acquired["manifest_sha256"]
        assert normalized["source_url"].endswith("?a=1&b=2")

        records = list(csv.DictReader(io.StringIO(Path(acquired["stored_path"]).read_text(encoding="utf-8"))))
        preview = ingest_public_snapshot(
            owner_actor(),
            source_id="data_gov_hospitals",
            ingestion_type="public_healthcare_entities",
            records=records,
            dataset_snapshot=manifest,
            dry_run=True,
        )
        assert preview["summary"]["dataset_snapshot"]["snapshot_uid"] == acquired["snapshot_uid"]

        applied = ingest_public_snapshot(
            owner_actor(),
            source_id="data_gov_hospitals",
            ingestion_type="public_healthcare_entities",
            records=records,
            dataset_snapshot=manifest,
            dry_run=False,
            preview_batch_uid=preview["batch_uid"],
        )
        assert applied["summary"]["dataset_snapshot"]["manifest_sha256"] == acquired["manifest_sha256"]
        row = get_db().execute(
            "SELECT metadata_json,zendoc_verification_status,booking_connectivity "
            "FROM public_healthcare_entities WHERE source_id=? AND source_record_id=?",
            ("data_gov_hospitals", "NADIA-001"),
        ).fetchone()
        metadata = json.loads(row["metadata_json"])
        assert metadata["_zendoc_source_snapshot"]["snapshot_uid"] == acquired["snapshot_uid"]
        assert row["zendoc_verification_status"] == "not_verified"
        assert row["booking_connectivity"] == "not_connected"

        class EmptyPlaces:
            def search(self, _query):
                from zendoc.places_provider import PlacesResult

                return PlacesResult(available=True, results=[], source="test-map")

        result = HealthcareFinder(places_provider=EmptyPlaces()).search(
            {"category": "hospital", "location": "Nadia", "specialty": "", "latitude": None, "longitude": None}
        )
        item = result["official_public_directory"][0]
        assert item["name"] == records[0]["name"]
        assert item["verification_status"] == "not_verified"
        assert item["bookable_in_zendoc"] is False


def test_local_file_acquisition_rejects_oversized_reads_and_windows_unsafe_names(tmp_path):
    source = tmp_path / "source.csv"
    source.write_bytes(b"12345")
    with pytest.raises(AcquisitionError, match="safe 4 byte limit"):
        acquire_source_file(
            "data_gov_hospitals",
            "https://www.data.gov.in/resource/hospitals",
            source,
            storage_root=tmp_path / "raw",
            usage_basis="manual_public_snapshot",
            license_or_terms="Manual public snapshot for safety testing.",
            dataset_version="test-1",
            max_bytes=4,
        )

    for file_name in ("CON.csv", "report.csv:secret", "report.csv.", "report.csv "):
        with pytest.raises(AcquisitionError, match="base filename"):
            acquire_source_bytes(
                "data_gov_hospitals",
                "https://www.data.gov.in/resource/hospitals",
                b"x",
                storage_root=tmp_path / "raw",
                usage_basis="manual_public_snapshot",
                license_or_terms="Manual public snapshot for safety testing.",
                dataset_version="test-1",
                file_name=file_name,
            )


def _acquire(tmp_path, **overrides):
    options = {
        "source_id": "data_gov_hospitals",
        "source_url": "https://www.data.gov.in/resource/hospitals",
        "content": b"name\nSynthetic test row\n",
        "storage_root": tmp_path / "stored",
        "usage_basis": "manual_public_snapshot",
        "license_or_terms": "Permitted synthetic test fixture.",
        "dataset_version": "test-1",
        "file_name": "fixture.csv",
    }
    options.update(overrides)
    return acquire_source_bytes(**options)


@pytest.mark.parametrize("file_name", [
    "C:fixture.csv", "fixture.csv:stream", "fixture.csv.", "fixture.csv ",
    "CON.csv", "con.extra.csv", "CON .csv", "LPT1.csv", "COM¹.csv", "NUL.csv",
    "fixture?.csv", "fixture*.csv", 'fixture".csv', "fixture|.csv", "fixture<.csv",
    "fixture>.csv", "fixture\x1f.csv", "fixture\x7f.csv", "../fixture.csv", "folder\\fixture.csv",
])
def test_acquisition_rejects_cross_platform_unsafe_names_before_storage(tmp_path, file_name):
    with pytest.raises(AcquisitionError, match="base filename"):
        _acquire(tmp_path, file_name=file_name)
    assert not (tmp_path / "stored").exists()


def test_acquisition_validates_canonical_manifest_before_writing(tmp_path):
    # This is a legal base filename, but creates a storage reference that the
    # existing canonical snapshot contract rejects for secret-like material.
    with pytest.raises(AcquisitionError, match="snapshot manifest is invalid") as error:
        _acquire(tmp_path, file_name="token=private-fixture.csv")
    assert "private-fixture" not in str(error.value)
    assert not (tmp_path / "stored").exists()


@pytest.mark.parametrize("overrides", [
    {"source_id": "secret-source-value"},
    {"source_url": "https://example.com:secret-port-value/file.csv"},
])
def test_acquisition_errors_do_not_echo_operator_secrets(tmp_path, overrides):
    with pytest.raises(AcquisitionError) as error:
        _acquire(tmp_path, **overrides)
    assert "secret-source-value" not in str(error.value)
    assert "secret-port-value" not in str(error.value)
    assert not (tmp_path / "stored").exists()


@pytest.mark.parametrize("operation", ["acquire", "inspect"])
def test_file_size_is_checked_before_opening_oversized_file(tmp_path, monkeypatch, operation):
    source = tmp_path / "fixture.csv"
    source.write_bytes(b"12345")

    def forbidden_open(*_args, **_kwargs):
        raise AssertionError("Oversized files must not be opened or read")

    monkeypatch.setattr(Path, "open", forbidden_open)
    with pytest.raises(AcquisitionError, match="safe 4 byte limit"):
        if operation == "inspect":
            inspect_artifact(source, max_bytes=4)
        else:
            acquire_source_file(
                "data_gov_hospitals", "https://www.data.gov.in/resource/hospitals", source,
                storage_root=tmp_path / "stored", usage_basis="manual_public_snapshot",
                license_or_terms="Permitted synthetic test fixture.", dataset_version="test-1", max_bytes=4,
            )


def test_file_growth_after_stat_is_bounded_and_handle_is_closed(tmp_path, monkeypatch):
    source = tmp_path / "fixture.csv"
    source.write_bytes(b"1")
    requested_sizes = []

    class GrowingFile(io.BytesIO):
        def read(self, size=-1):
            requested_sizes.append(size)
            assert size == 5
            return super().read(size)

    handle = GrowingFile(b"123456789")
    monkeypatch.setattr(Path, "open", lambda *_args, **_kwargs: handle)
    with pytest.raises(AcquisitionError, match="safe 4 byte limit"):
        inspect_artifact(source, max_bytes=4)
    assert requested_sizes == [5]
    assert handle.closed


@pytest.mark.parametrize("members", [
    {"xl/worksheets/sheet1.xml": "x" * 4096},
    {"xl/worksheets/sheet1.xml": "x" * 400, "other1.xml": "x" * 400, "other2.xml": "x" * 400},
])
def test_xlsx_expansion_is_rejected_before_decompression_and_closes_handle(monkeypatch, members):
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, contents in members.items():
            archive.writestr(name, contents)
    monkeypatch.setattr(data_acquisition, "MAX_ARTIFACT_BYTES", 256)
    handles = []
    original = data_acquisition._bytes_file

    def tracked_file(content):
        handle = original(content)
        handles.append(handle)
        return handle

    def forbidden_open(*_args, **_kwargs):
        raise AssertionError("Archive member decompressed before size validation")

    monkeypatch.setattr(data_acquisition, "_bytes_file", tracked_file)
    monkeypatch.setattr(zipfile.ZipFile, "open", forbidden_open)
    with pytest.raises(AcquisitionError, match="expands beyond"):
        inspect_bytes(payload.getvalue(), file_name="fixture.xlsx")
    assert handles and all(handle.closed for handle in handles)


def test_inspection_checks_stored_hash_before_parsing(tmp_path, monkeypatch):
    acquired = _acquire(tmp_path)
    stored = Path(acquired["stored_path"])
    stored.write_bytes(b"secret_header\nsecret_row\n")
    monkeypatch.setattr(data_acquisition, "_inspect_csv", lambda *_: pytest.fail("Changed artifact was parsed"))
    with pytest.raises(AcquisitionError, match="does not match"):
        inspect_artifact(stored, expected_sha256=acquired["file_sha256"])


@pytest.mark.parametrize("changed_file", ["input", "stored"])
def test_cli_inspects_the_hashed_stored_copy(tmp_path, monkeypatch, capsys, changed_file):
    from scripts import acquire_dataset

    source = tmp_path / "fixture.csv"
    source.write_bytes(b"name\nSynthetic test row\n")
    original_acquire = acquire_dataset.acquire_source_file

    def acquire_then_change(*args, **kwargs):
        result = original_acquire(*args, **kwargs)
        target = source if changed_file == "input" else Path(result["stored_path"])
        target.write_bytes(b"secret_header\nsecret_row\n")
        return result

    monkeypatch.setattr(acquire_dataset, "acquire_source_file", acquire_then_change)
    monkeypatch.setattr(sys, "argv", [
        "acquire_dataset", "--source-id", "data_gov_hospitals",
        "--source-url", "https://www.data.gov.in/resource/hospitals",
        "--input", str(source), "--storage-root", str(tmp_path / "stored"),
        "--usage-basis", "manual_public_snapshot", "--license-or-terms", "Permitted synthetic test fixture.",
        "--dataset-version", "test-1", "--inspect",
    ])
    result = acquire_dataset.main()
    output = capsys.readouterr()
    assert "secret_header" not in output.out + output.err
    assert "secret_row" not in output.out + output.err
    assert "Synthetic test row" not in output.out
    if changed_file == "input":
        assert result == 0
        manifest = json.loads(output.out)
        assert manifest["schema_inspection"]["columns"] == ["name"]
        assert "stored_path" not in manifest
    else:
        assert result == 2
        assert output.out == ""
        assert "does not match" in output.err

