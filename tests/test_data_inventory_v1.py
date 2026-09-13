from zendoc.data_freshness import platform_data_inventory
from zendoc.db import get_db
from tests.test_milestone1 import login_web, make_app


def test_owner_data_inventory_counts_persisted_operational_data(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        owner = get_db().execute("SELECT * FROM users WHERE email_normalized='admin@example.com'").fetchone()
        now = "2026-09-13T12:00:00+00:00"
        patient = get_db().execute(
            """
            INSERT INTO users
            (name,email,email_normalized,password_hash,role,created_at,updated_at)
            VALUES ('Inventory Patient','inventory-patient@example.com','inventory-patient@example.com','x','patient',?,?)
            RETURNING id
            """,
            (now, now),
        ).fetchone()
        get_db().execute(
            """
            INSERT INTO appointments
            (patient_id,provider_name,scheduled_for,reason,status,created_at,updated_at)
            VALUES (?, 'External referral', '2026-09-20T10:00', 'Inventory test', 'requested', ?, ?)
            """,
            (int(patient["id"]), now, now),
        )
        get_db().execute(
            """
            INSERT INTO ai_interactions
            (user_id,feature,intent,input_text,output_text,risk_level,model_version,provider,emergency,success,created_at)
            VALUES (?, 'assistant', 'navigation', 'hello', 'hi', 'low', 'test', 'deterministic', 0, 1, ?)
            """,
            (int(patient["id"]), now),
        )
        get_db().commit()

        inventory = platform_data_inventory(owner)

        assert inventory["database_engine"] == "sqlite"
        assert inventory["appointments"]["total"] == 1
        assert inventory["appointments"]["by_status"]["requested"] == 1
        assert inventory["ai_and_rag"]["ai_interactions"] == 1
        assert inventory["ai_and_rag"]["approved_source_families"] >= 5
        assert inventory["live_discovery"]["persistence_rule"] == "EXTERNAL_DISCOVERY_NOT_VERIFIED_OR_PERSISTED_AUTOMATICALLY"


def test_data_inventory_handles_optional_rag_tables_before_ingestion(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        owner = get_db().execute("SELECT * FROM users WHERE email_normalized='admin@example.com'").fetchone()
        inventory = platform_data_inventory(owner)
        assert inventory["ai_and_rag"]["knowledge_documents"] == 0
        assert inventory["ai_and_rag"]["knowledge_chunks"] == 0
        assert inventory["ai_and_rag"]["stored_embeddings"] == 0


def test_data_inventory_page_is_owner_only_and_explains_live_discovery(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()

    anonymous = client.get("/admin/startup/data-freshness", follow_redirects=False)
    assert anonymous.status_code == 302

    login_web(client, "admin", "admin@example.com", "AdminStrong123")
    response = client.get("/admin/startup/data-freshness")
    assert response.status_code == 200
    html = response.data.decode()
    assert "What data is actually inside ZENDOC?" in html
    assert "Live internet discovery" in html
    assert "not automatically ZENDOC-verified records" in html
    assert "AI &amp; medical RAG" in html
