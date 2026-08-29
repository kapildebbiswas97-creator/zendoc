from pathlib import Path

from flask import Blueprint, abort, flash, g, jsonify, redirect, render_template, request, url_for

from .db import get_db
from .health_access import HEALTH_SCOPES, authorize_patient, create_access_grant, list_access_grants, revoke_access_grant
from .health_analytics import METRIC_TYPES, create_measurement, get_health_trend, list_measurements
from .health_profile import BLOOD_GROUPS, SEX_OPTIONS, get_health_profile, save_health_profile
from .health_summary import build_health_summary, export_health_data
from .health_timeline import TIMELINE_TYPES, list_timeline
from .report_intelligence import (
    ABNORMAL_FLAGS,
    REPORT_TYPES,
    add_report_result,
    explain_report,
    get_report,
    get_report_file,
    get_report_result_trend,
    list_report_results,
    list_reports,
    store_report_upload,
)
from .record_storage import get_record_storage
from .routes import audit, create_notification, require_api_user
from .security import login_required, role_required


bp = Blueprint("health_memory", __name__)


def _api_error(error):
    if isinstance(error, PermissionError):
        status = 403
    elif isinstance(error, LookupError):
        status = 404
    else:
        status = 400
    return jsonify({"error": {"code": status, "message": str(error)}}), status


def _optional_patient_id(value):
    if value in (None, ""):
        return None
    try:
        patient_id = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("patient_id must be an integer.") from error
    if patient_id < 1:
        raise ValueError("patient_id must be a positive integer.")
    return patient_id


def _abort_service_error(error):
    if isinstance(error, PermissionError):
        abort(403)
    if isinstance(error, LookupError):
        abort(404)
    flash(str(error), "error")


@bp.route("/health-profile", methods=("GET", "POST"))
@login_required
def health_profile_page():
    if g.user["role"] != "patient":
        abort(403)
    if request.method == "POST":
        try:
            save_health_profile(g.user, request.form)
            audit("update", "patient_health_profile", str(g.user["id"]))
            get_db().commit()
            flash("Health profile updated.", "success")
            return redirect(url_for("health_memory.health_profile_page"))
        except ValueError as error:
            flash(str(error), "error")
    profile = get_health_profile(g.user)
    return render_template("health_profile.html", health_profile=profile, blood_groups=BLOOD_GROUPS, sex_options=SEX_OPTIONS)


@bp.get("/timeline")
@login_required
def timeline_page():
    if g.user["role"] != "patient":
        abort(403)
    try:
        timeline = list_timeline(
            g.user,
            event_type=request.args.get("type"),
            query=request.args.get("q"),
            order=request.args.get("order", "desc"),
            page=request.args.get("page", 1),
            per_page=25,
        )
    except ValueError as error:
        flash(str(error), "error")
        timeline = list_timeline(g.user)
    audit("view", "health_timeline", str(g.user["id"]))
    get_db().commit()
    return render_template("timeline.html", timeline=timeline, timeline_types=TIMELINE_TYPES)


@bp.get("/reports/<int:record_id>")
@login_required
def report_detail_page(record_id):
    try:
        report = get_report(g.user, record_id)
        results = list_report_results(g.user, record_id)
        explanation = explain_report(g.user, record_id)
    except (PermissionError, LookupError, ValueError) as error:
        _abort_service_error(error)
        return redirect(url_for("main.records"))
    audit("view", "medical_report", str(record_id))
    get_db().commit()
    return render_template("report_detail.html", report=report, results=results, explanation=explanation, abnormal_flags=ABNORMAL_FLAGS)


@bp.post("/reports/<int:record_id>/results")
@login_required
def report_result_create(record_id):
    try:
        result_id = add_report_result(g.user, record_id, request.form)
        audit("create", "report_result", str(result_id))
        get_db().commit()
        flash("Structured report result saved as manually entered data.", "success")
    except (PermissionError, LookupError, ValueError) as error:
        _abort_service_error(error)
    return redirect(url_for("health_memory.report_detail_page", record_id=record_id))


@bp.get("/reports/<int:record_id>/download")
@login_required
def report_download(record_id):
    try:
        report = get_report_file(g.user, record_id)
    except (PermissionError, LookupError) as error:
        _abort_service_error(error)
        abort(403)
    audit("download", "medical_report", str(record_id))
    get_db().commit()
    return get_record_storage().response(report["stored_filename"], report["original_filename"])


@bp.get("/health-summary")
@login_required
def health_summary_page():
    if g.user["role"] != "patient":
        abort(403)
    summary = build_health_summary(g.user)
    audit("view", "health_summary", str(g.user["id"]))
    get_db().commit()
    return render_template("health_summary.html", summary=summary, provider_view=False)


