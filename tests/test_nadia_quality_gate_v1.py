import pytest

from zendoc.nadia_pilot import nadia_data_quality_gate


def reviewed_report():
    return {
        **dict.fromkeys((
            "source_valid", "schema_mapped", "dry_run", "geography_validated", "duplicates_reviewed",
            "provenance_persisted", "no_fake_verification", "no_fake_availability", "security_tests", "postgresql_tests",
        ), True),
        "snapshot_uid": "snapshot_" + "a" * 20, "file_sha256": "b" * 64,
        "usage_basis": "manual_public_snapshot", "license_or_terms": "Synthetic test review.",
        "source_record_count": 1, "mapped_record_count": 1, "accepted_count": 1,
        "rejected_count": 0, "conflict_count": 0,
    }


def test_reviewed_nonempty_consistent_report_passes():
    assert nadia_data_quality_gate(reviewed_report())["status"] == "PASS"


@pytest.mark.parametrize("field,value", [
    ("source_record_count", 0), ("mapped_record_count", 0), ("accepted_count", -1),
    ("conflict_count", 1), ("accepted_count", "unknown"), ("accepted_count", True),
    ("rejected_count", 8), ("file_sha256", "invented-hash"), ("snapshot_uid", "snapshot_fake"),
])
def test_report_does_not_pass_with_empty_malformed_or_conflicting_evidence(field, value):
    report = reviewed_report()
    report[field] = value
    assert nadia_data_quality_gate(report)["status"] == "BLOCKED"

