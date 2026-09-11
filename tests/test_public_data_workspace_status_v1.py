from scripts.bootstrap_public_data_workspace import bootstrap
from scripts.public_data_workspace_status import workspace_status


def test_workspace_status_reports_missing_manual_authorized_and_catalog_only(tmp_path):
    root = tmp_path / "ZENDOC_DATA"
    bootstrap(root)
    result = workspace_status(root)
    assert result["status"] == "OK"
    by_id = {item["source_id"]: item for item in result["sources"]}
    assert by_id["abdm_hfr"]["status"] == "AUTHORIZED_BLOCKED"
    assert by_id["wb_clinical_establishments"]["status"] == "CATALOG_ONLY"
    assert by_id["wb_drug_license_verification"]["status"] == "CATALOG_ONLY"
    assert by_id["lgd"]["status"] in {"MISSING", "MANUAL_SNAPSHOT_REQUIRED"}


def test_workspace_status_detects_content_addressed_snapshot_without_reading_rows(tmp_path):
    root = tmp_path / "ZENDOC_DATA"
    bootstrap(root)
    raw = root / "raw" / "lgd" / ("a" * 64)
    raw.mkdir(parents=True)
    (raw / "districts.csv").write_text("State Code,District Code\n19,1\n", encoding="utf-8")
    result = workspace_status(root)
    by_id = {item["source_id"]: item for item in result["sources"]}
    assert by_id["lgd"]["status"] == "ACQUIRED"
    assert by_id["lgd"]["snapshot_count"] == 1
