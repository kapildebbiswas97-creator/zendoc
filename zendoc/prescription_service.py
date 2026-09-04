"""
ZENDOC Prescription Service & Safety Guard — Milestone 10
Prescription parsing, confidence tracking, uncertain item review, and strict clinical safeguards.

CLINICAL BOUNDARIES:
- Extraction is NOT prescribing.
- AI NEVER autonomously generates prescriptions or adds prescription-only medicines.
- Low-confidence extractions require explicit human review (ITEM_REVIEW_REQUIRED).
"""
from __future__ import annotations

import json
from typing import Any

from .db import get_db, now_iso

RX_RESTRICTED_TERMS = {
    "antibiotic", "amoxicillin", "azithromycin", "ciprofloxacin", "steroid",
    "prednisolone", "dexamethasone", "schedule h", "schedule x", "sedative",
    "alprazolam", "clonazepam", "tramadol", "prescribe", "give me prescription",
}


def is_autonomous_prescription_request(text: str) -> bool:
    """Detect attempts to request autonomous AI prescribing."""
    lower = str(text or "").lower()
    return any(t in lower for t in RX_RESTRICTED_TERMS)


def create_prescription(
    patient_id: int,
    prescriber_name: str,
    items: list[dict[str, Any]],
    prescriber_id: int | None = None,
    record_id: int | None = None,
    diagnosis_notes: str | None = None,
    data_mode: str = "LIVE",
    source: str = "DOCUMENT_EXTRACTED",
) -> dict[str, Any]:
    """
    Create a prescription record with itemized medications.
    Each item tracks extraction confidence and review status.
    """
    if not items:
        raise ValueError("Prescription must contain at least one medication item.")

    db = get_db()
    now = now_iso()
    uid = f"rx_{patient_id}_{int(db.execute('SELECT COUNT(*) c FROM prescriptions').fetchone()['c']) + 1}_{now[:10].replace('-', '')}"

    cursor = db.execute(
        """
        INSERT INTO prescriptions
        (prescription_uid, patient_id, prescriber_id, prescriber_name, record_id, issue_date, diagnosis_notes, status, data_mode, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)
        """,
        (uid, patient_id, prescriber_id, prescriber_name, record_id, now[:10], diagnosis_notes, data_mode, now, now),
    )
    presc_id = cursor.lastrowid

    inserted_items = []
    has_uncertain_item = False

    for it in items:
        med_name = str(it.get("medicine_name") or it.get("name") or "").strip()
        if not med_name:
            continue

        # Match SKU from catalog
        sku_row = db.execute(
            """
            SELECT id, name, rx_required, form, strength
            FROM medication_skus
            WHERE LOWER(name)=LOWER(?) OR LOWER(generic_name)=LOWER(?)
            LIMIT 1
            """,
            (med_name, med_name),
        ).fetchone()

        sku_id = int(it.get("sku_id")) if it.get("sku_id") else (sku_row["id"] if sku_row else None)
        if not sku_id:
            first_word = med_name.split()[0] if med_name else ""
            fuzzy = db.execute("SELECT id FROM medication_skus WHERE LOWER(name) LIKE ? LIMIT 1", (f"%{first_word.lower()}%",)).fetchone()
            if fuzzy:
                sku_id = fuzzy["id"]
        rx_req = int(sku_row["rx_required"]) if sku_row else int(it.get("rx_required", 1))
        confidence = float(it.get("extraction_confidence", 1.0))
        review_status = "item_review_required" if confidence < 0.90 else "verified"
        if review_status == "item_review_required":
            has_uncertain_item = True

        c_item = db.execute(
            """
            INSERT INTO prescription_items
            (prescription_id, medicine_name, salt_composition, dosage, form, frequency, duration,
             quantity_prescribed, quantity_unit, instructions, rx_required, extraction_confidence, review_status, sku_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                presc_id,
                med_name,
                it.get("salt_composition"),
                it.get("dosage"),
                it.get("form", "tablet"),
                it.get("frequency", "daily"),
                it.get("duration", "30 days"),
                int(it.get("quantity_prescribed", 30)),
                it.get("quantity_unit", "tablets"),
                it.get("instructions"),
                rx_req,
                confidence,
                review_status,
                sku_id,
                now,
            ),
        )
        inserted_items.append(c_item.lastrowid)

    # Record continuity event in Health Memory
    from .care_graph import record_care_continuity_event
    record_care_continuity_event(
        patient_id=patient_id,
        event_type="PRESCRIPTION_RECORDED",
        title=f"Prescription recorded ({prescriber_name})",
        summary=f"{len(inserted_items)} items prescribed by {prescriber_name}.",
        source=source,
        source_ref=f"prescription:{presc_id}",
        metadata={"prescription_uid": uid, "provider_name": prescriber_name, "has_uncertain_item": has_uncertain_item},
    )

    db.commit()
    return get_prescription(presc_id)


def get_prescription(prescription_id: int, actor: Any = None) -> dict[str, Any]:
    """Retrieve full prescription details including items and review status."""
    db = get_db()
    row = db.execute("SELECT * FROM prescriptions WHERE id=?", (prescription_id,)).fetchone()
    if not row:
        raise LookupError(f"Prescription #{prescription_id} not found.")

    res = dict(row)
    if actor is not None:
        from .context_engine import verify_context_authorization
        verify_context_authorization(actor, res["patient_id"], "prescription_view")

    items = db.execute(
        """
        SELECT pi.*, ms.sku_code, ms.mrp_inr
        FROM prescription_items pi
        LEFT JOIN medication_skus ms ON ms.id=pi.sku_id
        WHERE pi.prescription_id=?
        ORDER BY pi.id ASC
        """,
        (prescription_id,),
    ).fetchall()

    res["items"] = [dict(i) for i in items]
    res["needs_review"] = any(i["review_status"] == "item_review_required" for i in res["items"])
    return res


def confirm_uncertain_prescription_item(item_id: int, actor: Any) -> dict[str, Any]:
    """Explicit human confirmation gate for low-confidence medicine extractions."""
    db = get_db()
    row = db.execute(
        """
        SELECT pi.*, p.patient_id
        FROM prescription_items pi
        JOIN prescriptions p ON p.id=pi.prescription_id
        WHERE pi.id=?
        """,
        (item_id,),
    ).fetchone()
    if not row:
        raise LookupError(f"Prescription item #{item_id} not found.")

    from .context_engine import verify_context_authorization
    verify_context_authorization(actor, row["patient_id"], "prescription_item_confirm")

    db.execute(
        "UPDATE prescription_items SET review_status='user_confirmed' WHERE id=?",
        (item_id,),
    )
    db.commit()

    updated = db.execute("SELECT * FROM prescription_items WHERE id=?", (item_id,)).fetchone()
    return dict(updated)