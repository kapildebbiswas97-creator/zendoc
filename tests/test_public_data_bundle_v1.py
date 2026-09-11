from pathlib import Path

import pytest

from scripts.bootstrap_public_data_workspace import bootstrap
from scripts.download_public_artifact import _host_allowed, download_public_artifact
from zendoc.data_acquisition import AcquisitionError
from zendoc.public_data_bundle import (
    ALL_INDIA,
    FULL_WEST_BENGAL,
    india_bundle,
    west_bengal_bundle,
)


def test_west_bengal_bundle_is_full_state_not_nadia_only():
    bundle = west_bengal_bundle()
    assert bundle["scope"] == FULL_WEST_BENGAL
    assert bundle["coverage_rule"] == "ALL_DISTRICTS_FROM_CURRENT_OFFICIAL_LGD_SNAPSHOT"
    assert bundle["validation_is_not_scope_limit"] is True
    assert bundle["validation_districts"] == ["Nadia"]
    source_ids = {item["source_id"] for item in bundle["sources"]}
    assert {"lgd", "data_gov_hospitals", "wbhs_empanelled_hco", "swasthya_sathi_hospitals"} <= source_ids


def test_india_bundle_catalogues_public_and_authorized_sources_separately():
    bundle = india_bundle()
    assert bundle["scope"] == ALL_INDIA
    assert bundle["coverage_rule"] == "ALL_STATES_AND_UTS_FROM_CURRENT_OFFICIAL_LGD_SNAPSHOT"
    public_ids = {item["source_id"] for item in bundle["sources"]}
    auth_ids = {item["source_id"] for item in bundle["authorized_only_sources"]}
    assert {"lgd", "data_gov_hospitals", "nabl_labs", "pmbjp_kendras"} <= public_ids
    assert {"abdm_hfr", "abdm_hpr"} <= auth_ids
    assert public_ids.isdisjoint(auth_ids)


def test_workspace_bootstrap_creates_data_drive_layout(tmp_path):
    root = tmp_path / "ZENDOC_DATA"
    result = bootstrap(root)
    assert result["status"] == "READY"
    for name in ("raw", "incoming", "manifests", "curated", "samples", "rejected", "logs"):
        assert (root / name).is_dir()
    catalog = (root / "manifests" / "source_catalog.json").read_text(encoding="utf-8")
    assert "west_bengal_full_state_v1" in catalog
    assert "india_public_official_v1" in catalog


def test_official_host_matching_allows_only_registered_relations_and_explicit_ogd_family():
    assert _host_allowed("files.data.gov.in", "www.data.gov.in") is True
    assert _host_allowed("www.data.gov.in", "data.gov.in") is True
    assert _host_allowed("data.gov.in", "www.data.gov.in") is True
    assert _host_allowed("evil.example", "data.gov.in") is False
    assert _host_allowed("malicious-gov.in.example", "data.gov.in") is False


def test_authorized_registry_cannot_use_public_downloader(tmp_path):
    with pytest.raises(AcquisitionError, match="authorized access"):
        download_public_artifact(
            "abdm_hfr",
            "https://hfr.abdm.gov.in/export.csv",
            storage_root=tmp_path,
            usage_basis="authorized_export",
            license_or_terms="Authorized access required",
            dataset_version="test",
            file_name="hfr.csv",
        )
