"""
Healthcare Ecosystem Routes — Home Health, Ambulance, Pharmacy, IoT Hub, Marketplace, Universal Search.

Blueprint name: ecosystem
"""

from flask import (
    Blueprint,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from .home_health import (
    create_home_health_request,
    list_home_health_requests,
    list_home_health_services,
)
from .iot_hub import (
    connect_device,
    list_devices,
    list_supported_device_types,
    sync_device_measurement,
)
from .locations import delete_saved_location, list_saved_locations, save_location
from .marketplace import get_marketplace_catalog
from .medical_transport import (
    create_transport_request,
    list_transport_requests,
    list_transport_types,
)
from .pharmacy_service import (
    create_medicine_order,
    create_medicine_reminder,
    delete_medicine_reminder,
    list_medicine_orders,
    list_medicine_reminders,
    list_nearby_pharmacies,
    search_medicines,
)
from .routes import audit, require_api_user
from .security import login_required, role_required
from .universal_search import search_all


bp = Blueprint("ecosystem", __name__)


def _api_error(error):
    if isinstance(error, PermissionError):
        status = 403
    elif isinstance(error, LookupError):
        status = 404
    else:
        status = 400
    return jsonify({"error": {"code": status, "message": str(error)}}), status


# ---------------------------------------------------------------------------
# WEB ROUTES
# ---------------------------------------------------------------------------

@bp.route("/home-health", methods=("GET", "POST"))
@login_required
@role_required("patient")
def home_health_page():
    if request.method == "POST":
        try:
            req = create_home_health_request(g.user, {
                "service_type": request.form.get("service_type"),
                "scheduled_date": request.form.get("scheduled_date"),
                "address": request.form.get("address"),
                "city": request.form.get("city"),
                "notes": request.form.get("notes"),
                "patient_id": request.form.get("patient_id"),
            })
            audit("create", "home_health_request", str(req["id"]))
            flash("Home healthcare request submitted successfully.", "success")
        except (ValueError, PermissionError) as err:
            flash(str(err), "error")
        return redirect(url_for("ecosystem.home_health_page"))

    services = list_home_health_services()
    requests = list_home_health_requests(g.user)
    return render_template("home_health.html", services=services, requests=requests)


@bp.route("/ambulance", methods=("GET", "POST"))
@login_required
def ambulance_page():
    if request.method == "POST":
        try:
            req = create_transport_request(g.user, {
                "transport_type": request.form.get("transport_type"),
                "pickup_address": request.form.get("pickup_address"),
                "destination_address": request.form.get("destination_address"),
                "notes": request.form.get("notes"),
                "patient_id": request.form.get("patient_id"),
            })
            audit("create", "ambulance_request", str(req["id"]))
            if req.get("safety_warning"):
                flash(f"SAFETY ALERT: {req['safety_warning']}", "error")
            else:
                flash("Medical transport request registered successfully.", "success")
        except (ValueError, PermissionError) as err:
            flash(str(err), "error")
        return redirect(url_for("ecosystem.ambulance_page"))

    types = list_transport_types()
    requests = list_transport_requests(g.user)
    return render_template("ambulance.html", transport_types=types, requests=requests)


@bp.route("/pharmacy", methods=("GET", "POST"))
@login_required
def pharmacy_page():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "order":
            med_name = request.form.get("medicine_name")
            address = request.form.get("delivery_address")
            try:
                order = create_medicine_order(g.user, {
                    "items": [{"name": med_name, "quantity": 1}],
                    "delivery_address": address,
                    "pharmacy_id": request.form.get("pharmacy_id"),
                })
                audit("create", "medicine_order", str(order["id"]))
                flash("Medicine delivery order placed!", "success")
            except (ValueError, PermissionError) as err:
                flash(str(err), "error")

        elif action == "add_reminder":
            try:
                rem = create_medicine_reminder(g.user, {
                    "medicine_name": request.form.get("medicine_name"),
                    "dosage": request.form.get("dosage"),
                    "frequency": request.form.get("frequency", "daily"),
                    "reminder_time": request.form.get("reminder_time", "08:00"),
                })
                audit("create", "medicine_reminder", str(rem["id"]))
                flash("Refill & dosage reminder created.", "success")
            except (ValueError, PermissionError) as err:
                flash(str(err), "error")

        return redirect(url_for("ecosystem.pharmacy_page"))

    q = request.args.get("q", "")
    medicines = search_medicines(query=q)
    pharmacies = list_nearby_pharmacies()
    orders = list_medicine_orders(g.user)
    reminders = list_medicine_reminders(g.user)
    return render_template(
        "pharmacy.html",
        medicines=medicines,
        pharmacies=pharmacies,
        orders=orders,
        reminders=reminders,
        q=q,
    )


@bp.route("/iot-hub", methods=("GET", "POST"))
@login_required
def iot_hub_page():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "connect":
            try:
                dev = connect_device(g.user, {
                    "device_name": request.form.get("device_name"),
                    "device_type": request.form.get("device_type"),
                    "manufacturer": request.form.get("manufacturer"),
                    "model": request.form.get("model"),
                    "device_identifier": request.form.get("device_identifier"),
                })
                audit("connect", "health_device", str(dev["id"]))
                flash(f"Device '{dev['device_name']}' connected successfully!", "success")
            except (ValueError, PermissionError) as err:
                flash(str(err), "error")

        elif action == "sync":
            device_id = int(request.form.get("device_id"))
            metric_type = request.form.get("metric_type")
            metric_value = float(request.form.get("metric_value"))
            unit = request.form.get("unit")
            try:
                sync_device_measurement(g.user, device_id, metric_type, metric_value, unit=unit)
                audit("sync", "health_device", str(device_id))
                flash("Measurement synced from device into Health Memory!", "success")
            except Exception as err:
                flash(str(err), "error")

        return redirect(url_for("ecosystem.iot_hub_page"))

    device_types = list_supported_device_types()
    devices = list_devices(g.user)
    return render_template("iot_hub.html", device_types=device_types, devices=devices)


@bp.route("/marketplace")
def marketplace_page():
    catalog = get_marketplace_catalog()
    return render_template("marketplace.html", catalog=catalog)


@bp.route("/search")
def search_page():
    q = request.args.get("q", "")
    results = search_all(g.get("user"), q)
    return render_template("search.html", search_data=results, q=q)


# ---------------------------------------------------------------------------
# API V1 ENDPOINTS
# ---------------------------------------------------------------------------

@bp.get("/api/v1/home-health/requests")
def api_list_home_health():
    user, error = require_api_user()
    if error:
        return error
    reqs = list_home_health_requests(user)
    return jsonify({"home_health_requests": reqs})


@bp.post("/api/v1/home-health/requests")
def api_create_home_health():
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        req = create_home_health_request(user, data)
        audit("create", "home_health_request", str(req["id"]), actor=user)
        return jsonify({"home_health_request": req}), 201
    except (ValueError, PermissionError) as err:
        return _api_error(err)


@bp.get("/api/v1/ambulance/requests")
def api_list_ambulance():
    user, error = require_api_user()
    if error:
        return error
    reqs = list_transport_requests(user)
    return jsonify({"ambulance_requests": reqs})


@bp.post("/api/v1/ambulance/requests")
def api_create_ambulance():
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        req = create_transport_request(user, data)
        audit("create", "ambulance_request", str(req["id"]), actor=user)
        return jsonify({"ambulance_request": req}), 201
    except (ValueError, PermissionError) as err:
        return _api_error(err)


@bp.get("/api/v1/pharmacy/medicines")
def api_search_medicines():
    user, error = require_api_user()
    if error:
        return error
    q = request.args.get("q")
    results = search_medicines(query=q)
    return jsonify({"medicines": results})


@bp.get("/api/v1/pharmacy/stores")
def api_list_pharmacies():
    user, error = require_api_user()
    if error:
        return error
    city = request.args.get("city")
    pharmacies = list_nearby_pharmacies(city=city)
    return jsonify({"pharmacies": pharmacies})


@bp.post("/api/v1/pharmacy/orders")
def api_create_medicine_order():
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        order = create_medicine_order(user, data)
        audit("create", "medicine_order", str(order["id"]), actor=user)
        return jsonify({"medicine_order": order}), 201
    except (ValueError, PermissionError) as err:
        return _api_error(err)


@bp.get("/api/v1/pharmacy/reminders")
def api_list_reminders():
    user, error = require_api_user()
    if error:
        return error
    reminders = list_medicine_reminders(user)
    return jsonify({"medicine_reminders": reminders})


@bp.post("/api/v1/pharmacy/reminders")
def api_create_reminder():
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        rem = create_medicine_reminder(user, data)
        audit("create", "medicine_reminder", str(rem["id"]), actor=user)
        return jsonify({"medicine_reminder": rem}), 201
    except (ValueError, PermissionError) as err:
        return _api_error(err)


@bp.delete("/api/v1/pharmacy/reminders/<int:reminder_id>")
def api_delete_reminder(reminder_id):
    user, error = require_api_user()
    if error:
        return error
    delete_medicine_reminder(user, reminder_id)
    audit("delete", "medicine_reminder", str(reminder_id), actor=user)
    return jsonify({"status": "deleted"})


@bp.get("/api/v1/iot/devices")
def api_list_devices():
    user, error = require_api_user()
    if error:
        return error
    devices = list_devices(user)
    return jsonify({"health_devices": devices})


@bp.post("/api/v1/iot/devices")
def api_connect_device():
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        dev = connect_device(user, data)
        audit("connect", "health_device", str(dev["id"]), actor=user)
        return jsonify({"health_device": dev}), 201
    except (ValueError, PermissionError) as err:
        return _api_error(err)


@bp.post("/api/v1/iot/devices/<int:device_id>/sync")
def api_sync_device(device_id):
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    metric_type = data.get("metric_type")
    metric_value = data.get("metric_value")
    if not metric_type or metric_value is None:
        return jsonify({"error": {"code": 400, "message": "metric_type and metric_value are required."}}), 400
    try:
        res = sync_device_measurement(
            user,
            device_id,
            metric_type,
            float(metric_value),
            unit=data.get("unit"),
            recorded_at=data.get("recorded_at"),
            notes=data.get("notes"),
        )
        audit("sync", "health_device", str(device_id), actor=user)
        return jsonify({"synced_measurement": res}), 201
    except (LookupError, PermissionError, ValueError) as err:
        return _api_error(err)


@bp.get("/api/v1/search")
def api_universal_search():
    user = g.get("user")
    q = request.args.get("q", "")
    results = search_all(user, q)
    return jsonify(results)


@bp.get("/api/v1/marketplace")
def api_marketplace():
    return jsonify({"marketplace": get_marketplace_catalog()})


@bp.get("/api/v1/locations")
def api_list_locations():
    user, error = require_api_user()
    if error:
        return error
    return jsonify({"saved_locations": list_saved_locations(user)})


@bp.post("/api/v1/locations")
def api_save_location():
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        location = save_location(user, data)
        audit("create", "saved_location", str(location["id"]), actor=user)
        return jsonify({"saved_location": location}), 201
    except (ValueError, PermissionError) as err:
        return _api_error(err)


@bp.delete("/api/v1/locations/<int:location_id>")
def api_delete_location(location_id):
    user, error = require_api_user()
    if error:
        return error
    try:
        delete_saved_location(user, location_id)
        audit("delete", "saved_location", str(location_id), actor=user)
        return jsonify({"status": "deleted"})
    except (LookupError, PermissionError) as err:
        return _api_error(err)
