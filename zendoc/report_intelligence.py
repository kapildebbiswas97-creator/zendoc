import re
import secrets
import uuid
from datetime import date
from pathlib import Path

from flask import current_app
from werkzeug.utils import secure_filename

from .db import get_db, now_iso
from .health_access import authorize_patient


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
    stored = f"{secrets.token_hex(16)}-{original}"
    upload_root = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
    destination = (upload_root / stored).resolve()
    if destination.parent != upload_root:
        raise ValueError("Upload destination is invalid.")
    upload.save(destination)
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
                stored,
                upload.mimetype,
                destination.stat().st_size,
                now_iso(),
            ),
        )
        record_id = cursor.lastrowid
        create_report_metadata(record_id, data)
        return record_id
    except Exception:
        destination.unlink(missing_ok=True)
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


def get_report_result_trend(actor, test_name, patient_id=None):
    target_id = authorize_patient(actor, patient_id, "reports")
    clean_name = str(test_name or "").strip()
    if not clean_name:
        raise ValueError("test_name is required.")
    rows = get_db().execute(
        """
        SELECT rr.test_name, rr.numeric_value, rr.unit, rr.measurement_date, rr.abnormal_flag,
               mr.id record_id, mr.title report_title
        FROM report_results rr JOIN medical_records mr ON mr.id=rr.record_id
        WHERE mr.owner_id=? AND LOWER(rr.test_name)=LOWER(?) AND rr.numeric_value IS NOT NULL
        ORDER BY rr.measurement_date ASC, rr.id ASC LIMIT 1000
        """,
        (target_id, clean_name),
    ).fetchall()
    grouped = {}
    for row in rows:
        unit = row["unit"] or "unitless"
        grouped.setdefault(unit, []).append(dict(row))
    return {
        "test_name": clean_name,
        "series": [{"unit": unit, "points": points} for unit, points in grouped.items()],
        "unit_mismatch": len(grouped) > 1,
        "message": "Results with different units are kept in separate series." if len(grouped) > 1 else None,
    }
