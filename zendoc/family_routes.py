"""
Family Care & Remote Parent Care Routes — Web UI & API v1.

Blueprint name: family
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

from .family_care import (
    add_family_member,
    create_family_access_grant,
    create_care_task,
    delete_family_member,
    get_family_member,
    list_family_access_grants,
    list_care_tasks,
    list_family_members,
    revoke_family_access_grant,
    update_care_task_status,
    update_family_member,
)
from .routes import audit, require_api_user
from .security import login_required, role_required


bp = Blueprint("family", __name__)


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

@bp.route("/family", methods=("GET", "POST"))
@login_required
@role_required("patient")
def family_page():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "add_member":
            try:
                add_family_member(g.user, {
                    "member_name": request.form.get("member_name"),
                    "relationship": request.form.get("relationship"),
                    "age": request.form.get("age") or None,
                    "gender": request.form.get("gender"),
                    "phone": request.form.get("phone"),
                    "city": request.form.get("city"),
                    "is_remote_parent": 1 if request.form.get("is_remote_parent") else 0,
                })
                audit("create", "family_member", str(g.user["id"]))
                flash("Family member added successfully.", "success")
            except (ValueError, PermissionError) as err:
                flash(str(err), "error")
            return redirect(url_for("family.family_page"))

        elif action == "add_task":
            try:
                create_care_task(g.user, {
                    "family_member_id": request.form.get("family_member_id") or None,
                    "title": request.form.get("title"),
                    "task_type": request.form.get("task_type", "general"),
                    "due_date": request.form.get("due_date"),
                    "notes": request.form.get("notes"),
                })
                audit("create", "care_task", str(g.user["id"]))
                flash("Care task added.", "success")
            except (ValueError, PermissionError) as err:
                flash(str(err), "error")
            return redirect(url_for("family.family_page"))

        elif action == "complete_task":
            task_id = request.form.get("task_id")
            if task_id:
                try:
                    update_care_task_status(g.user, int(task_id), "completed")
                    flash("Task marked as completed!", "success")
                except (ValueError, LookupError, PermissionError) as err:
                    flash(str(err), "error")
            return redirect(url_for("family.family_page"))

    members = list_family_members(g.user)
    tasks = list_care_tasks(g.user)
    selected_member_id = request.args.get("member_id")
    selected_member = None
    if selected_member_id:
        try:
            selected_member = get_family_member(g.user, int(selected_member_id))
        except Exception:
            pass

    return render_template(
        "family_care.html",
        members=members,
        tasks=tasks,
        selected_member=selected_member,
    )


@bp.route("/parent-care")
@login_required
@role_required("patient")
def parent_care_page():
    members = list_family_members(g.user)
    parents = [m for m in members if m.get("is_remote_parent") or m["relationship"] in ("father", "mother", "grandfather", "grandmother")]
    tasks = list_care_tasks(g.user)
    return render_template("parent_care.html", parents=parents, tasks=tasks)


# ---------------------------------------------------------------------------
# API V1 ENDPOINTS
# ---------------------------------------------------------------------------

@bp.get("/api/v1/family")
def api_list_family():
    user, error = require_api_user()
    if error:
        return error
    members = list_family_members(user)
    return jsonify({"family_members": members})


@bp.post("/api/v1/family")
def api_add_family():
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        member = add_family_member(user, data)
        audit("create", "family_member", str(member["id"]), actor=user)
        return jsonify({"family_member": member}), 201
    except (ValueError, PermissionError) as err:
        return _api_error(err)


@bp.get("/api/v1/family/<int:member_id>")
def api_get_family(member_id):
    user, error = require_api_user()
    if error:
        return error
    try:
        member = get_family_member(user, member_id)
        return jsonify({"family_member": member})
    except (LookupError, PermissionError) as err:
        return _api_error(err)


@bp.put("/api/v1/family/<int:member_id>")
def api_update_family(member_id):
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        member = update_family_member(user, member_id, data)
        audit("update", "family_member", str(member_id), actor=user)
        return jsonify({"family_member": member})
    except (LookupError, PermissionError, ValueError) as err:
        return _api_error(err)


@bp.delete("/api/v1/family/<int:member_id>")
def api_delete_family(member_id):
    user, error = require_api_user()
    if error:
        return error
    try:
        delete_family_member(user, member_id)
        audit("delete", "family_member", str(member_id), actor=user)
        return jsonify({"status": "deleted"})
    except (LookupError, PermissionError) as err:
        return _api_error(err)


@bp.get("/api/v1/family/care-tasks")
def api_list_care_tasks():
    user, error = require_api_user()
    if error:
        return error
    status = request.args.get("status")
    member_id = request.args.get("member_id")
    tasks = list_care_tasks(user, status=status, member_id=member_id)
    return jsonify({"care_tasks": tasks})


@bp.post("/api/v1/family/care-tasks")
def api_create_care_task():
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        task = create_care_task(user, data)
        audit("create", "care_task", str(task["id"]), actor=user)
        return jsonify({"care_task": task}), 201
    except (ValueError, PermissionError, LookupError) as err:
        return _api_error(err)


@bp.put("/api/v1/family/care-tasks/<int:task_id>")
def api_update_care_task(task_id):
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    status = data.get("status")
    if not status:
        return jsonify({"error": {"code": 400, "message": "status is required."}}), 400
    try:
        task = update_care_task_status(user, task_id, status)
        audit("update", "care_task", str(task_id), actor=user)
        return jsonify({"care_task": task})
    except (LookupError, PermissionError, ValueError) as err:
        return _api_error(err)


@bp.get("/api/v1/family/access-grants")
def api_list_family_access_grants():
    user, error = require_api_user()
    if error:
        return error
    return jsonify({
        "given": list_family_access_grants(user, "given"),
        "received": list_family_access_grants(user, "received"),
    })


@bp.post("/api/v1/family/access-grants")
def api_create_family_access_grant():
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        grant = create_family_access_grant(user, data)
        audit("create", "family_access_grant", str(grant["id"]), actor=user)
        return jsonify({"family_access_grant": grant}), 201
    except (ValueError, LookupError, PermissionError) as err:
        return _api_error(err)


@bp.delete("/api/v1/family/access-grants/<int:grant_id>")
def api_revoke_family_access_grant(grant_id):
    user, error = require_api_user()
    if error:
        return error
    try:
        revoke_family_access_grant(user, grant_id)
        audit("revoke", "family_access_grant", str(grant_id), actor=user)
        return jsonify({"status": "revoked"})
    except (LookupError, PermissionError) as err:
        return _api_error(err)
