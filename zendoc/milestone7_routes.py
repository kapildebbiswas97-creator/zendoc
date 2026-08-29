from flask import Blueprint, abort, flash, g, jsonify, redirect, render_template, request, url_for

from .agent_core import admin_command_center_data, respond_with_core_agent
from .connect import (
    create_communication_permission,
    discover_contacts,
    get_conversation,
    list_conversations,
    list_messages,
    mark_read,
    send_message,
    share_report_message,
    share_video_message,
    start_conversation,
    unread_count,
)
from .db import get_db
from .human_operations import create_staff_task, list_staff_tasks, update_staff_task, upsert_staff_profile
from .pose_coach import POSE_EXERCISES, list_pose_sessions, save_pose_session
from .routes import audit, require_api_user
from .security import assert_owner, login_required, owner_required, role_required
from .telehealth import (
    get_consultation,
    get_doctor_availability,
    list_consultation_messages,
    list_consultations,
    request_consultation,
    send_consultation_message,
    set_doctor_availability,
    update_consultation_status,
)
from .video_guidance import build_video_guidance
from .video_intelligence import VIDEO_CATEGORIES, find_educational_video


bp = Blueprint("milestone7", __name__)


def _api_error(error):
    if isinstance(error, PermissionError):
        status = 403
    elif isinstance(error, LookupError):
        status = 404
    else:
        status = 400
    return jsonify({"error": {"code": status, "message": str(error)}}), status


@bp.route("/admin/agent-command-center", methods=("GET", "POST"))
@login_required
@owner_required
def admin_agent_command_center():
    agent_result = None
    if request.method == "POST":
        command = request.form.get("command", "")
        try:
            agent_result = respond_with_core_agent(g.user, command)
            audit("agent_command", "agent_run", str(agent_result["run_id"]))
            flash("Core Agent command completed.", "success")
        except (ValueError, PermissionError) as error:
            flash(str(error), "error")
    return render_template("admin_agent_command_center.html", data=admin_command_center_data(), agent_result=agent_result)


@bp.route("/doctor/availability", methods=("GET", "POST"))
@login_required
@role_required("doctor", "hospital")
def doctor_availability_page():
    if request.method == "POST":
        try:
            set_doctor_availability(g.user, request.form)
            audit("update", "doctor_availability", str(g.user["id"]))
            flash("Availability updated.", "success")
        except (ValueError, LookupError, PermissionError) as error:
            flash(str(error), "error")
        return redirect(url_for("milestone7.doctor_availability_page"))
    try:
        availability = get_doctor_availability(g.user["id"])
    except LookupError:
        availability = None
    return render_template("doctor_availability.html", availability=availability)


@bp.route("/messages", methods=("GET", "POST"))
@login_required
def messages_page():
    if request.method == "POST":
        action = request.form.get("action")
        try:
            if action == "start":
                conversation = start_conversation(g.user, request.form)
                audit("start", "conversation", str(conversation["id"]))
                flash("Conversation started.", "success")
                return redirect(url_for("milestone7.messages_page", conversation_id=conversation["id"]))
            if action == "send":
                message = send_message(g.user, int(request.form.get("conversation_id")), request.form)
                audit("message", "conversation", str(message["conversation_id"]))
                flash("Message sent.", "success")
                return redirect(url_for("milestone7.messages_page", conversation_id=message["conversation_id"]))
            if action == "share_video":
                message = share_video_message(g.user, int(request.form.get("conversation_id")), request.form)
                audit("share", "video_message", str(message["id"]))
                flash("Video shared.", "success")
                return redirect(url_for("milestone7.messages_page", conversation_id=message["conversation_id"]))
            if action == "share_report":
                message = share_report_message(g.user, int(request.form.get("conversation_id")), request.form)
                audit("share", "report_message", str(message["id"]))
                flash("Medical report shared with consent.", "success")
                return redirect(url_for("milestone7.messages_page", conversation_id=message["conversation_id"]))
        except (ValueError, LookupError, PermissionError) as error:
            flash(str(error), "error")
        return redirect(url_for("milestone7.messages_page"))

    conversations = list_conversations(g.user)
    selected = None
    messages = []
    selected_id = request.args.get("conversation_id")
    if selected_id:
        try:
            selected = get_conversation(g.user, int(selected_id))
            messages = list_messages(g.user, selected["id"])
        except (LookupError, PermissionError) as error:
            flash(str(error), "error")
    elif conversations:
        selected = conversations[0]
        messages = list_messages(g.user, selected["id"])
    contacts = discover_contacts(g.user, request.args.get("q", ""))
    return render_template(
        "messages.html",
        conversations=conversations,
        selected=selected,
        messages=messages,
        contacts=contacts,
        unread_total=unread_count(g.user),
        q=request.args.get("q", ""),
    )


