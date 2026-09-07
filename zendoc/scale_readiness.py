"""Production scale-readiness checks for ZENDOC.

This report is stricter than pilot readiness. It verifies software/deployment
conditions that matter before broad state-scale user growth. It does not claim
an exact supported user count because that depends on hosting CPU/RAM, database
tier, external providers, traffic shape, and load testing.
"""
from __future__ import annotations

import os

from flask import current_app

from .database_reliability import readiness_report
from .db import get_db
from .observability import request_metrics, agent_metrics


def scale_readiness_report() -> dict:
    readiness = readiness_report()
    blockers = []
    warnings = []
    passed = []

    if readiness.get("status") != "ready":
        blockers.append({
            "key": "database_readiness",
            "message": "Database/schema readiness is not green.",
            "detail": readiness,
        })
    else:
        passed.append({"key": "database_readiness", "message": "Database/schema readiness is green."})

    engine = str(current_app.config.get("DATABASE_ENGINE") or "").lower()
    if engine != "postgresql":
        blockers.append({
            "key": "database_engine",
            "message": "Broad multi-user production scale requires managed PostgreSQL; SQLite remains a pilot/local option.",
        })
    else:
        passed.append({"key": "database_engine", "message": "PostgreSQL is configured."})

    if not bool(current_app.config.get("PERSISTENCE_VERIFIED")):
        blockers.append({
            "key": "persistence_verified",
            "message": "Production persistence has not been explicitly verified.",
        })
    else:
        passed.append({"key": "persistence_verified", "message": "Production persistence is marked verified."})

    tables = {
        row["name"] if "name" in row.keys() else row["table_name"]
        for row in _table_rows()
    }
    for table in ("api_rate_limit_buckets", "geography_import_regions", "geography_relationships"):
        if table not in tables:
            blockers.append({
                "key": f"table_{table}",
                "message": f"Required scale table '{table}' is missing.",
            })
        else:
            passed.append({"key": f"table_{table}", "message": f"{table} is present."})

    workers = _env_int("ZENDOC_GUNICORN_WORKERS", 2)
    threads = _env_int("ZENDOC_GUNICORN_THREADS", 4)
    concurrency = workers * threads
    if concurrency < 4:
        warnings.append({
            "key": "app_concurrency",
            "message": f"Configured Gunicorn concurrency is {concurrency}; increase hosting capacity/workers before heavy traffic.",
            "workers": workers,
            "threads": threads,
        })
    else:
        passed.append({
            "key": "app_concurrency",
            "message": f"Configured Gunicorn concurrency is {concurrency} ({workers} worker(s) × {threads} thread(s)).",
        })

    requests = request_metrics(60)
    total = int(requests.get("total") or 0)
    errors = int(requests.get("server_errors") or 0)
    if total >= 20:
        error_rate = round(errors * 100.0 / total, 1)
        if error_rate >= 2.0:
            blockers.append({
                "key": "recent_server_error_rate",
                "message": f"Recent server error rate is {error_rate}% across {total} request(s).",
            })
        else:
            passed.append({
                "key": "recent_server_error_rate",
                "message": f"Recent server error rate is {error_rate}% across {total} request(s).",
            })
    else:
        warnings.append({
            "key": "recent_server_error_rate",
            "message": "Not enough recent traffic exists to validate production error rate statistically.",
        })

    agents = agent_metrics(60)
    agent_runs = int(agents.get("total") or 0)
    agent_failures = int(agents.get("failed") or 0)
    if agent_runs >= 10 and agent_failures:
        failure_rate = round(agent_failures * 100.0 / agent_runs, 1)
        if failure_rate >= 5.0:
            blockers.append({
                "key": "agent_failure_rate",
                "message": f"Agent failure rate is {failure_rate}% in the current window.",
            })

    # Hosting/DB capacity cannot be proven from source code alone.
    warnings.append({
        "key": "capacity_load_test",
        "message": (
            "Exact supported concurrent users cannot be certified from application tests alone. "
            "Run load tests against the actual production hosting/database tier before large public rollout."
        ),
    })

    status = "BLOCKED" if blockers else ("SCALE_READY_WITH_WARNINGS" if warnings else "SCALE_READY")
    return {
        "status": status,
        "blockers": blockers,
        "warnings": warnings,
        "passed": passed,
        "database": readiness,
        "runtime": {
            "gunicorn_workers": workers,
            "gunicorn_threads": threads,
            "configured_concurrency": concurrency,
        },
        "truth_notice": (
            "SCALE_READY verifies ZENDOC software/deployment prerequisites only. "
            "It does not guarantee a specific user count, provider density, external API capacity, or geographic service availability."
        ),
    }


def _table_rows():
    db = get_db()
    if getattr(db, "dialect", "sqlite") == "postgresql":
        return db.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema=current_schema()"
        ).fetchall()
    return db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, str(default))))
    except (TypeError, ValueError):
        return default
