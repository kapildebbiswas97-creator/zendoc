"""Regressions for the verified ZENDOC prelaunch PostgreSQL and AWS runbook defects.

These source contract tests complement the existing functional Health Memory
SQLite test and PostgreSQL readiness suite. They do not prove live EC2 access,
backup restore, or actual PostgreSQL runtime behavior of every application route.
"""
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _source(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_duplicate_metrics_query_has_postgresql_grouping_safe_select():
    # Duplicate semantics group by metric type + timestamp, even when values
    # differ. SELECT must not include ungrouped/nonaggregate metric fields.
    source = _source("zendoc/health_memory_continuity.py")
    function_source = source.split("def detect_record_conflicts_and_duplicates(", 1)[1]
    match = re.search(
        r"SELECT\s+(.*?)\s+FROM\s+health_metrics\s+WHERE\s+user_id=\?"
        r"\s+GROUP\s+BY\s+(.*?)\s+HAVING\s+COUNT\(\*\)\s*>\s*1",
        function_source,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert match, "Duplicate metrics query must retain its duplicate threshold"
    projection = re.sub(r"\s+", " ", match.group(1).strip()).lower()
    grouping = re.sub(r"\s+", " ", match.group(2).strip()).lower()
    assert projection == "metric_type, recorded_at, count(*) as cnt"
    assert grouping == "metric_type, recorded_at"
    assert "metric_value" not in projection and "unit" not in projection


def test_low_memory_aws_documentation_uses_effective_gunicorn_setting():
    instructions = _source("docs/AWS_EC2_VERCEL_LAUNCH.md")
    config = _source("gunicorn.conf.py")
    assert "ZENDOC_GUNICORN_WORKERS=1" in instructions
    assert "WEB_CONCURRENCY=1" not in instructions
    assert '_int("ZENDOC_GUNICORN_WORKERS", 2' in config


def test_backup_host_directory_matches_unprivileged_container_uid():
    instructions = _source("docs/AWS_EC2_VERCEL_LAUNCH.md")
    dockerfile = _source("deploy/aws/backup.Dockerfile")
    compose = _source("deploy/aws/compose.yaml")
    assert "sudo install -d -o 10001 -g 10001 -m 0700 /var/backups/zendoc" in instructions
    assert "USER zendocbackup:zendocbackup" in dockerfile
    assert "useradd --system --uid 10001" in dockerfile
    assert "/var/backups/zendoc:/backups" in compose
