"""Safe medical-document extraction boundary.

Native UTF-8 text extraction is supported. OCR and clinical imaging
interpretation are intentionally separate capabilities and remain unavailable
until concrete validated providers/pipelines are integrated.
"""
from __future__ import annotations

import hashlib

from .db import get_db, now_iso
from .record_storage import get_record_storage
from .report_intelligence import get_report, get_report_file


MAX_NATIVE_TEXT_BYTES = 1_048_576
MAX_NATIVE_TEXT_CHARS = 250_000


def document_extraction_capabilities():
    return {
        "native_utf8_text": {
            "status": "WORKING",
            "formats": ["txt"],
            "max_bytes": MAX_NATIVE_TEXT_BYTES,
        },
        "ocr": {
            "status": "INTEGRATION_REQUIRED",
            "formats": ["pdf", "png", "jpg", "jpeg", "doc", "docx"],
            "description": "No OCR provider is configured; ZENDOC does not fabricate extracted text.",
        },
        "clinical_imaging_interpretation": {
            "status": "DISABLED",
            "modalities": ["x_ray", "ct", "mri", "ultrasound", "imaging"],
            "description": "Image diagnosis/interpretation requires a separately validated specialist clinical pipeline and human governance.",
        },
    }


def _extension(filename):
    name = str(filename or "").strip().lower()
    return name.rsplit(".", 1)[-1] if "." in name else ""


def _normalize_text(raw_text):
    lines = []
    for raw_line in str(raw_text or "").replace("\x00", "").splitlines():
        clean = " ".join(raw_line.split())
        if clean:
            lines.append(clean)
    return "\n".join(lines).strip()


def extract_authorized_native_text(actor, record_id):
    report = get_report(actor, int(record_id))
    stored = get_report_file(actor, int(record_id))
    extension = _extension(stored.get("original_filename"))
    mime = str(stored.get("mime_type") or "").lower()

    if extension != "txt" and mime != "text/plain":
        return {
            "status": "OCR_INTEGRATION_REQUIRED",
            "record_id": int(record_id),
            "report_id": report["report_id"],
            "format": extension or mime or "unknown",
            "text": None,
            "clinical_imaging_interpretation": False,
            "notice": "This file is not native UTF-8 text. OCR is not configured, so ZENDOC did not invent or infer document text.",
        }

    payload = get_record_storage().read_bytes(stored["stored_filename"], max_bytes=MAX_NATIVE_TEXT_BYTES)
    try:
        decoded = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("Native text extraction supports UTF-8 text only.") from error
    normalized = _normalize_text(decoded)
    if not normalized:
        raise ValueError("The text report contains no extractable UTF-8 content.")
    if len(normalized) > MAX_NATIVE_TEXT_CHARS:
        raise ValueError("Extracted text exceeds the bounded native-text character limit.")

    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    get_db().execute(
        """
        UPDATE report_metadata
        SET extraction_status='native_text_extracted', extraction_message=?, updated_at=?
        WHERE record_id=?
        """,
        (
            f"Native UTF-8 text extracted on demand; sha256={digest}; chars={len(normalized)}. OCR and clinical imaging interpretation were not used.",
            now_iso(),
            int(record_id),
        ),
    )
    get_db().commit()
    return {
        "status": "NATIVE_TEXT_EXTRACTED",
        "record_id": int(record_id),
        "report_id": report["report_id"],
        "report_type": report["report_type"],
        "text": normalized,
        "text_sha256": digest,
        "character_count": len(normalized),
        "ocr_used": False,
        "clinical_imaging_interpretation": False,
        "notice": "Text extraction only. ZENDOC did not diagnose, interpret an image, or convert this text into verified clinical facts.",
    }
