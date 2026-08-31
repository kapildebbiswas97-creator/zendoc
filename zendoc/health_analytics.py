from datetime import datetime, timedelta, timezone

from .db import get_db, now_iso
from .health_access import authorize_patient


METRIC_TYPES = (
    "weight", "height", "bmi", "blood_pressure", "heart_rate", "blood_glucose",
    "oxygen_saturation", "temperature", "sleep", "water_intake", "steps",
)
DEFAULT_UNITS = {
    "weight": "kg", "height": "cm", "bmi": "kg/m2", "blood_pressure": "mmHg",
    "heart_rate": "bpm", "blood_glucose": "mg/dL", "oxygen_saturation": "%",
    "temperature": "C", "sleep": "hours", "water_intake": "L", "steps": "steps",
}
PERIOD_DAYS = {"7d": 7, "30d": 30, "90d": 90}


def _value(actor, key, default=None):
    if hasattr(actor, "keys") and key in actor.keys():
        return actor[key]
    return actor.get(key, default) if isinstance(actor, dict) else default


def normalize_metric_type(value):
    metric_type = str(value or "").strip().lower().replace(" ", "_").replace("-", "_")
    if not metric_type or len(metric_type) > 80 or not all(char.isalnum() or char == "_" for char in metric_type):
        raise ValueError("Metric type is invalid.")
    return metric_type


def _number(value, label):
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} must be numeric.") from error
    if abs(number) > 10000000:
        raise ValueError(f"{label} is outside the supported range.")
    return number


def _recorded_at(value):
    if not value:
        return now_iso()
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("Measurement date must be a valid ISO date or date-time.") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    if parsed > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise ValueError("Measurement date cannot be in the future.")
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")


def create_measurement(actor, data, patient_id=None, trusted_source=False):
    target_id = authorize_patient(actor, patient_id, "measurements")
    metric_type = normalize_metric_type(data.get("metric_type"))
    primary = data.get("value", data.get("metric_value"))
    if primary in (None, ""):
        raise ValueError("Measurement value is required.")
    numeric_value = _number(primary, "Measurement value")
    secondary_raw = data.get("secondary_value")
    secondary_value = _number(secondary_raw, "Second measurement value") if secondary_raw not in (None, "") else None
    if metric_type == "blood_pressure" and secondary_value is None:
        text_value = str(primary)
        if "/" in text_value:
            systolic, diastolic = text_value.split("/", 1)
            numeric_value = _number(systolic, "Systolic value")
            secondary_value = _number(diastolic, "Diastolic value")
        else:
            raise ValueError("Blood pressure requires systolic and diastolic values.")
    source = str(data.get("source") or "manual").strip().lower()
    actor_role = _value(actor, "role")
    if actor_role == "patient" and source != "manual" and not trusted_source:
        raise ValueError("Patient-entered measurements must use the manual source.")
    if actor_role == "patient" and source not in {"manual", "device", "report", "import"}:
        raise ValueError("Measurement source is not supported.")
    if actor_role in {"doctor", "hospital"} and source not in {"manual", "clinical", "provider"}:
        raise ValueError("Provider-entered measurements must use manual, clinical, or provider source.")
    if actor_role == "admin" and source not in {"manual", "clinical", "provider", "device", "report", "import", "imported", "calculated"}:
        raise ValueError("Measurement source is not supported.")
    unit = str(data.get("unit") or DEFAULT_UNITS.get(metric_type, "")).strip()[:40]
    display_value = f"{numeric_value:g}/{secondary_value:g}" if secondary_value is not None else f"{numeric_value:g}"
    cursor = get_db().execute(
        """
        INSERT INTO health_metrics
        (user_id,metric_type,metric_value,unit,recorded_at,numeric_value,secondary_value,source,notes)
        VALUES (?,?,?,?,?,?,?,?,?)
        """,
        (
            target_id, metric_type, display_value, unit, _recorded_at(data.get("recorded_at")),
            numeric_value, secondary_value, source, str(data.get("notes") or "").strip()[:500] or None,
        ),
    )
    get_db().commit()
    return cursor.lastrowid


