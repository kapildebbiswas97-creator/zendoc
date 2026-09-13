"""Truthful source-record validation for CareLoop integration labels.

A CareLoop action is internally integrated only when its service_ref resolves to
an authorized ZENDOC source record backed by the provider/assignment guarantees
used when that action was created.  This module never marks external execution.
"""
from __future__ import annotations

from .db import get_db

_DIAGNOSTIC_PROVIDER_TYPES = {"diagnostic_centre", "diagnostic_center", "lab", "hospital"}


def linked_internal_service(action: dict) -> dict | None:
    service_ref = str(action.get("service_ref") or "")
    patient_id = int(action.get("patient_id") or 0)
    if not service_ref or not patient_id or ":" not in service_ref:
        return None

    prefix, raw_id = service_ref.split(":", 1)
    try:
        source_id = int(raw_id)
    except (TypeError, ValueError):
        return None

    if prefix == "zendoc_appointment":
        return _appointment(source_id, patient_id)
    if prefix == "zendoc_pharmacy_order":
        return _pharmacy_order(source_id, patient_id)
    if prefix == "zendoc_diagnostic_booking":
        return _diagnostic_booking(source_id, patient_id)
    if prefix == "zendoc_home_health_request":
        return _home_health_request(source_id, patient_id)
    return None


def _appointment(source_id: int, patient_id: int) -> dict | None:
    row = get_db().execute(
        """
        SELECT a.id,a.provider_id,u.active,pp.verification_status
        FROM appointments a
        JOIN users u ON u.id=a.provider_id AND u.active=1
        LEFT JOIN provider_profiles pp ON pp.user_id=u.id
        WHERE a.id=? AND a.patient_id=? AND a.provider_id IS NOT NULL
        """,
        (source_id, patient_id),
    ).fetchone()
    if not row:
        return None
    # Appointments pre-date mandatory provider-profile verification in some
    # legitimate records, so preserve the established registered-provider
    # boundary while rejecting missing/inactive provider accounts.
    return {
        "execution_scope": "zendoc_internal_registered_provider",
        "source_type": "appointment",
        "source_id": source_id,
        "notice": (
            "This action is linked to a real ZENDOC registered-provider appointment lifecycle. "
            "It does not claim execution inside an external hospital/vendor system."
        ),
    }


def _pharmacy_order(source_id: int, patient_id: int) -> dict | None:
    row = get_db().execute(
        """
        SELECT mo.id,mo.pharmacy_id,p.active,pp.verification_status
        FROM medicine_orders mo
        JOIN users p ON p.id=mo.pharmacy_id AND p.role='pharmacy' AND p.active=1
        JOIN provider_profiles pp ON pp.user_id=p.id
        WHERE mo.id=? AND mo.patient_id=? AND mo.pharmacy_id IS NOT NULL
        """,
        (source_id, patient_id),
    ).fetchone()
    if not row or str(row["verification_status"] or "").strip().lower() != "verified":
        return None
    return {
        "execution_scope": "zendoc_internal_registered_pharmacy",
        "source_type": "pharmacy_order",
        "source_id": source_id,
        "notice": (
            "This action is linked to a real order assigned to an active verified ZENDOC pharmacy. "
            "It does not claim stock, payment, dispensing, courier, or external pharmacy-system execution."
        ),
    }


def _diagnostic_booking(source_id: int, patient_id: int) -> dict | None:
    row = get_db().execute(
        """
        SELECT b.id,b.lab_id,lab.active,pp.provider_type,pp.verification_status
        FROM diagnostic_bookings b
        JOIN users lab ON lab.id=b.lab_id AND lab.active=1
        JOIN provider_profiles pp ON pp.user_id=lab.id
        WHERE b.id=? AND b.patient_id=?
        """,
        (source_id, patient_id),
    ).fetchone()
    if not row:
        return None
    if str(row["verification_status"] or "").strip().lower() != "verified":
        return None
    if str(row["provider_type"] or "").strip().lower() not in _DIAGNOSTIC_PROVIDER_TYPES:
        return None
    return {
        "execution_scope": "zendoc_internal_verified_diagnostic_provider",
        "source_type": "diagnostic_booking",
        "source_id": source_id,
        "notice": (
            "This action is linked to a real booking assigned to an active verified ZENDOC diagnostic provider. "
            "It does not claim external LIS, payment, sample chain-of-custody, or clinical interpretation."
        ),
    }


def _home_health_request(source_id: int, patient_id: int) -> dict | None:
    row = get_db().execute(
        """
        SELECT h.id,h.service_type,a.provider_id,p.active,pp.verification_status,
               s.active AS capability_active
        FROM home_health_requests h
        JOIN home_health_assignments a ON a.request_id=h.id
        JOIN users p ON p.id=a.provider_id AND p.active=1
        JOIN provider_profiles pp ON pp.id=a.provider_profile_id AND pp.user_id=p.id
        JOIN home_health_provider_services s
          ON s.provider_id=p.id AND s.service_type=h.service_type AND s.active=1
        WHERE h.id=? AND h.patient_id=?
        """,
        (source_id, patient_id),
    ).fetchone()
    if not row or str(row["verification_status"] or "").strip().lower() != "verified":
        return None
    return {
        "execution_scope": "zendoc_internal_verified_home_health_provider",
        "source_type": "home_health_request",
        "source_id": source_id,
        "notice": (
            "This action is linked to a real ZENDOC home-health request assigned to an active verified provider "
            "that explicitly publishes the requested capability. It does not claim external agency dispatch, "
            "arrival, payment, or service execution outside ZENDOC."
        ),
    }
