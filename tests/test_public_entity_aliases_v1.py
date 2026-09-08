from zendoc.public_data_ingestion import _prepare_healthcare_entities


def test_public_healthcare_category_aliases_cover_common_state_labels():
    rows = [
        {"source_record_id": "1", "category": "medical shop", "name": "Shop A"},
        {"source_record_id": "2", "category": "chemist", "name": "Shop B"},
        {"source_record_id": "3", "category": "pathology lab", "name": "Lab A"},
        {"source_record_id": "4", "category": "diagnostic center", "name": "Diag A"},
        {"source_record_id": "5", "category": "nursinghome", "name": "Nursing A"},
    ]

    result = _prepare_healthcare_entities({"source_id": "test_source"}, rows)

    assert result["rejected"] == []
    categories = [record["category"] for record in result["accepted"]]
    assert categories == [
        "pharmacy",
        "pharmacy",
        "laboratory",
        "diagnostic_centre",
        "nursing_home",
    ]