def _measurement_dict(row):
    item = dict(row)
    if item.get("numeric_value") is None:
        try:
            item["numeric_value"] = float(str(item.get("metric_value") or "").split("/", 1)[0])
        except ValueError:
            item["numeric_value"] = None
    item["source"] = item.get("source") or "legacy_manual"
    return item


def list_measurements(actor, patient_id=None, metric_type=None, limit=100):
    target_id = authorize_patient(actor, patient_id, "measurements")
    limit = max(1, min(int(limit or 100), 500))
    params = [target_id]
    where = "user_id=?"
    if metric_type:
        where += " AND metric_type=?"
        params.append(normalize_metric_type(metric_type))
    params.append(limit)
    rows = get_db().execute(
        f"SELECT * FROM health_metrics WHERE {where} ORDER BY recorded_at DESC, id DESC LIMIT ?",
        tuple(params),
    ).fetchall()
    return [_measurement_dict(row) for row in rows]


def get_health_trend(actor, metric_type, patient_id=None, period="30d", start_date=None, end_date=None):
    target_id = authorize_patient(actor, patient_id, "measurements")
    metric_type = normalize_metric_type(metric_type)
    if period not in PERIOD_DAYS and period != "custom":
        raise ValueError("Period must be 7d, 30d, 90d, or custom.")
    now = datetime.now(timezone.utc)
    if period == "custom":
        if not start_date or not end_date:
            raise ValueError("Custom trends require start_date and end_date.")
        try:
            start = datetime.fromisoformat(str(start_date)).replace(tzinfo=timezone.utc)
            end = datetime.fromisoformat(str(end_date)).replace(tzinfo=timezone.utc) + timedelta(days=1)
        except ValueError as error:
            raise ValueError("Trend dates must use YYYY-MM-DD.") from error
        if start >= end or end - start > timedelta(days=3660):
            raise ValueError("Custom trend date range is invalid.")
    else:
        end = now + timedelta(seconds=1)
        start = now - timedelta(days=PERIOD_DAYS[period])
    rows = get_db().execute(
        """
        SELECT * FROM health_metrics
        WHERE user_id=? AND metric_type=? AND recorded_at>=? AND recorded_at<?
        ORDER BY recorded_at ASC, id ASC LIMIT 2000
        """,
        (target_id, metric_type, start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds")),
    ).fetchall()
    series_by_unit = {}
    for row in rows:
        item = _measurement_dict(row)
        if item["numeric_value"] is None:
            continue
        unit = item.get("unit") or "unitless"
        series_by_unit.setdefault(unit, []).append(
            {
                "date": item["recorded_at"],
                "value": item["numeric_value"],
                "secondary_value": item.get("secondary_value"),
                "source": item["source"],
            }
        )
    series = []
    for unit, points in series_by_unit.items():
        values = [point["value"] for point in points]
        low, high = min(values), max(values)
        for point in points:
            point["chart_percent"] = 50 if high == low else round(15 + ((point["value"] - low) / (high - low)) * 85, 1)
        direction = "stable"
        if len(points) > 1:
            delta = points[-1]["value"] - points[0]["value"]
            direction = "up" if delta > 0 else "down" if delta < 0 else "stable"
        series.append({"unit": unit, "direction": direction, "points": points})
    return {
        "metric_type": metric_type,
        "period": period,
        "series": series,
        "unit_mismatch": len(series) > 1,
        "message": "Measurements with different units are kept in separate series." if len(series) > 1 else None,
    }


def calculate_bmi(height_cm, weight_kg):
    if not height_cm or not weight_kg:
        return None
    meters = float(height_cm) / 100
    return round(float(weight_kg) / (meters * meters), 1) if meters > 0 else None
