import re
import uuid
from datetime import date

from werkzeug.utils import secure_filename

from .db import get_db, now_iso
from .health_access import authorize_patient
from .record_storage import get_record_storage


REPORT_TYPES = (
    "blood_test", "urine_test", "imaging", "x_ray", "ct", "mri", "ultrasound",
    "ecg", "pathology", "prescription", "discharge_summary", "other",
)
ABNORMAL_FLAGS = ("unknown", "normal", "low", "high", "abnormal")
UPLOAD_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "txt", "doc", "docx"}
MIME_TYPES = {
    "application/pdf", "image/png", "image/jpeg", "text/plain", "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/octet-stream",
}


def _value(actor, key, default=None):
    if hasattr(actor, "keys") and key in actor.keys():
        return actor[key]
    return actor.get(key, default) if isinstance(actor, dict) else default


def normalize_report_type(value):
    report_type = str(value or "other").strip().lower().replace("-", "_").replace(" ", "_")
    if not re.fullmatch(r"[a-z0-9_]{2,80}", report_type):
        raise ValueError("Report type is invalid.")
    return report_type


def _optional_date(value, label):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except ValueError as error:
        raise ValueError(f"{label} must use YYYY-MM-DD.") from error


def validate_report_upload(upload):
    if not upload or not upload.filename:
        raise ValueError("Select a report file to upload.")
    original = secure_filename(upload.filename)
    if not original or "." not in original:
        raise ValueError("Upload filename is invalid.")
    extension = original.rsplit(".", 1)[1].lower()
    if extension not in UPLOAD_EXTENSIONS:
        raise ValueError("Upload a valid PDF, image, DOC, DOCX, or TXT file.")
    mimetype = (upload.mimetype or "").lower()
    if mimetype and mimetype not in MIME_TYPES:
        raise ValueError("The uploaded file type does not match an allowed medical document format.")
    header = upload.stream.read(2048)
    upload.stream.seek(0)
    if not header:
        raise ValueError("The uploaded file is empty.")
    signatures = {
        "pdf": header.startswith(b"%PDF-"),
        "png": header.startswith(b"\x89PNG\r\n\x1a\n"),
        "jpg": header.startswith(b"\xff\xd8\xff"),
        "jpeg": header.startswith(b"\xff\xd8\xff"),
        "doc": header.startswith(b"\xd0\xcf\x11\xe0"),
        "docx": header.startswith(b"PK\x03\x04"),
    }
    if extension in signatures and not signatures[extension]:
        raise ValueError("The file content does not match its extension.")
    if extension == "txt":
        try:
            header.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError("Text reports must use UTF-8 encoding.") from error
    return original