@bp.get("/videos")
@login_required
def videos_page():
    q = request.args.get("q", "beginner mobility")
    category = request.args.get("category", "fitness")
    try:
        video_data = find_educational_video(g.user, q, category=category, max_results=6)
    except ValueError:
        video_data = {"available": False, "results": [], "reason": "Search for an exercise, health topic, or platform guide.", "guidance": build_video_guidance(q, category), "category": category}
    recent = get_db().execute(
        """
        SELECT query, category, provider, available, result_count, created_at
        FROM video_search_history
        WHERE user_id=?
        ORDER BY created_at DESC LIMIT 8
        """,
        (g.user["id"],),
    ).fetchall()
    return render_template(
        "videos.html",
        video_data=video_data,
        guidance=video_data.get("guidance") or build_video_guidance(q, category),
        categories=VIDEO_CATEGORIES,
        selected_category=video_data.get("category", category),
        q=q,
        recent_searches=[dict(row) for row in recent],
    )


@bp.route("/telehealth", methods=("GET", "POST"))
@login_required
def telehealth_page():
    if request.method == "POST":
        action = request.form.get("action")
        try:
            if action == "request_consultation":
                consultation = request_consultation(g.user, request.form)
                audit("request", "consultation", str(consultation["id"]))
                flash("Consultation request sent. The doctor must accept before chat, voice, or video controls are available.", "success")
            elif action == "update_status":
                consultation = update_consultation_status(g.user, int(request.form.get("consultation_id")), request.form.get("status"), request.form.get("scheduled_for"))
                audit("update", "consultation", str(consultation["id"]))
                flash("Consultation status updated.", "success")
            elif action == "send_message":
                message = send_consultation_message(g.user, int(request.form.get("consultation_id")), request.form)
                audit("message", "consultation", str(message["consultation_id"]))
                flash("Message sent securely.", "success")
        except (ValueError, LookupError, PermissionError) as error:
            flash(str(error), "error")
        return redirect(url_for("milestone7.telehealth_page"))
    return render_template("telehealth.html", consultations=list_consultations(g.user))


@bp.get("/telehealth/<int:consultation_id>")
@login_required
def telehealth_detail_page(consultation_id):
    try:
        consultation = get_consultation(g.user, consultation_id)
        messages = list_consultation_messages(g.user, consultation_id)
    except (LookupError, PermissionError) as error:
        flash(str(error), "error")
        return redirect(url_for("milestone7.telehealth_page"))
    return render_template("telehealth_detail.html", consultation=consultation, messages=messages)


@bp.route("/fitness/pose-coach", methods=("GET", "POST"))
@login_required
@role_required("patient")
def pose_coach_page():
    if request.method == "POST":
        try:
            session = save_pose_session(g.user, request.form)
            audit("create", "fitness_pose_session", str(session["id"]))
            return jsonify({"pose_session": session}), 201
        except (ValueError, LookupError, PermissionError) as error:
            return _api_error(error)
    return render_template("pose_coach.html", exercises=POSE_EXERCISES, sessions=list_pose_sessions(g.user))


@bp.get("/operations")
@login_required
@role_required("admin", "doctor", "hospital", "pharmacy")
def operations_page():
    return render_template("human_operations.html", tasks=list_staff_tasks(g.user))


