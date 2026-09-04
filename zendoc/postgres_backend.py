"""Small DB-API compatibility adapter for ZENDOC's PostgreSQL transition.

The application still uses parameterized SQL directly.  This adapter keeps the
existing SQLite path stable while translating the narrow SQLite DB-API surface
used by ZENDOC to psycopg.  Credentials are never included in status output.
"""
from __future__ import annotations

import re


LASTROWID_TABLES = {
    "agent_actions",
    "agent_alerts",
    "agent_approvals",
    "agent_runs",
    "agent_task_attempts",
    "agent_tasks",
    "agent_tool_calls",
    "ai_conversations",
    "ai_interactions",
    "ambulance_requests",
    "api_tokens",
    "appointments",
    "audit_logs",
    "communication_permissions",
    "consultation_messages",
    "consultation_requests",
    "consultation_rooms",
    "conversations",
    "duplicate_account_groups",
    "exercises",
    "family_access_grants",
    "family_care_tasks",
    "family_members",
    "fitness_pose_feedback",
    "fitness_pose_sessions",
    "health_access_grants",
    "health_devices",
    "health_metrics",
    "health_timeline_events",
    "home_health_requests",
    "hydration_logs",
    "medical_records",
    "medicine_orders",
    "medicine_reminders",
    "message_attachments",
    "messages",
    "model_evaluation_results",
    "model_evaluation_runs",
    "model_execution_logs",
    "notification_deliveries",
    "notifications",
    "nutrition_logs",
    "platform_events",
    "provider_profiles",
    "provider_schedules",
    "report_metadata",
    "report_results",
    "saved_locations",
    "staff_profiles",
    "staff_task_events",
    "staff_tasks",
    "users",
    "video_search_history",
    "consent_grants",
    "diagnostic_bookings",
    "diagnostic_catalog",
    "diagnostic_offers",
    "fulfilment_plan_items",
    "fulfilment_plans",
    "inventory_observations",
    "medication_skus",
    "order_events",
    "prescription_items",
    "prescriptions",
    "verified_reviews",
    "workout_plan_items",
    "workout_plans",
    "workout_session_items",
    "workout_sessions",
    "workout_set_logs",
}


def _replace_qmark_parameters(sql: str) -> str:
    output = []
    in_single = False
    in_double = False
    index = 0
    while index < len(sql):
        char = sql[index]
        if char == "'" and not in_double:
            output.append(char)
            if in_single and index + 1 < len(sql) and sql[index + 1] == "'":
                output.append("'")
                index += 2
                continue
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
            output.append(char)
        elif char == "?" and not in_single and not in_double:
            output.append("%s")
        else:
            output.append(char)
        index += 1
    return "".join(output)


def translate_sql(sql: str, *, return_inserted_id: bool = True) -> tuple[str, bool]:
    """Translate the SQLite-compatible subset used by application queries."""
    translated = str(sql)
    translated = re.sub(r"\bBEGIN\s+IMMEDIATE\b", "BEGIN", translated, flags=re.IGNORECASE)
    translated = re.sub(
        r"\bINTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b",
        "BIGSERIAL PRIMARY KEY",
        translated,
        flags=re.IGNORECASE,
    )
    translated = re.sub(
        r"\bINTEGER(\s+[^,;()]*\bREFERENCES\b)",
        r"BIGINT\1",
        translated,
        flags=re.IGNORECASE,
    )
    translated = re.sub(r"\bAUTOINCREMENT\b", "", translated, flags=re.IGNORECASE)

    # Translate SQLite datetime('now') expressions to PostgreSQL CURRENT_TIMESTAMP
    translated = re.sub(
        r"\bdatetime\s*\(\s*'now'\s*,\s*'([+-]?\d+\s+[a-zA-Z]+)'\s*\)",
        r"(CURRENT_TIMESTAMP + INTERVAL '\1')",
        translated,
        flags=re.IGNORECASE,
    )
    translated = re.sub(
        r"\bdatetime\s*\(\s*'now'\s*(?:,\s*'localtime')?\s*\)",
        "CURRENT_TIMESTAMP",
        translated,
        flags=re.IGNORECASE,
    )

    ignore_insert = bool(re.search(r"^\s*INSERT\s+OR\s+IGNORE\s+INTO\b", translated, re.IGNORECASE))
    if ignore_insert:
        translated = re.sub(
            r"^\s*INSERT\s+OR\s+IGNORE\s+INTO\b",
            "INSERT INTO",
            translated,
            count=1,
            flags=re.IGNORECASE,
        )
        translated = translated.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"

    table_match = re.search(r"^\s*INSERT\s+INTO\s+([A-Za-z_][A-Za-z0-9_]*)", translated, re.IGNORECASE)
    wants_lastrowid = bool(
        return_inserted_id
        and table_match
        and table_match.group(1).lower() in LASTROWID_TABLES
        and not re.search(r"\bRETURNING\b", translated, re.IGNORECASE)
    )
    if wants_lastrowid:
        translated = translated.rstrip().rstrip(";") + " RETURNING id"

    return _replace_qmark_parameters(translated), wants_lastrowid


def split_sql_script(script: str) -> list[str]:
    statements = []
    current = []
    in_single = False
    in_double = False
    index = 0
    while index < len(script):
        char = script[index]
        if char == "'" and not in_double:
            current.append(char)
            if in_single and index + 1 < len(script) and script[index + 1] == "'":
                current.append("'")
                index += 2
                continue
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
            current.append(char)
        elif char == ";" and not in_single and not in_double:
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
        else:
            current.append(char)
        index += 1
    final = "".join(current).strip()
    if final:
        statements.append(final)
    return statements


class PostgreSQLCursor:
    def __init__(self, cursor, lastrowid=None):
        self._cursor = cursor
        self.lastrowid = lastrowid

    @property
    def rowcount(self):
        return self._cursor.rowcount

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()


class PostgreSQLConnection:
    dialect = "postgresql"

    def __init__(self, connection):
        self._connection = connection

    def execute(self, sql, params=()):
        translated, returns_id = translate_sql(sql)
        cursor = self._connection.execute(translated, tuple(params or ()))
        inserted_id = None
        if returns_id:
            row = cursor.fetchone()
            if row:
                inserted_id = row.get("id") if hasattr(row, "get") else row[0]
        return PostgreSQLCursor(cursor, inserted_id)

    def executescript(self, script):
        cursor = None
        for statement in split_sql_script(script):
            cursor = self.execute(statement)
        return cursor

    def commit(self):
        self._connection.commit()

    def rollback(self):
        self._connection.rollback()

    def close(self):
        self._connection.close()


def connect_postgresql(database_url):
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as error:  # pragma: no cover - exercised only in a misbuilt deployment
        raise RuntimeError(
            "PostgreSQL is configured but the psycopg driver is unavailable. Install project requirements."
        ) from error

    url = str(database_url).replace("postgresql+psycopg://", "postgresql://", 1)
    connection = psycopg.connect(url, row_factory=dict_row, connect_timeout=10)
    return PostgreSQLConnection(connection)


def is_postgresql_integrity_error(error):
    sqlstate = str(getattr(error, "sqlstate", "") or "")
    return sqlstate.startswith("23")
