from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERCEL = ROOT / "vercel.ts"
PACKAGE = ROOT / "package.json"
COMPOSE = ROOT / "deploy" / "oci" / "compose.yaml"
OCI_ENV = ROOT / "deploy" / "oci" / ".env.example"


def test_vercel_gateway_fails_closed_and_never_receives_database_credentials():
    text = VERCEL.read_text(encoding="utf-8")

    assert "ZENDOC_ORIGIN_URL" in text
    assert "parsedOrigin.protocol !== 'https:'" in text
    assert "parsedOrigin.username" in text
    assert "parsedOrigin.password" in text
    assert "x-vercel-enable-rewrite-caching" in text
    assert "value: '0'" in text
    assert "DATABASE_URL" not in text
    assert "POSTGRES_PASSWORD" not in text


def test_repository_has_one_vercel_config_and_pins_config_sdk():
    assert VERCEL.is_file()
    assert not (ROOT / "vercel.json").exists()

    package = PACKAGE.read_text(encoding="utf-8")
    assert '"@vercel/config": "0.7.2"' in package


def test_oci_postgres_remains_private_behind_web_origin():
    text = COMPOSE.read_text(encoding="utf-8")
    db_block = text.split("  db:", 1)[1].split("\n  web:", 1)[0]
    web_block = text.split("  web:", 1)[1].split("\n  caddy:", 1)[0]

    assert "ports:" not in db_block
    assert "DATABASE_URL:" in web_block
    assert "@db:5432/" in web_block


def test_oci_public_url_is_distinct_from_origin_and_not_overridden_by_compose():
    env = OCI_ENV.read_text(encoding="utf-8")
    compose = COMPOSE.read_text(encoding="utf-8")

    assert "ZENDOC_DOMAIN=origin.zendoc.example" in env
    assert "ZENDOC_PUBLIC_BASE_URL=https://zendoc-sage.vercel.app" in env
    assert "ZENDOC_PUBLIC_BASE_URL:" not in compose
