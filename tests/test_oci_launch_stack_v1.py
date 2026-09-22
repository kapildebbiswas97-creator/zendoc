from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "deploy" / "oci" / "compose.yaml"
ENV_EXAMPLE = ROOT / "deploy" / "oci" / ".env.example"


def test_oci_postgres_is_not_published_to_host():
    text = COMPOSE.read_text(encoding="utf-8")

    db_block = text.split("  db:", 1)[1].split("\n  web:", 1)[0]
    assert "ports:" not in db_block
    assert "5432:5432" not in text
    assert "internal: true" in text


def test_oci_only_public_edge_publishes_http_https():
    text = COMPOSE.read_text(encoding="utf-8")

    web_block = text.split("  web:", 1)[1].split("\n  caddy:", 1)[0]
    caddy_block = text.split("  caddy:", 1)[1].split("\n  backup:", 1)[0]
    assert "ports:" not in web_block
    assert '"80:80"' in caddy_block
    assert '"443:443"' in caddy_block


def test_backup_container_does_not_inherit_application_env_file():
    text = COMPOSE.read_text(encoding="utf-8")

    backup_block = text.split("  backup:", 1)[1].split("\nvolumes:", 1)[0]
    assert "env_file:" not in backup_block
    assert "DATABASE_URL:" in backup_block
    assert "ZENDOC_ADMIN_PASSWORD" not in backup_block
    assert "ZENDOC_SMTP_PASSWORD" not in backup_block
    assert "ZENDOC_AI_API_KEY" not in backup_block


def test_real_oci_env_is_gitignored_and_example_defaults_fail_closed():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    example = ENV_EXAMPLE.read_text(encoding="utf-8")

    assert ".env" in gitignore
    assert "ZENDOC_PERSISTENCE_VERIFIED=false" in example
    assert "ZENDOC_BACKUP_VERIFIED=false" in example
    assert "ZENDOC_PUBLIC_RELEASE_REQUIRED=false" in example
    assert "ZENDOC_EMAIL_VERIFIED=false" in example
    assert "ZENDOC_STORAGE_VERIFIED=false" in example
