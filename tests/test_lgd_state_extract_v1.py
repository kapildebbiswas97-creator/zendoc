import csv
from pathlib import Path

import pytest

from scripts.extract_lgd_state_bundle import extract_bundle
from zendoc.lgd_state_extract import extract_state_csv


def _write_csv(path: Path, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["State Code", "District Code", "District Name In English"])
        writer.writeheader()
        writer.writerows(rows)


def test_streaming_extractor_keeps_all_matching_west_bengal_rows_only(tmp_path):
    source = tmp_path / "districts_india.csv"
    target = tmp_path / "west_bengal" / "districts.csv"
    _write_csv(
        source,
        [
            {"State Code": "19", "District Code": "301", "District Name In English": "Example WB A"},
            {"State Code": "18", "District Code": "302", "District Name In English": "Example Assam"},
            {"State Code": "019", "District Code": "303", "District Name In English": "Example WB B"},
        ],
    )

    result = extract_state_csv(source, target, state_code="19")
    assert result["input_rows_scanned"] == 3
    assert result["matched_rows"] == 2
    with target.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["State Code"] for row in rows] == ["19", "019"]
    assert [row["District Code"] for row in rows] == ["301", "303"]


def test_extractor_requires_official_state_code_column(tmp_path):
    source = tmp_path / "bad.csv"
    source.write_text("District Code,District Name\n1,A\n", encoding="utf-8")
    with pytest.raises(ValueError, match="State Code"):
        extract_state_csv(source, tmp_path / "out.csv", state_code="19")


def test_extractor_refuses_same_input_output_path(tmp_path):
    source = tmp_path / "districts.csv"
    _write_csv(source, [{"State Code": "19", "District Code": "1", "District Name In English": "A"}])
    with pytest.raises(ValueError, match="differ"):
        extract_state_csv(source, source, state_code="19")


def test_bundle_writes_manifest_for_supplied_national_files(tmp_path):
    source = tmp_path / "districts.csv"
    _write_csv(source, [{"State Code": "19", "District Code": "1", "District Name In English": "A"}])
    out = tmp_path / "curated" / "lgd" / "west_bengal"
    result = extract_bundle(state_code="19", output_dir=out, datasets={"districts": str(source)})
    assert result["state_code"] == "19"
    assert result["datasets"]["districts"]["matched_rows"] == 1
    assert (out / "extract_manifest.json").is_file()
