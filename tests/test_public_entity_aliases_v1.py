from zendoc.public_data_ingestion import adapt_public_rows


def test_public_healthcare_category_aliases_cover_common_state_labels():
    rows = [
        {"source_record_id": "1", "category": "medical shop", "name": "Shop A"},
        {"source_record_id": "2", "category": "chemist", "name": "Shop B"},
        {"source_record_id": "3", "category": "pathology lab", "name": "Lab A"},
        {"source_record_id": "4", "category": "diagnostic center", "name": "Diag A"},
        {"source_record_id": "5", "category": "nursinghome", "name": "Nursing A"},
    ]

    result = adapt_public_rows(
        source_id="test_source",
        ingestion_type="public_healthcare_entities",
        rows=rows,
    )

    categories = [record["category"] for record in result["records"]]
    assert categories == [
        "pharmacy",
        "pharmacy",
        "laboratory",
        "diagnostic_centre",
        "nursing_home",
    ]