def store_report_upload(upload, owner_id, uploaded_by, data):
    original = validate_report_upload(upload)
    storage = get_record_storage()
    stored_record = storage.save(upload, original)
    try:
        cursor = get_db().execute(
            """
            INSERT INTO medical_records
            (owner_id,uploaded_by,title,category,original_filename,stored_filename,mime_type,file_size,created_at)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                owner_id,
                uploaded_by,
                str(data.get("title") or original).strip()[:180],
                str(data.get("category") or data.get("report_type") or "Report").strip()[:80],
                original,
                stored_record.storage_key,
                upload.mimetype,
                stored_record.size_bytes,
                now_iso(),
            ),
        )
        record_id = cursor.lastrowid
        create_report_metadata(record_id, data)
        return record_id
    except Exception:
        storage.delete(stored_record.storage_key)
        raise


def create_report_metadata(record_id, data):
    record = get_db().execute("SELECT * FROM medical_records WHERE id=?", (record_id,)).fetchone()
    if not record:
        raise LookupError("Medical record not found.")
    now = now_iso()
    get_db().execute(
        """
        INSERT INTO report_metadata
        (record_id,report_uid,report_type,document_date,provider_name,lab_name,description,
         extraction_status,extraction_message,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,'unavailable','Automatic extraction unavailable for this document.',?,?)
        ON CONFLICT(record_id) DO UPDATE SET
          report_type=excluded.report_type, document_date=excluded.document_date,
          provider_name=excluded.provider_name, lab_name=excluded.lab_name,
          description=excluded.description, updated_at=excluded.updated_at
        """,
        (
            record_id,
            f"ZR-{uuid.uuid4().hex.upper()}",
            normalize_report_type(data.get("report_type") or data.get("category") or "other"),
            _optional_date(data.get("document_date"), "Document date"),
            str(data.get("provider_name") or "").strip()[:160] or None,
            str(data.get("lab_name") or "").strip()[:160] or None,
            str(data.get("description") or "").strip()[:2000] or None,
            now,
            now,
        ),
    )


def _report_query():
    return """
        SELECT mr.*, rm.report_uid, rm.report_type, rm.document_date, rm.provider_name,
               rm.lab_name, rm.description, rm.extraction_status, rm.extraction_message,
               rm.created_at metadata_created_at, rm.updated_at metadata_updated_at
        FROM medical_records mr LEFT JOIN report_metadata rm ON rm.record_id=mr.id
    """


def serialize_report(row):
    item = dict(row)
    item["report_id"] = item.get("report_uid") or f"LEGACY-{item['id']}"
    item["report_type"] = item.get("report_type") or normalize_report_type(item.get("category") or "other")
    item["document_date"] = item.get("document_date") or item.get("created_at")
    item["uploaded_at"] = item.get("created_at")
    item["extraction_status"] = item.get("extraction_status") or "unavailable"
    item["extraction_message"] = item.get("extraction_message") or "Automatic extraction unavailable for this document."
    item.pop("stored_filename", None)
    return item


def list_reports(actor, patient_id=None, page=1, per_page=25):
    target_id = authorize_patient(actor, patient_id, "reports")
    page = max(1, int(page or 1))
    per_page = max(1, min(int(per_page or 25), 100))
    total = get_db().execute("SELECT COUNT(*) count FROM medical_records WHERE owner_id=?", (target_id,)).fetchone()["count"]
    rows = get_db().execute(
        _report_query() + " WHERE mr.owner_id=? ORDER BY COALESCE(rm.document_date,mr.created_at) DESC LIMIT ? OFFSET ?",
        (target_id, per_page, (page - 1) * per_page),
    ).fetchall()
    return {"reports": [serialize_report(row) for row in rows], "page": page, "per_page": per_page, "total": total}


def get_report(actor, record_id):
    row = get_db().execute(_report_query() + " WHERE mr.id=?", (record_id,)).fetchone()
    if not row:
        raise LookupError("Report not found.")
    authorize_patient(actor, row["owner_id"], "reports")
    return serialize_report(row)


def get_report_file(actor, record_id):
    row = get_db().execute("SELECT * FROM medical_records WHERE id=?", (record_id,)).fetchone()
    if not row:
        raise LookupError("Report not found.")
    authorize_patient(actor, row["owner_id"], "reports")
    return dict(row)


def list_report_results(actor, record_id):
    get_report(actor, record_id)
    rows = get_db().execute(
        "SELECT * FROM report_results WHERE record_id=? ORDER BY measurement_date,test_name,id",
        (record_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def add_report_result(actor, record_id, data):
    report = get_report(actor, record_id)
    test_name = str(data.get("test_name") or "").strip()[:160]
    value = str(data.get("value") or data.get("value_text") or "").strip()[:120]
    if not test_name or not value:
        raise ValueError("Test name and value are required.")
    numeric_value = None
    try:
        numeric_value = float(value)
    except ValueError:
        pass
    abnormal_flag = str(data.get("abnormal_flag") or "unknown").strip().lower()
    if abnormal_flag not in ABNORMAL_FLAGS:
        raise ValueError("Abnormal flag must be unknown, normal, low, high, or abnormal.")
    role = _value(actor, "role")
    source = "clinical" if role in {"doctor", "hospital"} else "manual"
    cursor = get_db().execute(
        """
        INSERT INTO report_results
        (record_id,test_name,value_text,numeric_value,unit,reference_range,abnormal_flag,
         measurement_date,source,created_by,created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            record_id, test_name, value, numeric_value, str(data.get("unit") or "").strip()[:40] or None,
            str(data.get("reference_range") or "").strip()[:120] or None, abnormal_flag,
            _optional_date(data.get("measurement_date") or str(report["document_date"] or "")[:10], "Measurement date"),
            source, _value(actor, "id"), now_iso(),
        ),
    )
    return cursor.lastrowid


