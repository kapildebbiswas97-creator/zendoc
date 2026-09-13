from __future__ import annotations


def persistence_attestation(
    *,
    environment: str,
    engine: str,
    durability: str | None,
    explicit_verified: bool,
    require_durable_database: bool,
    database_reachable: bool,
    migrations_ready: bool,
    schema_ready: bool,
) -> dict:
    if explicit_verified:
        return {"verified": True, "source": "explicit_operator_attestation"}

    runtime_postgres = (
        str(engine or "").lower() == "postgresql"
        and str(durability or "").lower() == "durable_configured"
        and bool(database_reachable)
        and bool(migrations_ready)
        and bool(schema_ready)
    )
    if runtime_postgres:
        return {"verified": True, "source": "runtime_durable_postgresql_attestation"}

    return {"verified": False, "source": "not_verified"}
