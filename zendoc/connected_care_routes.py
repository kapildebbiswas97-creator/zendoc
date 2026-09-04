"""
ZENDOC Connected Care Routes — Milestone 10

Blueprint: connected_care
URL prefix: /connected-care  (pages)
             /api/v1/connected-care  (JSON API)

Architecture invariants enforced here:
  1. Zero autonomous consequential actions — AI stages, user explicitly confirms.
  2. Clinical boundary — AI never prescribes; prescription creation blocked for
     agent roles, only doctors / patients with warning.
  3. Inventory truth — UNKNOWN inventory never shown as available.
  4. All state-changing API endpoints are CSRF-protected via require_api_user().
"""
from __future__ import annotations

import hmac
import json
from datetime import datetime, timezone

from flask import (
    Blueprint,
    abort,
    current_app,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from .care_graph import get_patient_care_graph, record_care_continuity_event
from .context_engine import (
    build_minimum_context_bundle,
    create_or_update_consent_grant,
    get_active_consent_grant,
    revoke_consent_grant,
    verify_context_authorization,
)
from .db import get_db, now_iso
from .diagnostic_service import (
    book_diagnostic_test,
    search_lab_offers,
)
from .fulfilment_optimizer import optimize_prescription_fulfilment
from .health_memory_continuity import (
    determine_next_safe_actions,
    get_health_memory_provenance_summary,
)
from .inventory_service import search_pharmacy_offers, update_inventory_observation
from .order_service import (
    get_order_details,
    submit_order_from_plan,
)
from .prescription_service import (
    create_prescription,
    get_prescription,
    is_autonomous_prescription_request,
)
from .routes import api_user, audit, require_api_user
from .security import is_owner
from .trust_service import get_provider_trust_signals

bp = Blueprint("connected_care", __name__)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _api_error(error, status=None):
    if status is None:
        if isinstance(error, PermissionError):
            status = 403
        elif isinstance(error, LookupError):
            status = 404
        elif isinstance(error, ValueError):
            status = 400
        else:
            status = 400
    return jsonify({"error": {"code": status, "message": str(error)}}), status


def _api_user(mutation=False):
    """Return ``(user_dict, error_response | None)`` for API or browser calls.

    The browser Connected Care page uses the normal Flask session, while API
    clients use bearer tokens.  ``require_api_user`` intentionally only knows
    about tokens, so this boundary handles the session case and applies the
    CSRF check for session-backed mutations.  A malformed bearer token must
    never fall back to an unrelated browser session.
    """
    authorization = request.headers.get("Authorization", "").strip()
    if authorization:
        user, error = require_api_user()
        if error:
            return None, error
        return dict(user), None

    user = g.get("user")
    if user is None and session.get("user_id"):
        user = get_db().execute(
            "SELECT * FROM users WHERE id=? AND active=1", (int(session["user_id"]),)
        ).fetchone()
    if user is None:
        return None, (jsonify({"error": "Unauthorized"}), 401)
    if user["role"] == "admin" and not is_owner(user):
        return None, (jsonify({"error": {"code": 403, "message": "Only the ZENDOC owner may access Admin operations."}}), 403)

    if mutation:
        supplied = request.headers.get("X-CSRF-Token") or request.headers.get("X-CSRFToken")
        expected = session.get("csrf_token")
        if not expected or not supplied or not hmac.compare_digest(str(supplied), str(expected)):
            return None, (jsonify({"error": {"code": 400, "message": "A valid CSRF token is required for browser mutations."}}), 400)
    return dict(user), None


def _current_user_id():
    """Return logged-in user id or None."""
    if getattr(g, "user", None):
        return g.user["id"]
    if getattr(g, "current_user", None):
        return g.current_user["id"]
    if session.get("user_id"):
        return session.get("user_id")
    u = api_user()
    if u:
        return u["id"]
    return None


def _get_patient_id(user, request_data: dict) -> int:
    """
    Resolve the target patient_id from request body or default to the actor.
    Raises PermissionError if the actor lacks authorization for a 3rd-party patient.
    """
    patient_id = int(request_data.get("patient_id") or user["id"])
    if patient_id != int(user["id"]):
        # Verify the actor has delegation before proceeding
        verify_context_authorization(user, patient_id, request_data.get("purpose", "pharmacy"))
    return patient_id


# ── Page Routes ────────────────────────────────────────────────────────────────

@bp.get("/connected-care/")
@bp.get("/connected-care")
def connected_care_home():
    uid = _current_user_id()
    if not uid:
        return redirect(url_for("main.login", role="patient"))

    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not user:
        abort(401)
    user = dict(user)
    data_mode = str(current_app.config.get("CONNECTED_CARE_DATA_MODE", "LIVE")).upper()

    # Fetch active prescriptions summary for display (limit 5)
    try:
        presc_rows = db.execute(
            "SELECT * FROM prescriptions WHERE patient_id=? AND status='active' ORDER BY id DESC LIMIT 5",
            (uid,),
        ).fetchall()
        prescriptions = [dict(r) for r in presc_rows]
    except Exception:
        prescriptions = []

    # Fetch recent orders (limit 5)
    orders = db.execute(
        """
        SELECT id, ('Medicine Order #' || id) as medicine_name, status, order_uid, tracking_status, created_at
        FROM medicine_orders WHERE patient_id=? OR ordered_by=? ORDER BY id DESC LIMIT 5
        """,
        (uid, uid),
    ).fetchall()

    # Health memory provenance summary
    try:
        provenance = get_health_memory_provenance_summary(user, actor=user)
    except Exception:
        provenance = {"total_events": 0, "latest_event": None}

    # Next safe actions
    try:
        next_actions = determine_next_safe_actions(user, actor=user)
    except Exception:
        next_actions = []

    return render_template(
        "connected_care.html",
        user=user,
        prescriptions=prescriptions,
        recent_orders=[dict(o) for o in orders],
        provenance=provenance,
        next_actions=next_actions,
        data_mode=data_mode,
        demo_mode=data_mode == "DEMO",
    )


@bp.get("/connected-care/prescriptions")
def prescriptions_page():
    uid = _current_user_id()
    if not uid:
        return redirect(url_for("main.login", role="patient"))
    db = get_db()
    user = dict(db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone() or abort(401))
    try:
        presc_rows = db.execute(
            "SELECT * FROM prescriptions WHERE patient_id=? AND status='active' ORDER BY id DESC LIMIT 50",
            (int(user["id"]),),
        ).fetchall()
        prescriptions = [dict(r) for r in presc_rows]
    except Exception as e:
        prescriptions = []
    data_mode = str(current_app.config.get("CONNECTED_CARE_DATA_MODE", "LIVE")).upper()
    return render_template("connected_care.html", user=user, prescriptions=prescriptions,
                           page_tab="prescriptions", data_mode=data_mode, demo_mode=data_mode == "DEMO")


@bp.get("/connected-care/orders")
def orders_page():
    uid = _current_user_id()
    if not uid:
        return redirect(url_for("main.login", role="patient"))
    db = get_db()
    user = dict(db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone() or abort(401))
    orders = db.execute(
        """
        SELECT id, ('Medicine Order #' || id) as medicine_name, status, order_uid, tracking_status, delivery_address, created_at
        FROM medicine_orders WHERE patient_id=? OR ordered_by=? ORDER BY id DESC LIMIT 20
        """,
        (uid, uid),
    ).fetchall()
    data_mode = str(current_app.config.get("CONNECTED_CARE_DATA_MODE", "LIVE")).upper()
    return render_template("connected_care.html", user=user,
                           orders=[dict(o) for o in orders],
                           page_tab="orders", data_mode=data_mode, demo_mode=data_mode == "DEMO")


@bp.get("/connected-care/diagnostics")
def diagnostics_page():
    uid = _current_user_id()
    if not uid:
        return redirect(url_for("main.login", role="patient"))
    db = get_db()
    user = dict(db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone() or abort(401))
    query = request.args.get("q", "")
    try:
        offers = search_lab_offers(query) if query else []
        # The catalog is descriptive only.  Availability and price come from
        # verified lab offers; diagnostic_catalog has no active flag.
        catalog = db.execute("SELECT * FROM diagnostic_catalog ORDER BY name").fetchall()
    except Exception:
        offers = []
        catalog = []
    data_mode = str(current_app.config.get("CONNECTED_CARE_DATA_MODE", "LIVE")).upper()
    return render_template("connected_care.html", user=user,
                           diagnostic_offers=offers,
                           diagnostic_catalog=[dict(c) for c in catalog],
                           page_tab="diagnostics", data_mode=data_mode, demo_mode=data_mode == "DEMO")


@bp.get("/connected-care/inbox")
def inbox_page():
    uid = _current_user_id()
    if not uid:
        return redirect(url_for("main.login", role="patient"))
    db = get_db()
    user = dict(db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone() or abort(401))

    # Unified inbox: recent orders + recent bookings + health memory events
    orders = db.execute(
        "SELECT 'order' as item_type, id, created_at, status, ('Medicine Order #' || id) as title FROM medicine_orders WHERE patient_id=? OR ordered_by=? ORDER BY id DESC LIMIT 10",
        (uid, uid),
    ).fetchall()
    bookings = db.execute(
        "SELECT 'diagnostic' as item_type, id, created_at, status, ('Test #' || test_id) as title FROM diagnostic_bookings WHERE patient_id=? ORDER BY id DESC LIMIT 10",
        (uid,),
    ).fetchall()
    events = db.execute(
        "SELECT 'memory' as item_type, id, created_at, 'Health Record' as status, event_type as title FROM health_timeline_events WHERE patient_id=? ORDER BY id DESC LIMIT 10",
        (uid,),
    ).fetchall()

    # Merge and sort
    inbox_items = sorted(
        [dict(o) for o in orders] + [dict(b) for b in bookings] + [dict(e) for e in events],
        key=lambda x: x.get("created_at") or "",
        reverse=True,
    )[:30]

    data_mode = str(current_app.config.get("CONNECTED_CARE_DATA_MODE", "LIVE")).upper()
    return render_template("inbox.html", user=user, inbox_items=inbox_items,
                           data_mode=data_mode, demo_mode=data_mode == "DEMO")


# ── JSON API ───────────────────────────────────────────────────────────────────

@bp.get("/api/v1/connected-care/context")
def api_context():
    user, err = _api_user()
    if err:
        return err
    try:
        data = request.args
        patient_id = int(data.get("patient_id") or user["id"])
        purpose = data.get("purpose", "pharmacy")
        action = data.get("action", "view_context")
        bundle = build_minimum_context_bundle(user, patient_id, purpose, action)
        return jsonify(bundle.to_dict())
    except PermissionError as e:
        return _api_error(e, 403)
    except Exception as e:
        return _api_error(e)


@bp.get("/api/v1/connected-care/pharmacy-offers")
def api_pharmacy_offers():
    user, err = _api_user()
    if err:
        return err
    try:
        q = request.args.get("q", "")
        lat = request.args.get("lat")
        lon = request.args.get("lon")
        patient_lat = float(lat) if lat else None
        patient_lon = float(lon) if lon else None
        radius_km = float(request.args.get("radius_km", 10))
        results = search_pharmacy_offers(
            query=q,
            patient_lat=patient_lat,
            patient_lon=patient_lon,
            radius_km=radius_km,
        )
        return jsonify({"offers": results, "query": q})
    except Exception as e:
        return _api_error(e)


@bp.post("/api/v1/connected-care/fulfilment")
def api_optimize_fulfilment():
    """Stage a multi-pharmacy fulfilment plan. Does NOT place an order."""
    user, err = _api_user()
    if err:
        return err
    try:
        body = request.get_json(force=True) or {}
        prescription_id = int(body.get("prescription_id", 0))
        if not prescription_id:
            return _api_error(ValueError("prescription_id is required"), 400)
        patient_id = int(body.get("patient_id") or user["id"])
        _get_patient_id(user, {"patient_id": patient_id, "purpose": "pharmacy"})

        plan = optimize_prescription_fulfilment(
            prescription_id=prescription_id,
            patient_lat=body.get("patient_lat"),
            patient_lon=body.get("patient_lon"),
            strategy=body.get("strategy"),
        )
        audit("connected_care.fulfilment.stage", "fulfilment_plan", plan.get("plan_id"), user)
        return jsonify({"plan": plan, "requires_confirmation": True})
    except PermissionError as e:
        return _api_error(e, 403)
    except LookupError as e:
        return _api_error(e, 404)
    except Exception as e:
        return _api_error(e)


@bp.post("/api/v1/connected-care/orders/confirm")
def api_confirm_order():
    """
    Submit a staged fulfilment plan as a real order.
    REQUIRES explicit user confirmation (user_confirmed=True in body).
    This is the only route that places orders — all others are read/stage only.
    """
    user, err = _api_user()
    if err:
        return err
    try:
        body = request.get_json(force=True) or {}
        user_confirmed = bool(body.get("user_confirmed", False))
        if not user_confirmed:
            return _api_error(
                ValueError("Order requires explicit user confirmation. Set user_confirmed=true."), 400
            )

        plan_id_raw = body.get("plan_id")
        if plan_id_raw is None or str(plan_id_raw).strip() == "":
            return _api_error(ValueError("plan_id is required"), 400)
        plan_id = int(plan_id_raw)

        result = submit_order_from_plan(
            plan_id=plan_id,
            actor=user,
            user_confirmed=True,
            delivery_address=body.get("delivery_address"),
        )
        audit("connected_care.order.confirm", "medicine_order", result.get("order_id"), user)
        return jsonify({"order": result, "message": "Order placed successfully."})
    except PermissionError as e:
        return _api_error(e, 403)
    except LookupError as e:
        return _api_error(e, 404)
    except Exception as e:
        return _api_error(e)


@bp.post("/api/v1/connected-care/prescriptions")
def api_create_prescription():
    user, err = _api_user()
    if err:
        return err
    try:
        body = request.get_json(force=True) or {}
        patient_id = int(body.get("patient_id") or user["id"])
        _get_patient_id(user, {"patient_id": patient_id, "purpose": "prescriptions"})
        # Prescriptions are only created from doctor uploads / record extraction, not AI autonomy
        prescriber_name = str(body.get("prescriber_name") or "Unknown Prescriber")
        prescription = create_prescription(
            patient_id=patient_id,
            prescriber_name=prescriber_name,
            items=body.get("items", []),
            prescriber_id=body.get("prescribing_doctor_id"),
            diagnosis_notes=body.get("notes", ""),
        )
        audit("connected_care.prescription.create", "prescription", prescription.get("id"), user)
        return jsonify({"prescription": prescription}), 201
    except PermissionError as e:
        return _api_error(e, 403)
    except ValueError as e:
        return _api_error(e, 400)
    except Exception as e:
        return _api_error(e)


@bp.get("/api/v1/connected-care/prescriptions")
def api_list_prescriptions():
    user, err = _api_user()
    if err:
        return err
    try:
        patient_id = int(request.args.get("patient_id") or user["id"])
        _get_patient_id(user, {"patient_id": patient_id, "purpose": "prescriptions"})
        db = get_db()
        rows = db.execute(
            "SELECT * FROM prescriptions WHERE patient_id=? AND status='active' ORDER BY id DESC LIMIT 50",
            (patient_id,),
        ).fetchall()
        return jsonify({"prescriptions": [dict(r) for r in rows]})
    except PermissionError as e:
        return _api_error(e, 403)
    except Exception as e:
        return _api_error(e)


@bp.post("/api/v1/connected-care/inventory")
def api_update_inventory():
    """Pharmacy-only: report current inventory observation for a SKU."""
    user, err = _api_user()
    if err:
        return err
    if user.get("role") not in ("pharmacy", "admin"):
        return _api_error(PermissionError("Only pharmacy accounts may update inventory."), 403)
    try:
        body = request.get_json(force=True) or {}
        quantity = int(body.get("quantity") or body.get("quantity_available", 0))
        price_inr = float(body.get("price_inr") or body.get("unit_price", 0))
        status = str(body.get("stock_status") or body.get("availability_status", "CONFIRMED")).upper()
        result = update_inventory_observation(
            pharmacy_id=int(user["id"]),
            sku_id=int(body["sku_id"]),
            quantity=quantity,
            price_inr=price_inr,
            stock_status=status,
            source=body.get("source", "pharmacy_manual"),
        )
        audit("connected_care.inventory.update", "inventory_observations", result.get("id"), user)
        return jsonify({"observation": result}), 201
    except (KeyError, TypeError, ValueError) as e:
        return _api_error(ValueError(f"Invalid request: {e}"), 400)
    except Exception as e:
        return _api_error(e)


@bp.get("/api/v1/connected-care/next-safe-actions")
def api_next_safe_actions():
    user, err = _api_user()
    if err:
        return err
    try:
        patient_id = int(request.args.get("patient_id") or user["id"])
        _get_patient_id(user, {"patient_id": patient_id, "purpose": "care_continuity"})
        db = get_db()
        patient = db.execute("SELECT * FROM users WHERE id=?", (patient_id,)).fetchone()
        if not patient:
            return _api_error(LookupError("Patient not found"), 404)
        actions = determine_next_safe_actions(dict(patient))
        return jsonify({"next_safe_actions": actions})
    except PermissionError as e:
        return _api_error(e, 403)
    except Exception as e:
        return _api_error(e)


@bp.post("/api/v1/connected-care/consent")
def api_create_consent():
    user, err = _api_user()
    if err:
        return err
    try:
        body = request.get_json(force=True) or {}
        grant = create_or_update_consent_grant(
            subject_id=int(user["id"]),
            grantee_id=int(body["grantee_id"]),
            purpose=body.get("purpose", "pharmacy"),
            scopes=body.get("scopes", ["prescriptions", "delivery_address"]),
            expires_at=body.get("expires_at"),
        )
        audit("connected_care.consent.grant", "consent_grants", grant.get("id"), user)
        return jsonify({"grant": grant}), 201
    except (KeyError, TypeError) as e:
        return _api_error(ValueError(f"Missing required field: {e}"), 400)
    except Exception as e:
        return _api_error(e)


@bp.delete("/api/v1/connected-care/consent/<int:grant_id>")
def api_revoke_consent(grant_id):
    user, err = _api_user()
    if err:
        return err
    try:
        revoke_consent_grant(grant_id, int(user["id"]))
        audit("connected_care.consent.revoke", "consent_grants", grant_id, user)
        return jsonify({"revoked": True, "grant_id": grant_id})
    except PermissionError as e:
        return _api_error(e, 403)
    except Exception as e:
        return _api_error(e)


@bp.post("/api/v1/connected-care/diagnostics/book")
def api_book_diagnostic():
    user, err = _api_user()
    if err:
        return err
    try:
        body = request.get_json(force=True) or {}
        patient_id = int(body.get("patient_id") or user["id"])
        _get_patient_id(user, {"patient_id": patient_id, "purpose": "diagnostics"})
        test_id = int(body.get("test_id") or body.get("offer_id", 0))
        lab_id = body.get("lab_id")
        scheduled_date = str(body.get("scheduled_date") or body.get("scheduled_at") or now_iso()[:10])
        address = str(body.get("address") or user.get("city") or "Patient Address")
        booking = book_diagnostic_test(
            actor=user,
            patient_id=patient_id,
            test_id=test_id,
            lab_id=int(lab_id) if lab_id else None,
            scheduled_date=scheduled_date,
            address=address,
            collection_type=str(body.get("collection_type", "home_collection")),
            slot_time=str(body.get("slot_time", "08:00 - 10:00")),
        )
        audit("connected_care.diagnostic.book", "diagnostic_bookings", booking.get("id"), user)
        return jsonify({"booking": booking}), 201
    except (KeyError, TypeError) as e:
        return _api_error(ValueError(f"Missing required field: {e}"), 400)
    except LookupError as e:
        return _api_error(e, 404)
    except Exception as e:
        return _api_error(e)


@bp.get("/api/v1/connected-care/orders/<int:order_id>")
def api_get_order(order_id):
    user, err = _api_user()
    if err:
        return err
    try:
        order = get_order_details(order_id, actor=user)
        return jsonify({"order": order})
    except PermissionError as e:
        return _api_error(e, 403)
    except LookupError as e:
        return _api_error(e, 404)
    except Exception as e:
        return _api_error(e)


@bp.get("/api/v1/connected-care/trust/<int:provider_id>")
def api_provider_trust(provider_id):
    user, err = _api_user()
    if err:
        return err
    try:
        signals = get_provider_trust_signals(provider_id)
        return jsonify({"trust": signals})
    except Exception as e:
        return _api_error(e)


@bp.get("/api/v1/connected-care/care-graph")
def api_care_graph():
    user, err = _api_user()
    if err:
        return err
    try:
        patient_id = int(request.args.get("patient_id") or user["id"])
        _get_patient_id(user, {"patient_id": patient_id, "purpose": "care_graph"})
        graph = get_patient_care_graph(patient_id)
        return jsonify({"care_graph": graph})
    except PermissionError as e:
        return _api_error(e, 403)
    except Exception as e:
        return _api_error(e)