@bp.route("/health-access", methods=("GET", "POST"))
@login_required
def health_access_page():
    if g.user["role"] != "patient":
        abort(403)
    if request.method == "POST":
        data = request.form.to_dict()
        data["scopes"] = request.form.getlist("scopes")
        try:
            grant_id = create_access_grant(g.user, data)
            audit("grant", "health_access", str(grant_id))
            get_db().commit()
            flash("Provider access granted for the selected scopes.", "success")
            return redirect(url_for("health_memory.health_access_page"))
        except (PermissionError, ValueError) as error:
            flash(str(error), "error")
    grants = list_access_grants(g.user["id"])
    providers = get_db().execute(
        """
        SELECT pp.id, pp.organization, pp.specialty, u.name
        FROM provider_profiles pp JOIN users u ON u.id=pp.user_id
        WHERE pp.verification_status='verified' AND u.role IN ('doctor','hospital') AND u.active=1
        ORDER BY COALESCE(pp.organization,u.name), pp.specialty
        """
    ).fetchall()
    return render_template("health_access.html", grants=grants, providers=providers, health_scopes=HEALTH_SCOPES)


@bp.post("/health-access/<int:grant_id>/revoke")
@login_required
def health_access_revoke(grant_id):
    try:
        revoke_access_grant(g.user, grant_id)
        audit("revoke", "health_access", str(grant_id))
        get_db().commit()
        flash("Provider access revoked.", "success")
    except (PermissionError, LookupError) as error:
        _abort_service_error(error)
    return redirect(url_for("health_memory.health_access_page"))


@bp.get("/provider/patients/<int:patient_id>/health-summary")
@role_required("doctor", "hospital")
def provider_patient_summary(patient_id):
    try:
        summary = build_health_summary(g.user, patient_id)
    except (PermissionError, LookupError) as error:
        _abort_service_error(error)
        abort(403)
    audit("provider_view", "health_summary", str(patient_id))
    get_db().commit()
    return render_template("health_summary.html", summary=summary, provider_view=True)


@bp.get("/health-export")
@login_required
def health_export_page():
    try:
        exported = export_health_data(g.user)
    except PermissionError:
        abort(403)
    audit("export", "health_data", str(g.user["id"]))
    get_db().commit()
    response = jsonify(exported)
    response.headers["Content-Disposition"] = "attachment; filename=zendoc-health-export.json"
    return response


@bp.route("/api/v1/health-profile", methods=("GET", "PUT"))
def api_health_profile():
    user, error = require_api_user()
    if error:
        return error
    try:
        if request.method == "PUT":
            data = request.get_json(silent=True) or {}
            profile = save_health_profile(user, data, _optional_patient_id(data.get("patient_id")))
            audit("update", "patient_health_profile", str(profile["patient_id"]), actor=user)
            get_db().commit()
        else:
            profile = get_health_profile(user, _optional_patient_id(request.args.get("patient_id")))
            audit("view", "patient_health_profile", str(profile["patient_id"]), actor=user)
            get_db().commit()
        return jsonify({"health_profile": profile})
    except (PermissionError, LookupError, ValueError) as service_error:
        return _api_error(service_error)


@bp.get("/api/v1/health-timeline")
def api_health_timeline():
    user, error = require_api_user()
    if error:
        return error
    try:
        patient_id = _optional_patient_id(request.args.get("patient_id"))
        result = list_timeline(
            user, patient_id=patient_id, event_type=request.args.get("type"), query=request.args.get("q"),
            order=request.args.get("order", "desc"), page=request.args.get("page", 1),
            per_page=request.args.get("per_page", 25), start_date=request.args.get("start_date"), end_date=request.args.get("end_date"),
        )
        audit("view", "health_timeline", str(patient_id or user["id"]), actor=user)
        get_db().commit()
        return jsonify(result)
    except (PermissionError, LookupError, ValueError) as service_error:
        return _api_error(service_error)


@bp.get("/api/v1/health-timeline/search")
def api_health_timeline_search():
    if not request.args.get("q", "").strip():
        return jsonify({"error": {"code": 400, "message": "q is required"}}), 400
    return api_health_timeline()


@bp.route("/api/v1/reports", methods=("GET", "POST"))
def api_reports():
    user, error = require_api_user()
    if error:
        return error
    try:
        patient_id = _optional_patient_id(request.values.get("patient_id"))
        if request.method == "POST":
            target_id = authorize_patient(user, patient_id, "reports")
            upload = request.files.get("file") or request.files.get("record_file")
            record_id = store_report_upload(upload, target_id, user["id"], request.form)
            create_notification(target_id, "Report uploaded", "A medical report was added to your health timeline.")
            audit("upload", "medical_report", str(record_id), actor=user)
            get_db().commit()
            return jsonify({"status": "created", "record_id": record_id, "report": get_report(user, record_id)}), 201
        result = list_reports(user, patient_id, request.args.get("page", 1), request.args.get("per_page", 25))
        return jsonify(result)
    except (PermissionError, LookupError, ValueError) as service_error:
        return _api_error(service_error)


@bp.get("/api/v1/reports/<int:record_id>")
def api_report_detail(record_id):
    user, error = require_api_user()
    if error:
        return error
    try:
        report = get_report(user, record_id)
        report["results"] = list_report_results(user, record_id)
        audit("view", "medical_report", str(record_id), actor=user)
        get_db().commit()
        return jsonify({"report": report})
    except (PermissionError, LookupError) as service_error:
        return _api_error(service_error)


