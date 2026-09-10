import hashlib
import json

import pytest

from zendoc.dataset_snapshot_ingestion import ingest_public_snapshot, normalize_dataset_snapshot
from zendoc.db import get_db
from tests.test_milestone1 import make_app, make_client


def owner_actor():
    return {"id": 1, "role": "admin", "email": "admin@example.com", "active": 1}


def snapshot(**overrides):
    manifest = {
        "source_id": "data_gov_hospitals",
        "source_url": "https://www.data.gov.in/resource/pilot-hospital-directory.csv",
        "retrieved_at": "2026-09-11T00:30:00+05:30",
        "dataset_version": "2026-09-10",
        "file_name": "hospital-directory-2026-09-10.csv",
        "file_format": "csv",
        "file_size_bytes": 12345,
        "file_sha256": hashlib.sha256(b"exact downloaded test dataset").hexdigest(),
        "usage_basis": "official_public_download",
        "license_or_terms": "Official public/open-data snapshot retained for source provenance testing.",
        "license_url": "https://www.data.gov.in/terms-of-use",
        "storage_ref": "raw/data_gov_hospitals/2026-09-10/hospital-directory.csv",
    }
    manifest.update(overrides)
    return manifest


def hospital(name="Pilot Snapshot Hospital"):
    return {
        "source_record_id": "SNAP-HOSP-001",
        "category": "hospital",
        "name": name,
        "district": "Nadia",
        "state": "West Bengal",
    }


def test_snapshot_manifest_is_normalized_and_checksum_addressed(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        result = normalize_dataset_snapshot("data_gov_hospitals", snapshot())
        assert result["source_id"] == "data_gov_hospitals"
        assert result["file_format"] == "csv"
        assert len(result["manifest_sha256"]) == 64
        assert result["snapshot_uid"].startswith("snapshot_")


def test_snapshot_manifest_rejects_secret_bearing_urls_and_bad_hash(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        with pytest.raises(ValueError, match="credentials"):
            normalize_dataset_snapshot(
                "data_gov_hospitals",
                snapshot(source_url="https://example.gov/data.csv?api_key=do-not-store-me"),
            )
        with pytest.raises(ValueError, match="64 hexadecimal"):
            normalize_dataset_snapshot(
                "data_gov_hospitals",
                snapshot(file_sha256="not-a-sha256"),
            )


def test_snapshot_manifest_rejects_source_mismatch_and_missing_version(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        with pytest.raises(ValueError, match="must match"):
            normalize_dataset_snapshot(
                "data_gov_hospitals",
                snapshot(source_id="lgd"),
            )
        manifest = snapshot(dataset_version=None, published_at=None)
        with pytest.raises(ValueError, match="dataset_version or published_at"):
            normalize_dataset_snapshot("data_gov_hospitals", manifest)


def test_snapshot_apply_requires_exact_prior_preview_and_persists_provenance(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        preview = ingest_public_snapshot(
            owner_actor(),
            source_id="data_gov_hospitals",
            ingestion_type="public_healthcare_entities",
            records=[hospital()],
            dataset_snapshot=snapshot(),
            dry_run=True,
        )
        assert preview["dry_run"] is True
        assert preview["snapshot_bound"] is True

        applied = ingest_public_snapshot(
            owner_actor(),
            source_id="data_gov_hospitals",
            ingestion_type="public_healthcare_entities",
            records=[hospital()],
            dataset_snapshot=snapshot(),
            dry_run=False,
            preview_batch_uid=preview["batch_uid"],
        )
        assert applied["dry_run"] is False
        assert applied["applied"]["inserted_count"] == 1
        assert applied["summary"]["source_snapshot_preview_batch_uid"] == preview["batch_uid"]

        entity = get_db().execute(
            "SELECT zendoc_verification_status,booking_connectivity,metadata_json "
            "FROM public_healthcare_entities WHERE source_id=? AND source_record_id=?",
            ("data_gov_hospitals", "SNAP-HOSP-001"),
        ).fetchone()
        assert entity is not None
        assert entity["zendoc_verification_status"] == "not_verified"
        assert entity["booking_connectivity"] == "not_connected"
        metadata = json.loads(entity["metadata_json"])
        source_snapshot = metadata["_zendoc_source_snapshot"]
        assert source_snapshot["file_sha256"] == snapshot()["file_sha256"]
        assert source_snapshot["dataset_version"] == "2026-09-10"

        batch = get_db().execute(
            "SELECT summary_json FROM data_ingestion_batches WHERE batch_uid=?",
            (applied["batch_uid"],),
        ).fetchone()
        summary = json.loads(batch["summary_json"])
        assert summary["dataset_snapshot"]["file_sha256"] == snapshot()["file_sha256"]
        assert summary["source_snapshot_preview_batch_uid"] == preview["batch_uid"]


def test_snapshot_apply_rejects_changed_file_or_changed_rows_after_preview(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        preview = ingest_public_snapshot(
            owner_actor(),
            source_id="data_gov_hospitals",
            ingestion_type="public_healthcare_entities",
            records=[hospital()],
            dataset_snapshot=snapshot(),
            dry_run=True,
        )

        changed_snapshot = snapshot(file_sha256=hashlib.sha256(b"different downloaded file").hexdigest())
        with pytest.raises(ValueError, match="does not match|different dataset snapshot"):
            ingest_public_snapshot(
                owner_actor(),
                source_id="data_gov_hospitals",
                ingestion_type="public_healthcare_entities",
                records=[hospital()],
                dataset_snapshot=changed_snapshot,
                dry_run=False,
                preview_batch_uid=preview["batch_uid"],
            )

        with pytest.raises(ValueError, match="does not match"):
            ingest_public_snapshot(
                owner_actor(),
                source_id="data_gov_hospitals",
                ingestion_type="public_healthcare_entities",
                records=[hospital(name="Changed After Preview")],
                dataset_snapshot=snapshot(),
                dry_run=False,
                preview_batch_uid=preview["batch_uid"],
            )


def test_snapshot_apply_without_preview_is_rejected(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        with pytest.raises(ValueError, match="preview_batch_uid is required"):
            ingest_public_snapshot(
                owner_actor(),
                source_id="data_gov_hospitals",
                ingestion_type="public_healthcare_entities",
                records=[hospital()],
                dataset_snapshot=snapshot(),
                dry_run=False,
            )


def test_snapshot_endpoints_are_owner_only_and_require_explicit_apply(tmp_path):
    _app, client = make_client(tmp_path)

    denied = client.post(
        "/api/v1/admin/ingestion/snapshots/validate",
        json={"source_id": "data_gov_hospitals", "dataset_snapshot": snapshot()},
    )
    assert denied.status_code in {302, 401, 403}

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "AdminStrong123"},
    )
    assert login.status_code == 200
    token = login.get_json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    validated = client.post(
        "/api/v1/admin/ingestion/snapshots/validate",
        json={"source_id": "data_gov_hospitals", "dataset_snapshot": snapshot()},
        headers=headers,
    )
    assert validated.status_code == 200
    assert validated.get_json()["dataset_snapshot"]["snapshot_uid"].startswith("snapshot_")

    refused = client.post(
        "/api/v1/admin/ingestion/snapshots/apply",
        json={
            "source_id": "data_gov_hospitals",
            "ingestion_type": "public_healthcare_entities",
            "records": [hospital()],
            "dataset_snapshot": snapshot(),
        },
        headers=headers,
    )
    assert refused.status_code == 400
    assert "apply=true" in refused.get_json()["error"]["message"]
