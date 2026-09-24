from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERCEL = ROOT / "vercel.ts"
PACKAGE = ROOT / "package.json"
COMPOSE = ROOT / "deploy" / "oci" / "compose.yaml"
OCI_ENV = ROOT / "deploy" / "oci" / ".env.example"


def test_vercel_gateway_requires_https_origin_and_has_no_database_secret():
    text = VERCEL.read_text(encoding="utf-8")

    assert "ZENDOC_ORIGIN_URL" in text
    assert "parsedOrigin.protocol !== 'https:'" in text
    assert "parsedOrigin.username" in text
    assert "parsedOrigin.password" in text
    assert "deploymentEnabled: false" in text
    assert "x-vercel-enable-rewrite-caching" in text
    assert "value: '0'" in text
    assert "routes.rewrite('/:path*', `${origin}/:path*`)" in text
    assert "routes.header('/:path*'" in text
    assert "DATABASE_URL" not in text
    assert "POSTGRES_PASSWORD" not in text


def test_vercel_config_is_single_source_and_dependency_is_pinned():
    assert VERCEL.is_file()
    assert not (ROOT / "vercel.json").exists()

    package = PACKAGE.read_text(encoding="utf-8")
    assert '"@vercel/config": "0.7.2"' in package


def test_postgres_is_not_published_from_oci_compose():
    text = COMPOSE.read_text(encoding="utf-8")
    db_block = text.split("  db:", 1)[1].split("\n  web:", 1)[0]

    assert "ports:" not in db_block
    assert "internal: true" in text


def test_public_url_and_oci_origin_are_distinct_and_restore_guard_is_preserved():
    env = OCI_ENV.read_text(encoding="utf-8")
    compose = COMPOSE.read_text(encoding="utf-8")

    assert "ZENDOC_DOMAIN=origin.zendoc.example" in env
    assert "ZENDOC_PUBLIC_BASE_URL=https://zendoc-sage.vercel.app" in env
    assert "ZENDOC_POSTGRES_RESTORE_ALLOW_RESET=false" in env
    assert "ZENDOC_PUBLIC_BASE_URL:" not in compose
    assert "ZENDOC_POSTGRES_RESTORE_ALLOW_RESET:" in compose