@bp.post("/api/v1/agent/message")
def api_agent_message():
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        result = respond_with_core_agent(user, data.get("message", ""))
        audit("agent_command", "agent_run", str(result["run_id"]), actor=user)
        return jsonify(result)
    except (ValueError, PermissionError) as error:
        return _api_error(error)


@bp.get("/api/v1/admin/agent-command-center")
def api_admin_agent_command_center():
    user, error = require_api_user()
    if error:
        return error
    try:
        assert_owner(user)
    except PermissionError:
        abort(403)
    return jsonify(admin_command_center_data())


@bp.put("/api/v1/doctor/availability")
def api_set_doctor_availability():
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        availability = set_doctor_availability(user, data)
        audit("update", "doctor_availability", str(availability["doctor_id"]), actor=user)
        return jsonify({"doctor_availability": availability})
    except (ValueError, LookupError, PermissionError) as error:
        return _api_error(error)


@bp.get("/api/v1/doctor/<int:doctor_id>/availability")
def api_get_doctor_availability(doctor_id):
    user, error = require_api_user()
    if error:
        return error
    try:
        return jsonify({"doctor_availability": get_doctor_availability(doctor_id)})
    except LookupError as error:
        return _api_error(error)


@bp.get("/api/v1/contacts")
def api_contacts():
    user, error = require_api_user()
    if error:
        return error
    try:
        return jsonify({"contacts": discover_contacts(user, request.args.get("q", ""))})
    except (ValueError, PermissionError) as error:
        return _api_error(error)


@bp.get("/api/v1/conversations")
def api_list_conversations():
    user, error = require_api_user()
    if error:
        return error
    return jsonify({"conversations": list_conversations(user)})


@bp.post("/api/v1/conversations")
def api_start_conversation():
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        conversation = start_conversation(user, data)
        audit("start", "conversation", str(conversation["id"]), actor=user)
        return jsonify({"conversation": conversation}), 201
    except (ValueError, LookupError, PermissionError) as error:
        return _api_error(error)


@bp.get("/api/v1/conversations/<int:conversation_id>")
def api_get_conversation(conversation_id):
    user, error = require_api_user()
    if error:
        return error
    try:
        return jsonify({"conversation": get_conversation(user, conversation_id)})
    except (LookupError, PermissionError) as error:
        return _api_error(error)


@bp.get("/api/v1/conversations/<int:conversation_id>/messages")
def api_list_messages(conversation_id):
    user, error = require_api_user()
    if error:
        return error
    try:
        return jsonify({"messages": list_messages(user, conversation_id)})
    except (LookupError, PermissionError) as error:
        return _api_error(error)


@bp.post("/api/v1/conversations/<int:conversation_id>/messages")
def api_send_message(conversation_id):
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        message = send_message(user, conversation_id, data)
        audit("message", "conversation", str(conversation_id), actor=user)
        return jsonify({"message": message}), 201
    except (ValueError, LookupError, PermissionError) as error:
        return _api_error(error)


@bp.post("/api/v1/conversations/<int:conversation_id>/read")
def api_mark_conversation_read(conversation_id):
    user, error = require_api_user()
    if error:
        return error
    try:
        return jsonify(mark_read(user, conversation_id))
    except (LookupError, PermissionError) as error:
        return _api_error(error)


@bp.post("/api/v1/conversations/<int:conversation_id>/share-video")
def api_share_video(conversation_id):
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        message = share_video_message(user, conversation_id, data)
        audit("share", "video_message", str(message["id"]), actor=user)
        return jsonify({"message": message}), 201
    except (ValueError, LookupError, PermissionError) as error:
        return _api_error(error)


@bp.post("/api/v1/conversations/<int:conversation_id>/share-report")
def api_share_report(conversation_id):
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        message = share_report_message(user, conversation_id, data)
        audit("share", "report_message", str(message["id"]), actor=user)
        return jsonify({"message": message}), 201
    except (ValueError, LookupError, PermissionError) as error:
        return _api_error(error)


@bp.post("/api/v1/communication-permissions")
def api_create_communication_permission():
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        permission = create_communication_permission(user, data)
        audit("create", "communication_permission", str(permission["id"]), actor=user)
        return jsonify({"communication_permission": permission}), 201
    except (ValueError, LookupError, PermissionError) as error:
        return _api_error(error)