def explain_report(actor, record_id):
    report = get_report(actor, record_id)
    results = list_report_results(actor, record_id)
    if not results:
        return {
            "report_id": report["report_id"],
            "status": "unavailable",
            "message": report["extraction_message"],
            "results": [],
            "disclaimer": "ZENDOC has not interpreted or diagnosed this document. Discuss medical reports with a qualified clinician.",
        }
    flagged = [item for item in results if item["abnormal_flag"] in {"low", "high", "abnormal"}]
    message = f"This report contains {len(results)} stored result{'s' if len(results) != 1 else ''}."
    if flagged:
        message += f" {len(flagged)} result{'s are' if len(flagged) != 1 else ' is'} marked outside the supplied reference information."
    else:
        message += " No stored result is marked outside the supplied reference information."
    return {
        "report_id": report["report_id"],
        "status": "structured_results_available",
        "message": message,
        "results": results,
        "disclaimer": "This is a patient-friendly summary of stored values, not a diagnosis. Confirm results and ranges with a qualified clinician.",
    }


def latest_report(actor, patient_id=None, report_type=None):
    listing = list_reports(actor, patient_id, page=1, per_page=100)
    if not report_type:
        return listing["reports"][0] if listing["reports"] else None
    wanted = normalize_report_type(report_type)
    return next((item for item in listing["reports"] if item["report_type"] == wanted), None)


STANDARD_BIOMARKERS = {
    "glucose": {
        "canonical_name": "Fasting Blood Glucose",
        "standard_unit": "mg/dL",
        "aliases": ["glucose", "fbs", "fasting blood glucose", "fasting blood sugar", "blood sugar"],
        "normal_range": (70.0, 99.0),
        "critical_low": 50.0,
        "critical_high": 300.0,
        "conversions": {
            "mmol/l": lambda val: val * 18.0182,
        },
        "description": "Fasting blood sugar measures glucose levels after an overnight fast. Normal fasting levels are typically 70-99 mg/dL.",
        "clinician_questions": [
            "Are there dietary or physical activity modifications recommended for this glucose level?",
            "Would you recommend repeating this test or evaluating an HbA1c to assess longer-term glycemic control?",
        ],
    },
    "hba1c": {
        "canonical_name": "Hemoglobin A1c (HbA1c)",
        "standard_unit": "%",
        "aliases": ["hba1c", "glycated hemoglobin", "a1c"],
        "normal_range": (4.0, 5.6),
        "critical_low": 3.5,
        "critical_high": 12.0,
        "conversions": {
            "mmol/mol": lambda val: (val * 0.09148) + 2.152,
        },
        "description": "HbA1c reflects average blood sugar levels over the past 2 to 3 months. Guidelines consider values under 5.7% normal.",
        "clinician_questions": [
            "What target HbA1c range is most appropriate for my personal profile?",
            "When should we next monitor my HbA1c?",
        ],
    },
    "cholesterol": {
        "canonical_name": "Total Cholesterol",
        "standard_unit": "mg/dL",
        "aliases": ["cholesterol", "total cholesterol", "serum cholesterol"],
        "normal_range": (120.0, 199.0),
        "critical_low": 90.0,
        "critical_high": 350.0,
        "conversions": {
            "mmol/l": lambda val: val * 38.67,
        },
        "description": "Total blood cholesterol includes LDL, HDL, and other lipid components. Desirable levels are generally below 200 mg/dL.",
        "clinician_questions": [
            "How does my total cholesterol relate to my overall cardiovascular risk score?",
            "Should we evaluate a complete lipid panel (LDL, HDL, triglycerides)?",
        ],
    },
    "creatinine": {
        "canonical_name": "Serum Creatinine",
        "standard_unit": "mg/dL",
        "aliases": ["creatinine", "serum creatinine", "sr creatinine"],
        "normal_range": (0.6, 1.2),
        "critical_low": 0.3,
        "critical_high": 4.0,
        "conversions": {
            "umol/l": lambda val: val / 88.42,
            "µmol/l": lambda val: val / 88.42,
        },
        "description": "Creatinine is a waste product filtered by the kidneys. Reference ranges typically span 0.6 to 1.2 mg/dL.",
        "clinician_questions": [
            "Is my estimated glomerular filtration rate (eGFR) in a healthy range?",
            "Could hydration status or recent exertion have influenced this result?",
        ],
    },
    "hemoglobin": {
        "canonical_name": "Hemoglobin",
        "standard_unit": "g/dL",
        "aliases": ["hemoglobin", "hb", "haemoglobin"],
        "normal_range": (12.0, 17.5),
        "critical_low": 7.0,
        "critical_high": 20.0,
        "conversions": {
            "g/l": lambda val: val / 10.0,
        },
        "description": "Hemoglobin is the oxygen-carrying protein in red blood cells. Normal adult ranges are generally 12.0-17.5 g/dL.",
        "clinician_questions": [
            "Could nutritional factors (such as iron, B12, or folate) be relevant to this hemoglobin level?",
            "Are follow-up red blood cell indices recommended?",
        ],
    },
    "spo2": {
        "canonical_name": "Oxygen Saturation (SpO2)",
        "standard_unit": "%",
        "aliases": ["spo2", "oxygen saturation", "pulse oximetry"],
        "normal_range": (95.0, 100.0),
        "critical_low": 90.0,
        "critical_high": 100.0,
        "conversions": {},
        "description": "Oxygen saturation measures the percentage of oxygen carried in arterial blood. Healthy room-air levels are 95% or higher.",
        "clinician_questions": [
            "If SpO2 drops below 95%, what immediate steps or clinical evaluation are recommended?",
        ],
    },
    "blood_pressure_systolic": {
        "canonical_name": "Systolic Blood Pressure",
        "standard_unit": "mmHg",
        "aliases": ["systolic", "systolic bp", "systolic blood pressure", "bpsys"],
        "normal_range": (90.0, 119.0),
        "critical_low": 80.0,
        "critical_high": 180.0,
        "conversions": {},
        "description": "Systolic blood pressure measures arterial pressure when the heart beats. Normal adult resting pressure is under 120 mmHg.",
        "clinician_questions": [
            "Should I keep an ambulatory home blood pressure log over 7 to 14 days?",
            "What lifestyle or medication adjustments are recommended?",
        ],
    },
}


