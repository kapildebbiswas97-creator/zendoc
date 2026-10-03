from zendoc import public_data_refresh
from zendoc.db import get_db
from tests.test_milestone1 import make_app


def _owner():
    return get_db().execute(
        "SELECT * FROM users WHERE role='admin' AND email='admin@example.com'"
    ).fetchone()


def _profile():
    return {
        "source_id": "data_gov_hospitals",
        "connector_type": "DATA_GOV_RESOURCE_API_OR_DOWNLOAD",
        "ingestion_type": "public_healthcare_entities",
        "availability": "CONFIGURABLE_NOW",
        "config_keys": ["ZENDOC_DATA_GOV_API_KEY", "ZENDOC_DATA_GOV_HOSPITAL_RESOURCE_ID"],
        "refresh_cadence": "MONTHLY",
        "notes": "test",
    }


def _source():
    return {
        "source_id": "data_gov_hospitals",
        "personal_data_allowed": False,
        "ingestion_types": ["public_healthcare_entities"],
        "trust_level": "OFFICIAL_PUBLIC_DATA",
    }


def test_auto_refresh_processes_bounded_pages_and_then_respects_cadence(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    calls = []
    ingestions = []

    monkeypatch.setattr(public_data_refresh, "list_connector_profiles", lambda: [_profile()])
    monkeypatch.setattr(public_data_refresh, "get_public_ingestion_source", lambda _source_id: _source())
    monkeypatch.setattr(
        public_data_refresh,
        "connector_readiness",
        lambda _source_id: {"ready_for_fetch": True, "missing_config": []},
    )

    def fake_fetch(source_id, *, limit, offset):
        calls.append((source_id, limit, offset))
        if offset == 0:
            return {
                "source_id": source_id,
                "records": [
                    {"source_record_id": "1", "name": "Hospital 1", "category": "hospital"},
                    {"source_record_id": "2", "name": "Hospital 2", "category": "hospital"},
                ],
                "record_count": 2,
                "rejected_count": 0,
                "upstream_count": 2,
                "upstream_total": 3,
            }
        return {
            "source_id": source_id,
            "records": [
                {"source_record_id": "3", "name": "Hospital 3", "category": "hospital"},
            ],
            "record_count": 1,
            "rejected_count": 0,
            "upstream_count": 1,
            "upstream_total": 3,
        }

    def fake_ingest(actor, **kwargs):
        ingestions.append({"actor": actor, **kwargs})
        return {"status": "previewed" if kwargs["dry_run"] else "completed", "duplicate_batch": False}

    monkeypatch.setattr(public_data_refresh, "fetch_data_gov_resource", fake_fetch)
    monkeypatch.setattr(public_data_refresh, "ingest_public_records", fake_ingest)

    with app.app_context():
        owner = _owner()
        first = public_data_refresh.refresh_official_public_data(owner, page_limit=2)
        second = public_data_refresh.refresh_official_public_data(owner, page_limit=2)
        third = public_data_refresh.refresh_official_public_data(owner, page_limit=2)
        state = public_data_refresh.public_refresh_snapshot()["states"][0]

    assert calls == [
        ("data_gov_hospitals", 2, 0),
        ("data_gov_hospitals", 2, 2),
    ]
    assert first["processed_count"] == 1
    assert first["outcomes"][0]["complete"] is False
    assert second["outcomes"][0]["complete"] is True
    assert third["processed_count"] == 0
    assert state["next_offset"] == 0
    assert state["last_success_at"]
    assert all(item["dry_run"] is True for item in ingestions)


def test_switching_preview_to_apply_restarts_at_zero_and_applies(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    fetch_offsets = []
    dry_run_values = []

    monkeypatch.setattr(public_data_refresh, "list_connector_profiles", lambda: [_profile()])
    monkeypatch.setattr(public_data_refresh, "get_public_ingestion_source", lambda _source_id: _source())
    monkeypatch.setattr(
        public_data_refresh,
        "connector_readiness",
        lambda _source_id: {"ready_for_fetch": True, "missing_config": []},
    )

    def fake_fetch(source_id, *, limit, offset):
        fetch_offsets.append(offset)
        return {
            "source_id": source_id,
            "records": [{"source_record_id": str(offset + 1), "name": "Hospital", "category": "hospital"}],
            "record_count": 1,
            "rejected_count": 0,
            "upstream_count": limit,
            "upstream_total": 999,
        }

    def fake_ingest(_actor, **kwargs):
        dry_run_values.append(kwargs["dry_run"])
        return {"status": "previewed" if kwargs["dry_run"] else "completed", "duplicate_batch": False}

    monkeypatch.setattr(public_data_refresh, "fetch_data_gov_resource", fake_fetch)
    monkeypatch.setattr(public_data_refresh, "ingest_public_records", fake_ingest)

    with app.app_context():
        owner = _owner()
        public_data_refresh.refresh_official_public_data(owner, apply=False, page_limit=2)
        public_data_refresh.refresh_official_public_data(owner, apply=True, page_limit=2)

    assert fetch_offsets == [0, 0]
    assert dry_run_values == [True, False]


def test_auto_refresh_excludes_geography_and_personal_sources(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    profiles = [
        {
            **_profile(),
            "source_id": "lgd",
            "ingestion_type": "geography_nodes",
        },
        {
            **_profile(),
            "source_id": "private_source",
        },
    ]

    monkeypatch.setattr(public_data_refresh, "list_connector_profiles", lambda: profiles)
    monkeypatch.setattr(
        public_data_refresh,
        "get_public_ingestion_source",
        lambda source_id: {
            "source_id": source_id,
            "personal_data_allowed": source_id == "private_source",
        },
    )

    with app.app_context():
        result = public_data_refresh.refresh_official_public_data(_owner())

    assert result["configured_source_count"] == 0
    assert result["processed_count"] == 0


def test_auto_refresh_records_only_failure_category_not_exception_text(tmp_path, monkeypatch):
    app = make_app(tmp_path)

    monkeypatch.setattr(public_data_refresh, "list_connector_profiles", lambda: [_profile()])
    monkeypatch.setattr(public_data_refresh, "get_public_ingestion_source", lambda _source_id: _source())
    monkeypatch.setattr(
        public_data_refresh,
        "connector_readiness",
        lambda _source_id: {"ready_for_fetch": True, "missing_config": []},
    )

    def fail_fetch(*_args, **_kwargs):
        raise RuntimeError("sensitive-upstream-message-that-must-not-be-persisted")

    monkeypatch.setattr(public_data_refresh, "fetch_data_gov_resource", fail_fetch)

    with app.app_context():
        result = public_data_refresh.refresh_official_public_data(_owner())
        state = public_data_refresh.public_refresh_snapshot()["states"][0]

    assert result["outcomes"][0]["error_category"] == "RuntimeError"
    assert state["last_error_category"] == "RuntimeError"
    assert "sensitive-upstream-message" not in repr(state)
