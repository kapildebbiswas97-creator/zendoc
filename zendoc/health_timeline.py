from .db import get_db, now_iso
from .health_access import authorize_patient


TIMELINE_TYPES = (
    "appointment", "consultation", "report", "medical_record", "measurement", "medication",
    "vaccination", "procedure", "ai_health_event", "mental_wellness", "fitness",
)
FILTER_ALIASES = {"appointments": "appointment", "reports": "report", "records": "medical_record", "measurements": "measurement", "medications": "medication", "ai": "ai_health_event", "workouts": "fitness", "workout": "fitness"}


EVENTS_SQL = """
WITH events AS (
    SELECT 'appointment' event_type, a.scheduled_for event_at,
           'Appointment with ' || a.provider_name title,
           a.reason || ' - Status: ' || a.status summary,
           a.provider_name provider_name, 'appointments' source, CAST(a.id AS TEXT) source_id
    FROM appointments a WHERE a.patient_id=?
    UNION ALL
    SELECT CASE WHEN rm.id IS NULL THEN 'medical_record' ELSE 'report' END event_type,
           COALESCE(rm.document_date,mr.created_at) event_at, mr.title title,
           COALESCE(rm.description,mr.category) summary,
           COALESCE(rm.provider_name,rm.lab_name) provider_name,
           'medical_records' source, CAST(mr.id AS TEXT) source_id
    FROM medical_records mr LEFT JOIN report_metadata rm ON rm.record_id=mr.id
    WHERE mr.owner_id=?
    UNION ALL
    SELECT 'measurement' event_type, hm.recorded_at event_at,
           REPLACE(hm.metric_type,'_',' ') title,
           hm.metric_value || CASE WHEN COALESCE(hm.unit,'')='' THEN '' ELSE ' ' || hm.unit END summary,
           NULL provider_name, 'health_metrics' source, CAST(hm.id AS TEXT) source_id
    FROM health_metrics hm WHERE hm.user_id=?
    UNION ALL
    SELECT 'ai_health_event' event_type, ai.created_at event_at,
           'ZENDOC AI: ' || REPLACE(COALESCE(ai.intent,ai.feature),'_',' ') title,
           SUBSTR(ai.input_text,1,240) summary, NULL provider_name,
           'ai_interactions' source, CAST(ai.id AS TEXT) source_id
    FROM ai_interactions ai
    WHERE ai.user_id=? AND COALESCE(ai.intent,ai.feature) IN
      ('symptoms','emergency','medical_report','report_intelligence','report_history',
       'health_records','health_timeline','health_analytics','health_monitoring')
    UNION ALL
    SELECT hte.event_type, hte.event_at, hte.title, hte.summary, hte.provider_name,
           hte.source, CAST(hte.id AS TEXT) source_id
    FROM health_timeline_events hte WHERE hte.patient_id=?
)
"""


def _where_clause(event_type=None, query=None, start_date=None, end_date=None):
    conditions = []
    params = []
    normalized = FILTER_ALIASES.get(str(event_type or "").lower(), str(event_type or "").lower())
    if normalized and normalized != "all":
        if normalized not in TIMELINE_TYPES:
            raise ValueError("Timeline event filter is invalid.")
        conditions.append("event_type=?")
        params.append(normalized)
    if query:
        text = f"%{str(query).strip().lower()[:200]}%"
        conditions.append("(LOWER(title) LIKE ? OR LOWER(COALESCE(summary,'')) LIKE ? OR LOWER(COALESCE(provider_name,'')) LIKE ? OR LOWER(event_at) LIKE ?)")
        params.extend([text, text, text, text])
    if start_date:
        conditions.append("event_at>=?")
        params.append(str(start_date))
    if end_date:
        conditions.append("event_at<?")
        params.append(f"{end_date}T23:59:59.999999+00:00")
    return (" WHERE " + " AND ".join(conditions)) if conditions else "", params


def _details_path(item):
    if item["source"] == "appointments":
        return "/appointments"
    if item["source"] == "medical_records":
        return f"/reports/{item['source_id']}" if item["event_type"] == "report" else "/records"
    if item["source"] == "health_metrics":
        return "/health"
    if item["source"] == "ai_interactions":
        return "/ai"
    return None


def list_timeline(actor, patient_id=None, event_type=None, query=None, order="desc", page=1, per_page=25, start_date=None, end_date=None):
    target_id = authorize_patient(actor, patient_id, "timeline")
    order = str(order or "desc").lower()
    if order not in {"asc", "desc"}:
        raise ValueError("Timeline order must be asc or desc.")
    page = max(1, int(page or 1))
    per_page = max(1, min(int(per_page or 25), 100))
    where, filter_params = _where_clause(event_type, query, start_date, end_date)
    owner_params = [target_id] * 5
    db = get_db()
    total = db.execute(EVENTS_SQL + "SELECT COUNT(*) count FROM events" + where, tuple(owner_params + filter_params)).fetchone()["count"]
    rows = db.execute(
        EVENTS_SQL + f"SELECT * FROM events{where} ORDER BY event_at {order.upper()}, source_id {order.upper()} LIMIT ? OFFSET ?",
        tuple(owner_params + filter_params + [per_page, (page - 1) * per_page]),
    ).fetchall()
    events = []
    for row in rows:
        item = dict(row)
        item["id"] = f"{item['source']}:{item['source_id']}"
        item["details_url"] = _details_path(item)
        events.append(item)
    return {"events": events, "page": page, "per_page": per_page, "total": total, "order": order}


def add_timeline_event(patient_id, event_type, title, event_at=None, summary=None, provider_name=None, source="zendoc", source_ref=None, created_by=None):
    normalized = str(event_type or "").strip().lower()
    if normalized not in TIMELINE_TYPES:
        raise ValueError("Timeline event type is invalid.")
    cursor = get_db().execute(
        """
        INSERT INTO health_timeline_events
        (patient_id,event_type,event_at,title,summary,provider_name,source,source_ref,created_by,created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
        (patient_id, normalized, event_at or now_iso(), str(title)[:180], str(summary or "")[:1000] or None, str(provider_name or "")[:160] or None, str(source)[:80], str(source_ref or "")[:120] or None, created_by, now_iso()),
    )
    get_db().commit()
    return cursor.lastrowid