def lookup_biomarker_definition(test_name: str | None) -> dict | None:
    if not test_name:
        return None
    cleaned = str(test_name).strip().lower()
    for key, meta in STANDARD_BIOMARKERS.items():
        if cleaned == key or cleaned in meta["aliases"]:
            return meta
        for alias in meta["aliases"]:
            if alias in cleaned or cleaned in alias:
                return meta
    return None


def normalize_biomarker_value(test_name: str | None, value: float | int | None, unit: str | None) -> tuple[float | None, str | None, dict | None]:
    meta = lookup_biomarker_definition(test_name)
    if value is None or not meta:
        return value, unit, meta
    clean_unit = str(unit or "").strip().lower()
    std_unit = meta["standard_unit"]
    if clean_unit and clean_unit in meta.get("conversions", {}):
        converter = meta["conversions"][clean_unit]
        try:
            converted = round(converter(float(value)), 2)
            return converted, std_unit, meta
        except Exception:
            pass
    return value, unit, meta


def calculate_biomarker_longitudinal_trend(series_points: list[dict], biomarker_meta: dict | None = None) -> dict:
    """
    Computes delta, rate of change, direction, educational non-diagnostic context,
    red flags, and questions for the clinician.
    """
    if not series_points:
        return {
            "status": "NO_DATA",
            "trend_direction": "NONE",
            "points_count": 0,
            "disclaimer": "ZENDOC does not independently diagnose conditions or prescribe treatments.",
        }

    # Sort chronologically
    sorted_pts = sorted(series_points, key=lambda p: (str(p.get("measurement_date") or ""), p.get("id") or 0))
    valid_pts = [p for p in sorted_pts if p.get("numeric_value") is not None]
    if not valid_pts:
        return {
            "status": "INSUFFICIENT_NUMERIC_DATA",
            "trend_direction": "NONE",
            "points_count": len(series_points),
            "disclaimer": "ZENDOC does not independently diagnose conditions or prescribe treatments.",
        }

    latest = valid_pts[-1]
    latest_val = float(latest["numeric_value"])
    previous = valid_pts[-2] if len(valid_pts) > 1 else None
    baseline = valid_pts[0]

    delta = None
    pct_change = None
    trend_dir = "STABLE"
    if previous:
        prev_val = float(previous["numeric_value"])
        delta = round(latest_val - prev_val, 2)
        if prev_val != 0:
            pct_change = round((delta / prev_val) * 100.0, 1)
        if delta > 0.05 * prev_val:
            trend_dir = "RISING"
        elif delta < -0.05 * prev_val:
            trend_dir = "FALLING"
        else:
            trend_dir = "STABLE"

    red_flag = False
    red_flag_reason = None
    if biomarker_meta:
        crit_low = biomarker_meta.get("critical_low")
        crit_high = biomarker_meta.get("critical_high")
        if crit_low is not None and latest_val < crit_low:
            red_flag = True
            red_flag_reason = f"Value {latest_val} is below critical threshold ({crit_low}). Urgent medical consultation recommended."
        elif crit_high is not None and latest_val > crit_high:
            red_flag = True
            red_flag_reason = f"Value {latest_val} exceeds critical threshold ({crit_high}). Urgent medical consultation recommended."

    educational_summary = None
    if biomarker_meta:
        ref_low, ref_high = biomarker_meta.get("normal_range", (None, None))
        if ref_low is not None and ref_high is not None:
            if latest_val < ref_low:
                status_desc = f"below standard adult reference range ({ref_low} - {ref_high} {latest.get('unit') or ''})"
            elif latest_val > ref_high:
                status_desc = f"above standard adult reference range ({ref_low} - {ref_high} {latest.get('unit') or ''})"
            else:
                status_desc = f"within standard adult reference range ({ref_low} - {ref_high} {latest.get('unit') or ''})"
            educational_summary = f"Most recent result ({latest_val}) is {status_desc}."

    return {
        "status": "ANALYZED",
        "points_count": len(valid_pts),
        "latest": {
            "value": latest_val,
            "date": latest.get("measurement_date"),
            "unit": latest.get("unit"),
            "abnormal_flag": latest.get("abnormal_flag"),
        },
        "previous": {
            "value": float(previous["numeric_value"]) if previous else None,
            "date": previous.get("measurement_date") if previous else None,
        } if previous else None,
        "delta": delta,
        "percent_change": pct_change,
        "trend_direction": trend_dir,
        "red_flag": red_flag,
        "red_flag_reason": red_flag_reason,
        "educational_summary": educational_summary,
        "clinician_questions": biomarker_meta.get("clinician_questions", []) if biomarker_meta else [
            "Are there factors that explain changes in these lab values?",
            "What follow-up timeline or re-testing frequency is advised?",
        ],
        "non_diagnostic_guarantee": (
            "Educational health interpretation only. ZENDOC does not independently diagnose "
            "disease or prescribe medical treatments. Discuss all trends with a licensed physician."
        ),
    }


