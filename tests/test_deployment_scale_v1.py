from pathlib import Path


def test_render_blueprint_uses_shared_gunicorn_profile_and_durable_db():
    text = Path("render.yaml").read_text(encoding="utf-8")
    assert "gunicorn -c gunicorn.conf.py run:app" in text
    assert "ZENDOC_REQUIRE_DURABLE_DATABASE" in text
    assert 'value: "true"' in text
    assert "ZENDOC_GUNICORN_WORKERS" in text
    assert "ZENDOC_GUNICORN_THREADS" in text


def test_procfile_uses_shared_gunicorn_profile():
    text = Path("Procfile").read_text(encoding="utf-8").strip()
    assert text == "web: gunicorn -c gunicorn.conf.py run:app"


def test_gunicorn_profile_has_worker_recycling_and_graceful_timeouts():
    text = Path("gunicorn.conf.py").read_text(encoding="utf-8")
    assert "workers =" in text
    assert "threads =" in text
    assert "graceful_timeout =" in text
    assert "max_requests =" in text
    assert "max_requests_jitter =" in text
