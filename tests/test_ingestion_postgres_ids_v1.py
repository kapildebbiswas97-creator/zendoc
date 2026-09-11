from zendoc.postgres_backend import translate_sql


def test_postgres_returns_inserted_ids_for_snapshot_and_geography_writes():
    for table in ("data_ingestion_batches", "public_healthcare_entities", "geography_nodes"):
        sql, returns_id = translate_sql(f"INSERT INTO {table} (source_id) VALUES (?)")
        assert returns_id
        assert sql.endswith("RETURNING id")
        assert "%s" in sql