@bp.get("/api/v1/messages/unread-count")
def api_unread_count():
    user, error = require_api_user()
    if error:
        return error
    return jsonify({"unread_count": unread_count(user)})


@bp.get("/api/v1/consultations")
def api_list_consultations():
    user, error = require_api_user()
    if error:
        return error
    return jsonify({"consultations": list_consultations(user)})


@bp.post("/api/v1/consultations")
def api_request_consultation():
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        consultation = request_consultation(user, data)
        audit("request", "consultation", str(consultation["id"]), actor=user)
        return jsonify({"consultation": consultation}), 201
    except (ValueError, LookupError, PermissionError) as error:
        return _api_error(error)


@bp.post("/api/v1/consultations/<int:consultation_id>/status")
def api_update_consultation(consultation_id):
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        consultation = update_consultation_status(user, consultation_id, data.get("status"), data.get("scheduled_for"))
        audit("update", "consultation", str(consultation_id), actor=user)
        return jsonify({"consultation": consultation})
    except (ValueError, LookupError, PermissionError) as error:
        return _api_error(error)


@bp.get("/api/v1/consultations/<int:consultation_id>/messages")
def api_list_consultation_messages(consultation_id):
    user, error = require_api_user()
    if error:
        return error
    try:
        return jsonify({"messages": list_consultation_messages(user, consultation_id)})
    except (LookupError, PermissionError) as error:
        return _api_error(error)


@bp.post("/api/v1/consultations/<int:consultation_id>/messages")
def api_send_consultation_message(consultation_id):
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        message = send_consultation_message(user, consultation_id, data)
        audit("message", "consultation", str(consultation_id), actor=user)
        return jsonify({"message": message}), 201
    except (ValueError, LookupError, PermissionError) as error:
        return _api_error(error)


@bp.post("/api/v1/fitness/pose-sessions")
def api_save_pose_session():
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        session = save_pose_session(user, data)
        audit("create", "fitness_pose_session", str(session["id"]), actor=user)
        return jsonify({"pose_session": session}), 201
    except (ValueError, LookupError, PermissionError) as error:
        return _api_error(error)


@bp.get("/api/v1/video-intelligence/search")
def api_video_intelligence_search():
    user, error = require_api_user()
    if error:
        return error
    try:
        result = find_educational_video(user, request.args.get("q", ""), category=request.args.get("category", "fitness"))
        audit("search", "video_intelligence", result["category"], actor=user)
        return jsonify(result)
    except (ValueError, PermissionError) as error:
        return _api_error(error)


@bp.get("/api/v1/videos/guidance")
def api_video_guidance():
    user, error = require_api_user()
    if error:
        return error
    return jsonify({"guidance": build_video_guidance(request.args.get("q", ""), request.args.get("category", "fitness"))})


@bp.post("/api/v1/staff-profiles")
def api_upsert_staff_profile():
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        profile = upsert_staff_profile(user, data)
        audit("upsert", "staff_profile", str(profile["user_id"]), actor=user)
        return jsonify({"staff_profile": profile})
    except (ValueError, LookupError, PermissionError) as error:
        return _api_error(error)


@bp.get("/api/v1/staff-tasks")
def api_list_staff_tasks():
    user, error = require_api_user()
    if error:
        return error
    return jsonify({"staff_tasks": list_staff_tasks(user)})


@bp.post("/api/v1/staff-tasks")
def api_create_staff_task():
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        task = create_staff_task(user, data)
        audit("create", "staff_task", str(task["id"]), actor=user)
        return jsonify({"staff_task": task}), 201
    except (ValueError, LookupError, PermissionError) as error:
        return _api_error(error)


@bp.post("/api/v1/staff-tasks/<int:task_id>/status")
def api_update_staff_task(task_id):
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        task = update_staff_task(user, task_id, data.get("status"), data.get("message"))
        audit("update", "staff_task", str(task_id), actor=user)
        return jsonify({"staff_task": task})
    except (ValueError, LookupError, PermissionError) as error:
        return _api_error(error)
