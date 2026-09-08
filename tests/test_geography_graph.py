import pytest

from zendoc.geography_graph import (
    geography_path,
    link_entity_to_geography,
    list_entities_for_geography,
    search_geography_nodes,
    upsert_geography_node,
)
from tests.test_milestone1 import api_token, make_app


def test_geography_hierarchy_and_provenance(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        country = upsert_geography_node(
            node_type="country",
            name="Test Country",
            source="unit_test",
            source_ref="test-country",
            verified=True,
        )
        state = upsert_geography_node(
            node_type="state",
            name="Test State",
            parent_id=country["id"],
            source="unit_test",
            source_ref="test-state",
            verified=True,
        )
        district = upsert_geography_node(
            node_type="district",
            name="Test District",
            parent_id=state["id"],
            source="unit_test",
            source_ref="test-district",
            verified=True,
        )
        village = upsert_geography_node(
            node_type="village",
            name="Test Village",
            parent_id=district["id"],
            source="unit_test",
            source_ref="test-village",
            verified=False,
        )

        path = geography_path(village["id"])
        assert [item["node_type"] for item in path] == ["country", "state", "district", "village"]
        assert village["source"] == "unit_test"


def test_geography_rejects_invalid_parent_type(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        country = upsert_geography_node(
            node_type="country",
            name="Root",
            source="unit_test",
        )
        with pytest.raises(ValueError):
            upsert_geography_node(
                node_type="village",
                name="Bad Village",
                parent_id=country["id"],
                source="unit_test",
            )


def test_geography_entity_link_preserves_verification_state(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        country = upsert_geography_node(node_type="country", name="Country X", source="unit_test")
        state = upsert_geography_node(node_type="state", name="State X", parent_id=country["id"], source="unit_test")
        city = upsert_geography_node(node_type="city", name="City X", parent_id=state["id"], source="unit_test") if False else None

        # City cannot directly parent under state by design; use a district.
        district = upsert_geography_node(node_type="district", name="District X", parent_id=state["id"], source="unit_test")
        city = upsert_geography_node(node_type="city", name="City X", parent_id=district["id"], source="unit_test")
        link = link_entity_to_geography(
            geography_node_id=city["id"],
            entity_type="hospital",
            entity_id="external-place-123",
            source="google_places",
            verification_state="EXTERNAL_UNVERIFIED",
            metadata={"bookable_in_zendoc": False},
        )
        assert link["verification_state"] == "EXTERNAL_UNVERIFIED"
        assert link["metadata"]["bookable_in_zendoc"] is False
        entities = list_entities_for_geography(city["id"], entity_type="hospital")
        assert len(entities) == 1


def test_geography_search_api_requires_auth_and_returns_ingested_nodes(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    denied = client.get("/api/v1/geography/search?q=Test")
    assert denied.status_code == 401

    with app.app_context():
        upsert_geography_node(
            node_type="country",
            name="Searchable Test Country",
            source="unit_test",
        )

    token = api_token(client, "geo-user@example.com")
    response = client.get(
        "/api/v1/geography/search?q=Searchable",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.get_json()["nodes"]


def test_geography_admin_ingestion_is_owner_only(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    patient_token = api_token(client, "geo-normal@example.com")
    denied = client.post(
        "/api/v1/admin/geography/nodes",
        json={"node_type": "country", "name": "Denied", "source": "test"},
        headers={"Authorization": f"Bearer {patient_token}"},
    )
    assert denied.status_code == 403

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "AdminStrong123"},
    )
    assert login.status_code == 200
    owner_token = login.get_json()["token"]
    allowed = client.post(
        "/api/v1/admin/geography/nodes",
        json={"node_type": "country", "name": "Owner Test Country", "source": "unit_test", "verified": True},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert allowed.status_code == 201
    assert allowed.get_json()["node"]["verified"] == 1


def test_geography_graph_starts_empty_without_fabricated_preload(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        assert search_geography_nodes("Kolkata") == []
        assert search_geography_nodes("Malipota") == []


def test_geography_source_ref_is_stable_identity_across_rename(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        country = upsert_geography_node(
            node_type="country",
            name="India",
            source="lgd",
            source_ref="country:IN",
            verified=True,
        )
        state = upsert_geography_node(
            node_type="state",
            name="Example State",
            parent_id=country["id"],
            source="lgd",
            source_ref="state:99",
            verified=True,
        )
        first = upsert_geography_node(
            node_type="district",
            name="Old Official Name",
            parent_id=state["id"],
            source="lgd",
            source_ref="district:123",
            verified=True,
        )
        renamed = upsert_geography_node(
            node_type="district",
            name="New Official Name",
            parent_id=state["id"],
            source="lgd",
            source_ref="district:123",
            verified=True,
        )

        assert renamed["id"] == first["id"]
        assert renamed["name"] == "New Official Name"
        assert renamed["normalized_name"] == "new official name"


def test_same_geography_name_under_different_parents_does_not_collide(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        country = upsert_geography_node(node_type="country", name="India", source="lgd", source_ref="country:IN")
        state = upsert_geography_node(
            node_type="state", name="Example State", parent_id=country["id"],
            source="lgd", source_ref="state:98",
        )
        d1 = upsert_geography_node(
            node_type="district", name="District A", parent_id=state["id"],
            source="lgd", source_ref="district:A",
        )
        d2 = upsert_geography_node(
            node_type="district", name="District B", parent_id=state["id"],
            source="lgd", source_ref="district:B",
        )
        v1 = upsert_geography_node(
            node_type="village", name="Rampur", parent_id=d1["id"],
            source="lgd", source_ref="village:1",
        )
        v2 = upsert_geography_node(
            node_type="village", name="Rampur", parent_id=d2["id"],
            source="lgd", source_ref="village:2",
        )

        assert v1["id"] != v2["id"]
        assert v1["parent_id"] != v2["parent_id"]