@bp.get("/api/v1/reports/<int:record_id>/download")
def api_report_download(record_id):
    user, error = require_api_user()
    if error:
        return error
    try:
        report = get_report_file(user, record_id)
        audit("download", "medical_report", str(record_id), actor=user)
        get_db().commit()
        return get_record_storage().response(report["stored_filename"], report["original_filename"])
    except (PermissionError, LookupError) as service_error:
        return _api_error(service_error)


@bp.route("/api/v1/reports/<int:record_id>/results", methods=("GET", "POST"))
def api_report_results(record_id):
    user, error = require_api_user()
    if error:
        return error
    try:
        if request.method == "POST":
            result_id = add_report_result(user, record_id, request.get_json(silent=True) or {})
            audit("create", "report_result", str(result_id), actor=user)
            get_db().commit()
            return jsonify({"status": "created", "result_id": result_id}), 201
        return jsonify({"results": list_report_results(user, record_id)})
    except (PermissionError, LookupError, ValueError) as service_error:
        return _api_error(service_error)


@bp.get("/api/v1/reports/<int:record_id>/explanation")
def api_report_explanation(record_id):
    user, error = require_api_user()
    if error:
        return error
    try:
        return jsonify(explain_report(user, record_id))
    except (PermissionError, LookupError) as service_error:
        return _api_error(service_error)


@bp.get("/api/v1/report-trends")
def api_report_trends():
    user, error = require_api_user()
    if error:
        return error
    try:
        result = get_report_result_trend(
            user,
            request.args.get("test_name"),
            _optional_patient_id(request.args.get("patient_id")),
        )
        return jsonify(result)
    except (PermissionError, LookupError, ValueError) as service_error:
        return _api_error(service_error)


@bp.route("/api/v1/health-measurements", methods=("GET", "POST"))
def api_health_measurements():
    user, error = require_api_user()
    if error:
        return error
    try:
        if request.method == "POST":
            data = request.get_json(silent=True) or {}
            patient_id = _optional_patient_id(data.get("patient_id"))
            measurement_id = create_measurement(user, data, patient_id)
            audit("create", "health_measurement", str(measurement_id), actor=user)
            get_db().commit()
            return jsonify({"status": "created", "measurement_id": measurement_id}), 201
        patient_id = _optional_patient_id(request.args.get("patient_id"))
        rows = list_measurements(user, patient_id, request.args.get("metric_type"), request.args.get("limit", 100))
        return jsonify({"measurements": rows})
    except (PermissionError, LookupError, ValueError) as service_error:
        return _api_error(service_error)


@bp.get("/api/v1/health-trends")
def api_health_trends():
    user, error = require_api_user()
    if error:
        return error
    try:
        metric_type = request.args.get("metric_type")
        if not metric_type:
            raise ValueError("metric_type is required.")
        result = get_health_trend(
            user, metric_type, _optional_patient_id(request.args.get("patient_id")), request.args.get("period", "30d"),
            request.args.get("start_date"), request.args.get("end_date"),
        )
        return jsonify(result)
    except (PermissionError, LookupError, ValueError) as service_error:
        return _api_error(service_error)


@bp.get("/api/v1/health-summary")
def api_health_summary():
    user, error = require_api_user()
    if error:
        return error
    try:
        patient_id = _optional_patient_id(request.args.get("patient_id"))
        summary = build_health_summary(user, patient_id)
        audit("view", "health_summary", str(patient_id or user["id"]), actor=user)
        get_db().commit()
        return jsonify({"health_summary": summary})
    except (PermissionError, LookupError, ValueError) as service_error:
        return _api_error(service_error)


@bp.route("/api/v1/health-access", methods=("GET", "POST"))
def api_health_access():
    user, error = require_api_user()
    if error:
        return error
    if user["role"] != "patient":
        return _api_error(PermissionError("Only patients can manage health-data access."))
    try:
        if request.method == "POST":
            grant_id = create_access_grant(user, request.get_json(silent=True) or {})
            audit("grant", "health_access", str(grant_id), actor=user)
            get_db().commit()
            return jsonify({"status": "created", "grant_id": grant_id}), 201
        return jsonify({"grants": list_access_grants(user["id"])})
    except (PermissionError, LookupError, ValueError) as service_error:
        return _api_error(service_error)


@bp.delete("/api/v1/health-access/<int:grant_id>")
def api_health_access_revoke(grant_id):
    user, error = require_api_user()
    if error:
        return error
    try:
        revoke_access_grant(user, grant_id)
        audit("revoke", "health_access", str(grant_id), actor=user)
        get_db().commit()
        return jsonify({"status": "revoked"})
    except (PermissionError, LookupError) as service_error:
        return _api_error(service_error)


@bp.get("/api/v1/health-export")
def api_health_export():
    user, error = require_api_user()
    if error:
        return error
    try:
        exported = export_health_data(user)
        audit("export", "health_data", str(user["id"]), actor=user)
        get_db().commit()
        response = jsonify(exported)
        response.headers["Content-Disposition"] = "attachment; filename=zendoc-health-export.json"
        return response
    except PermissionError as service_error:
        return _api_error(service_error)
