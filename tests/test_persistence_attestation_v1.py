from zendoc.persistence_attestation import persistence_attestation


def test_explicit_operator_attestation_remains_authoritative():
    result = persistence_attestation(
        environment="development",
        engine="sqlite",
        durability="local_development",
        explicit_verified=True,
        require_durable_database=False,
        database_reachable=False,
        migrations_ready=False,
        schema_ready=False,
    )
    assert result == {"verified": True, "source": "explicit_operator_attestation"}


def test_runtime_postgres_attestation_requires_all_production_evidence():
    result = persistence_attestation(
        environment="production",
        engine="postgresql",
        durability="durable_configured",
        explicit_verified=False,
        require_durable_database=True,
        database_reachable=True,
        migrations_ready=True,
        schema_ready=True,
    )
    assert result == {"verified": True, "source": "runtime_durable_postgresql_attestation"}


def test_runtime_attestation_never_self_verifies_sqlite():
    result = persistence_attestation(
        environment="production",
        engine="sqlite",
        durability="durable_configured",
        explicit_verified=False,
        require_durable_database=True,
        database_reachable=True,
        migrations_ready=True,
        schema_ready=True,
    )
    assert result["verified"] is False


def test_runtime_postgres_attestation_fails_closed_when_any_evidence_is_missing():
    base = {
        "environment": "production",
        "engine": "postgresql",
        "durability": "durable_configured",
        "explicit_verified": False,
        "require_durable_database": True,
        "database_reachable": True,
        "migrations_ready": True,
        "schema_ready": True,
    }
    for field in ("require_durable_database", "database_reachable", "migrations_ready", "schema_ready"):
        case = dict(base)
        case[field] = False
        assert persistence_attestation(**case)["verified"] is False

    for field, value in (
        ("environment", "development"),
        ("engine", "sqlite"),
        ("durability", "integration_required"),
    ):
        case = dict(base)
        case[field] = value
        assert persistence_attestation(**case)["verified"] is False