def get_report_result_trend(actor, test_name, patient_id=None):
    target_id = authorize_patient(actor, patient_id, "reports")
    clean_name = str(test_name or "").strip()
    if not clean_name:
        raise ValueError("test_name is required.")
    rows = get_db().execute(
        """
        SELECT rr.test_name, rr.numeric_value, rr.unit, rr.measurement_date, rr.abnormal_flag,
               mr.id record_id, mr.title report_title, rr.id
        FROM report_results rr JOIN medical_records mr ON mr.id=rr.record_id
        WHERE mr.owner_id=? AND LOWER(rr.test_name)=LOWER(?) AND rr.numeric_value IS NOT NULL
        ORDER BY rr.measurement_date ASC, rr.id ASC LIMIT 1000
        """,
        (target_id, clean_name),
    ).fetchall()
    grouped = {}
    all_points = []
    for row in rows:
        item = dict(row)
        unit = item.get("unit") or "unitless"
        grouped.setdefault(unit, []).append(item)
        all_points.append(item)

    biomarker_meta = lookup_biomarker_definition(clean_name)
    longitudinal_analysis = calculate_biomarker_longitudinal_trend(all_points, biomarker_meta)

    return {
        "test_name": clean_name,
        "canonical_name": biomarker_meta["canonical_name"] if biomarker_meta else clean_name,
        "series": [{"unit": unit, "points": points} for unit, points in grouped.items()],
        "unit_mismatch": len(grouped) > 1,
        "message": "Results with different units are kept in separate series." if len(grouped) > 1 else None,
        "longitudinal_analysis": longitudinal_analysis,
        "biomarker_meta": {
            "canonical_name": biomarker_meta["canonical_name"],
            "standard_unit": biomarker_meta["standard_unit"],
            "normal_range": biomarker_meta["normal_range"],
            "description": biomarker_meta["description"],
        } if biomarker_meta else None,
        "clinical_discussion_prompts": longitudinal_analysis["clinician_questions"],
        "non_diagnostic_guarantee": longitudinal_analysis["non_diagnostic_guarantee"],
    }
