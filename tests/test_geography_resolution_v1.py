from zendoc.db import get_db
from zendoc.geography_graph import link_geography_nodes, list_entities_for_geography, upsert_geography_node
from zendoc.geography_resolution import resolve_canonical_geography
from zendoc.public_data_ingestion import ingest_public_records
from tests.test_milestone1 import make_app


def owner_actor():
    return {"id": 1, "role": "admin", "email": "admin@example.com", "active": 1}


def build_wb_graph():
    country = upsert_geography_node(
        node_type="country",
        name="India",
        source="lgd",
        source_ref="country:IN",
        verified=True,
    )
    state = upsert_geography_node(
        node_type="state",
        name="West Bengal",
        parent_id=country["id"],
        source="lgd",
        source_ref="state:19",
        verified=True,
    )
    nadia = upsert_geography_node(
        node_type="district",
        name="Nadia",
        parent_id=state["id"],
        source="lgd",
        source_ref="district:320",
        verified=True,
    )
    ranaghat = upsert_geography_node(
        node_type="subdivision",
        name="Ranaghat",
        parent_id=nadia["id"],
        source="lgd",
        source_ref="subdistrict:2320",
        verified=True,
    )
    block = upsert_geography_node(
        node_type="block",
        name="Santipur",
        parent_id=ranaghat["id"],
        source="lgd",
        source_ref="block:WB-B1",
        verified=True,
    )
    village = upsert_geography_node(
        node_type="village",
        name="Fulia",
        parent_id=ranaghat["id"],
        source="lgd",
        source_ref="village:WB-V1",
        verified=True,
    )
    link_geography_nodes(
        from_node_id=village["id"],
        to_node_id=block["id"],
        relationship_type="BLOCK_MEMBERSHIP",
        source="lgd",
        source_ref="village:WB-V1:block:WB-B1",
    )
    return {
        "country": country,
        "state": state,
        "district": nadia,
        "subdistrict": ranaghat,
        "block": block,
        "village": village,
    }


def test_resolver_matches_deepest_exact_hierarchical_location(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        graph = build_wb_graph()
        result = resolve_canonical_geography(
            state="West Bengal",
            district="Nadia",
            subdistrict="Ranaghat",
            block="Santipur",
            village="Fulia",
        )

        assert result["status"] == "MATCHED"
        assert result["matched_level"] == "village"
        assert result["geography_node_id"] == graph["village"]["id"]
        assert result["resolution_method"] == "EXACT_HIERARCHICAL_NAME"


def test_resolver_does_not_guess_ambiguous_same_name_district(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        country = upsert_geography_node(
            node_type="country",
            name="India",
            source="lgd",
            source_ref="country:IN",
        )
        state_a = upsert_geography_node(
            node_type="state",
            name="State A",
            parent_id=country["id"],
            source="lgd",
            source_ref="state:A",
        )
        state_b = upsert_geography_node(
            node_type="state",
            name="State B",
            parent_id=country["id"],
            source="lgd",
            source_ref="state:B",
        )
        upsert_geography_node(
            node_type="district",
            name="Rampur",
            parent_id=state_a["id"],
            source="lgd",
            source_ref="district:A-R",
        )
        upsert_geography_node(
            node_type="district",
            name="Rampur",
            parent_id=state_b["id"],
            source="lgd",
            source_ref="district:B-R",
        )

        ambiguous = resolve_canonical_geography(district="Rampur")
        assert ambiguous["status"] == "AMBIGUOUS"
        assert ambiguous["candidate_count"] == 2

        scoped = resolve_canonical_geography(state="State A", district="Rampur")
        assert scoped["status"] == "MATCHED"
        assert scoped["matched_level"] == "district"


def test_public_facility_auto_links_using_exact_state_and_district_names(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        graph = build_wb_graph()

        result = ingest_public_records(
            owner_actor(),
            source_id="data_gov_hospitals",
            ingestion_type="public_healthcare_entities",
            records=[
                {
                    "source_record_id": "AUTO-GEO-HOSP-1",
                    "category": "hospital",
                    "name": "Auto Resolved Hospital",
                    "state": "West Bengal",
                    "district": "Nadia",
                }
            ],
            dry_run=False,
        )

        assert result["applied"]["inserted_count"] == 1
        assert result["applied"]["geography_linked_count"] == 1
        assert result["applied"]["geography_unresolved_count"] == 0
        assert result["applied"]["geography_ambiguous_count"] == 0

        links = list_entities_for_geography(graph["district"]["id"], entity_type="hospital")
        assert len(links) == 1
        assert links[0]["metadata"]["resolution_method"] == "EXACT_HIERARCHICAL_NAME"
        assert links[0]["metadata"]["matched_level"] == "district"


def test_unresolved_free_text_facility_is_kept_but_not_falsely_linked(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        build_wb_graph()

        result = ingest_public_records(
            owner_actor(),
            source_id="data_gov_hospitals",
            ingestion_type="public_healthcare_entities",
            records=[
                {
                    "source_record_id": "UNRESOLVED-1",
                    "category": "hospital",
                    "name": "Unknown Location Hospital",
                    "state": "West Bengal",
                    "district": "Not A Real District",
                }
            ],
            dry_run=False,
        )

        assert result["applied"]["inserted_count"] == 1
        assert result["applied"]["geography_linked_count"] == 0
        assert result["applied"]["geography_unresolved_count"] == 1
        row = get_db().execute(
            "SELECT id,district,state FROM public_healthcare_entities WHERE source_record_id='UNRESOLVED-1'"
        ).fetchone()
        assert row is not None
        assert row["district"] == "Not A Real District"


def test_explicit_unknown_source_ref_still_rejects_record(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        build_wb_graph()

        result = ingest_public_records(
            owner_actor(),
            source_id="data_gov_hospitals",
            ingestion_type="public_healthcare_entities",
            records=[
                {
                    "source_record_id": "STRICT-REF-1",
                    "category": "hospital",
                    "name": "Strict Ref Hospital",
                    "geography_source": "lgd",
                    "geography_source_record_id": "district:missing",
                }
            ],
            dry_run=False,
        )

        assert result["accepted_count"] == 0
        assert result["rejected_count"] == 1
        assert get_db().execute(
            "SELECT id FROM public_healthcare_entities WHERE source_record_id='STRICT-REF-1'"
        ).fetchone() is None
