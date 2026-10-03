import json

from zendoc.db import get_db
from zendoc.global_source_research import (
    enqueue_source_research_batch,
    global_source_gap_report,
)
from tests.test_milestone1 import make_app


def test_global_source_gap_report_is_truthful_and_worldwide(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        report = global_source_gap_report()
        assert report["country_count"] == 195
        assert report["source_registered_country_count"] + report["source_gap_count"] == 195
        assert report["source_gap_count"] > 0
        assert all(item["country_code"] for item in report["gaps"])
        assert "guessed" in report["truth_notice"].lower()


def test_research_agent_source_gap_batch_is_bounded_and_deduplicated(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db = get_db()
        owner = db.execute(
            "SELECT * FROM users WHERE role='admin' AND active=1 ORDER BY id LIMIT 1"
        ).fetchone()

        first = enqueue_source_research_batch(owner, max_countries=7)
        second = enqueue_source_research_batch(owner, max_countries=7)

        assert first["source_gap_count"] > 0
        assert len(first["selected_countries"]) == 7
        assert first["production_changes_executed"] == 0
        assert first["task"]["assigned_agent"] == "OperationsAgent"
        assert second["task"]["id"] == first["task"]["id"]

        rows = db.execute(
            "SELECT * FROM agent_tasks WHERE task_type='global_source_research'"
        ).fetchall()
        assert len(rows) == 1
        metadata = json.loads(rows[0]["metadata_json"])
        assert metadata["workforce_owner"] == "ResearchAgent"
        assert "captcha_or_auth_bypass" in metadata["forbidden"]
        assert "automatic_ingestion_before_source_review" in metadata["forbidden"]
