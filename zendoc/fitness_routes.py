"""
Fitness & Lifestyle Intelligence Routes — Web UI & API v1.

Blueprint name: fitness
Web routes are patient-only (lifestyle data).
API endpoints require Bearer token auth via require_api_user().
Cross-user isolation enforced for all endpoints.
"""

from flask import (
    Blueprint,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from .exercise_library import get_exercise, list_exercises
from .fitness_analytics import get_fitness_progress, get_weight_trend_for_fitness
from .fitness_profile import get_fitness_profile, save_fitness_profile
from .nutrition import (
    get_hydration_summary,
    get_nutrition_summary,
    list_hydration_logs,
    list_nutrition_logs,
    log_food,
    log_water,
)
from .routes import audit, require_api_user
from .security import login_required, role_required
from .video_provider import search_fitness_video
from .workout_engine import (
    create_plan,
    get_latest_plan,
    get_plan,
    list_plans,
)
from .workout_tracking import (
    finish_session,
    get_session,
    list_sessions,
    log_set,
    start_session,
)


bp = Blueprint("fitness", __name__)


def _api_error(error):
    if isinstance(error, PermissionError):
        status = 403
    elif isinstance(error, LookupError):
        status = 404
    else:
        status = 400
    return jsonify({"error": {"code": status, "message": str(error)}}), status


# ---------------------------------------------------------------------------
# WEB ROUTES (Patients only)
# ---------------------------------------------------------------------------

@bp.route("/fitness")
@login_required
@role_required("patient")
def overview():
    profile = get_fitness_profile(g.user)
    latest_plan = get_latest_plan(g.user)
    recent_sessions = list_sessions(g.user, page=1, per_page=5)
    progress = get_fitness_progress(g.user, period="30d")
    nutrition_summary = get_nutrition_summary(g.user)
    hydration_summary = get_hydration_summary(g.user)

    # Active session check
    active_session = None
    if recent_sessions.get("sessions"):
        first = recent_sessions["sessions"][0]
        if first.get("status") == "active":
            active_session = first

    return render_template(
        "fitness_overview.html",
        profile=profile,
        latest_plan=latest_plan,
        recent_sessions=recent_sessions.get("sessions", []),
        active_session=active_session,
        progress=progress,
        nutrition=nutrition_summary,
        hydration=hydration_summary,
    )


@bp.route("/fitness/profile", methods=("GET", "POST"))
@login_required
@role_required("patient")
def profile_page():
    if request.method == "POST":
        equipment = request.form.getlist("equipment")
        preferred_days = request.form.getlist("preferred_days")
        data = {
            "fitness_goal": request.form.get("fitness_goal"),
            "experience_level": request.form.get("experience_level"),
            "preferred_workout_type": request.form.get("preferred_workout_type"),
            "workout_location": request.form.get("workout_location"),
            "equipment": equipment,
            "available_minutes": request.form.get("available_minutes"),
            "preferred_days": preferred_days,
            "height_cm": request.form.get("height_cm") or None,
            "weight_kg": request.form.get("weight_kg") or None,
            "limitations": request.form.get("limitations") or None,
            "target_weight_kg": request.form.get("target_weight_kg") or None,
        }
        try:
            save_fitness_profile(g.user, data)
            audit("update", "fitness_profile", str(g.user["id"]))
            flash("Fitness profile updated successfully.", "success")
            return redirect(url_for("fitness.overview"))
        except ValueError as error:
            flash(str(error), "error")

    profile = get_fitness_profile(g.user)
    return render_template("fitness_profile.html", profile=profile)


@bp.route("/fitness/plan")
@login_required
@role_required("patient")
def plan_page():
    plan_id = request.args.get("id")
    plan = None
    if plan_id:
        try:
            plan = get_plan(g.user, int(plan_id))
        except (ValueError, LookupError, PermissionError) as err:
            flash(str(err), "error")
    if not plan:
        plan = get_latest_plan(g.user)

    profile = get_fitness_profile(g.user)
    all_plans = list_plans(g.user, limit=5)
    return render_template("fitness_plan.html", plan=plan, profile=profile, all_plans=all_plans)


@bp.route("/fitness/plan/generate", methods=("POST",))
@login_required
@role_required("patient")
def generate_plan_web():
    label = request.form.get("name") or None
    try:
        plan = create_plan(g.user, label=label)
        audit("create", "workout_plan", str(plan["id"]))
        flash("New workout plan generated successfully!", "success")
        return redirect(url_for("fitness.plan_page", id=plan["id"]))
    except (ValueError, PermissionError) as error:
        flash(str(error), "error")
        return redirect(url_for("fitness.plan_page"))


@bp.route("/fitness/workout", methods=("GET", "POST"))
@login_required
@role_required("patient")
def workout_page():
    if request.method == "POST":
        action = request.form.get("action")
        session_id = request.form.get("session_id")
        if action == "start":
            plan_id = request.form.get("plan_id")
            plan_id = int(plan_id) if plan_id and plan_id.isdigit() else None
            label = request.form.get("name") or None
            try:
                sess = start_session(g.user, plan_id=plan_id, label=label)
                audit("start", "workout_session", str(sess["id"]))
                flash("Workout session started! Let's get moving.", "success")
                return redirect(url_for("fitness.workout_page", id=sess["id"]))
            except (ValueError, LookupError, PermissionError) as err:
                flash(str(err), "error")
                return redirect(url_for("fitness.overview"))

        elif action == "log_set" and session_id:
            exercise_id = int(request.form.get("exercise_id"))
            reps = request.form.get("completed_reps")
            notes = request.form.get("notes")
            try:
                log_set(
                    g.user,
                    int(session_id),
                    exercise_id,
                    completed_reps=int(reps) if reps and reps.isdigit() else None,
                    notes=notes,
                )
                flash("Set logged!", "success")
            except (ValueError, LookupError, PermissionError) as err:
                flash(str(err), "error")
            return redirect(url_for("fitness.workout_page", id=session_id))

        elif action == "finish" and session_id:
            notes = request.form.get("session_notes")
            try:
                res = finish_session(g.user, int(session_id), notes=notes)
                audit("complete", "workout_session", str(session_id))
                flash(f"Great job! Workout completed in {res['duration_minutes']} min and saved to your timeline.", "success")
                return redirect(url_for("fitness.overview"))
            except (ValueError, LookupError, PermissionError) as err:
                flash(str(err), "error")
                return redirect(url_for("fitness.workout_page", id=session_id))

    # GET
    session_id = request.args.get("id")
    active_session = None
    if session_id:
        try:
            active_session = get_session(g.user, int(session_id))
        except (ValueError, LookupError, PermissionError) as err:
            flash(str(err), "error")

    if not active_session:
        # Check if there is any active session
        recent = list_sessions(g.user, page=1, per_page=1)
        if recent.get("sessions") and recent["sessions"][0]["status"] == "active":
            active_session = get_session(g.user, recent["sessions"][0]["id"])

    latest_plan = get_latest_plan(g.user)
    return render_template("fitness_workout.html", session=active_session, latest_plan=latest_plan)


@bp.route("/fitness/exercises")
@login_required
@role_required("patient")
def exercises_page():
    category = request.args.get("category") or None
    equipment = request.args.get("equipment") or None
    difficulty = request.args.get("difficulty") or None
    q = request.args.get("q") or None

    data = list_exercises(category=category, equipment=equipment, difficulty=difficulty, q=q, limit=60)
    return render_template(
        "fitness_exercises.html",
        exercises=data["exercises"],
        total=data["total"],
        selected_category=category,
        selected_equipment=equipment,
        selected_difficulty=difficulty,
        q=q,
    )


@bp.route("/fitness/exercises/<int:exercise_id>")
@login_required
@role_required("patient")
def exercise_detail_page(exercise_id):
    try:
        ex = get_exercise(exercise_id)
    except LookupError:
        abort(404)
    # Search video tutorials for this exercise
    video_res = search_fitness_video(ex["name"], max_results=3)
    return render_template("fitness_exercise_detail.html", exercise=ex, videos=video_res)


@bp.route("/fitness/videos")
@login_required
@role_required("patient")
def videos_page():
    q = request.args.get("q", "home workout tutorial")
    res = search_fitness_video(q, max_results=6)
    return render_template("fitness_videos.html", video_data=res, q=q)


@bp.route("/fitness/progress")
@login_required
@role_required("patient")
def progress_page():
    period = request.args.get("period", "30d")
    progress = get_fitness_progress(g.user, period=period)
    weight_trend = get_weight_trend_for_fitness(g.user, period=period)
    recent_sessions = list_sessions(g.user, page=1, per_page=10)
    return render_template(
        "fitness_progress.html",
        progress=progress,
        weight_trend=weight_trend,
        sessions=recent_sessions.get("sessions", []),
        selected_period=period,
    )


@bp.route("/fitness/nutrition", methods=("GET", "POST"))
@login_required
@role_required("patient")
def nutrition_page():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "log_food":
            try:
                log_food(g.user, {
                    "food_name": request.form.get("food_name"),
                    "meal_type": request.form.get("meal_type", "other"),
                    "quantity_g": request.form.get("quantity_g") or None,
                    "calories_kcal": request.form.get("calories_kcal") or None,
                    "protein_g": request.form.get("protein_g") or None,
                    "carbs_g": request.form.get("carbs_g") or None,
                    "fat_g": request.form.get("fat_g") or None,
                    "notes": request.form.get("notes") or None,
                })
                audit("create", "nutrition_log", str(g.user["id"]))
                flash("Food logged!", "success")
            except ValueError as err:
                flash(str(err), "error")

    date_str = request.args.get("date")
    summary = get_nutrition_summary(g.user, date=date_str)
    logs_data = list_nutrition_logs(g.user, date=date_str)
    return render_template("fitness_nutrition.html", summary=summary, logs=logs_data.get("logs", []))


@bp.route("/fitness/hydration", methods=("GET", "POST"))
@login_required
@role_required("patient")
def hydration_page():
    if request.method == "POST":
        ml = request.form.get("ml")
        try:
            log_water(g.user, ml)
            audit("create", "hydration_log", str(g.user["id"]))
            flash(f"Logged {ml} ml water!", "success")
        except ValueError as err:
            flash(str(err), "error")

    date_str = request.args.get("date")
    summary = get_hydration_summary(g.user, date=date_str)
    logs_data = list_hydration_logs(g.user, date=date_str)
    return render_template("fitness_hydration.html", summary=summary, logs=logs_data.get("logs", []))


# ---------------------------------------------------------------------------
# API V1 ENDPOINTS (Mobile / REST architecture)
# ---------------------------------------------------------------------------

@bp.get("/api/v1/fitness-profile")
def api_get_fitness_profile():
    user, error = require_api_user()
    if error:
        return error
    try:
        profile = get_fitness_profile(user)
        return jsonify({"fitness_profile": profile})
    except (PermissionError, LookupError, ValueError) as err:
        return _api_error(err)


@bp.put("/api/v1/fitness-profile")
def api_update_fitness_profile():
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        profile = save_fitness_profile(user, data)
        audit("update", "fitness_profile", str(user["id"]), actor=user)
        return jsonify({"status": "saved", "fitness_profile": profile})
    except (PermissionError, LookupError, ValueError) as err:
        return _api_error(err)


@bp.get("/api/v1/fitness/exercises")
def api_list_exercises():
    user, error = require_api_user()
    if error:
        return error
    category = request.args.get("category")
    equipment = request.args.get("equipment")
    difficulty = request.args.get("difficulty")
    q = request.args.get("q")
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 50))
    offset = (page - 1) * per_page
    res = list_exercises(category=category, equipment=equipment, difficulty=difficulty, q=q, limit=per_page, offset=offset)
    return jsonify(res)


@bp.get("/api/v1/fitness/exercises/<int:exercise_id>")
def api_get_exercise(exercise_id):
    user, error = require_api_user()
    if error:
        return error
    try:
        ex = get_exercise(exercise_id)
        return jsonify({"exercise": ex})
    except LookupError as err:
        return _api_error(err)


@bp.get("/api/v1/fitness/plans")
def api_list_plans():
    user, error = require_api_user()
    if error:
        return error
    plans = list_plans(user)
    return jsonify({"workout_plans": plans})


@bp.post("/api/v1/fitness/plans")
def api_create_plan():
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    label = data.get("name") or None
    try:
        plan = create_plan(user, label=label)
        audit("create", "workout_plan", str(plan["id"]), actor=user)
        return jsonify({"workout_plan": plan}), 201
    except (ValueError, PermissionError) as err:
        return _api_error(err)


@bp.get("/api/v1/fitness/plans/<int:plan_id>")
def api_get_plan(plan_id):
    user, error = require_api_user()
    if error:
        return error
    try:
        plan = get_plan(user, plan_id)
        return jsonify({"workout_plan": plan})
    except (LookupError, PermissionError) as err:
        return _api_error(err)


@bp.get("/api/v1/fitness/sessions")
def api_list_sessions():
    user, error = require_api_user()
    if error:
        return error
    page = request.args.get("page", 1)
    per_page = request.args.get("per_page", 20)
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    data = list_sessions(user, page=page, per_page=per_page, start_date=start_date, end_date=end_date)
    return jsonify(data)


@bp.post("/api/v1/fitness/sessions")
def api_start_session():
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    plan_id = data.get("plan_id")
    label = data.get("name")
    try:
        sess = start_session(user, plan_id=plan_id, label=label)
        audit("start", "workout_session", str(sess["id"]), actor=user)
        return jsonify({"workout_session": sess}), 201
    except (LookupError, PermissionError, ValueError) as err:
        return _api_error(err)


@bp.get("/api/v1/fitness/sessions/<int:session_id>")
def api_get_session(session_id):
    user, error = require_api_user()
    if error:
        return error
    try:
        sess = get_session(user, session_id)
        return jsonify({"workout_session": sess})
    except (LookupError, PermissionError) as err:
        return _api_error(err)


@bp.post("/api/v1/fitness/sessions/<int:session_id>/sets")
def api_log_set(session_id):
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    exercise_id = data.get("exercise_id")
    if not exercise_id:
        return jsonify({"error": {"code": 400, "message": "exercise_id is required."}}), 400
    try:
        res = log_set(
            user,
            session_id,
            int(exercise_id),
            completed_reps=data.get("completed_reps"),
            duration_seconds=data.get("duration_seconds"),
            notes=data.get("notes"),
            set_number=data.get("set_number"),
        )
        return jsonify(res), 200
    except (LookupError, PermissionError, ValueError) as err:
        return _api_error(err)


@bp.post("/api/v1/fitness/sessions/<int:session_id>/complete")
def api_complete_session(session_id):
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        res = finish_session(user, session_id, notes=data.get("notes"))
        audit("complete", "workout_session", str(session_id), actor=user)
        return jsonify(res)
    except (LookupError, PermissionError, ValueError) as err:
        return _api_error(err)


@bp.get("/api/v1/fitness/progress")
def api_fitness_progress():
    user, error = require_api_user()
    if error:
        return error
    period = request.args.get("period", "30d")
    progress = get_fitness_progress(user, period=period)
    weight_trend = get_weight_trend_for_fitness(user, period=period)
    return jsonify({"progress": progress, "weight_trend": weight_trend})


@bp.get("/api/v1/fitness/videos")
def api_fitness_videos():
    user, error = require_api_user()
    if error:
        return error
    q = request.args.get("q", "")
    max_res = request.args.get("max_results", 5)
    res = search_fitness_video(q, max_results=max_res)
    return jsonify(res)


@bp.get("/api/v1/nutrition/logs")
def api_list_nutrition_logs():
    user, error = require_api_user()
    if error:
        return error
    date_str = request.args.get("date")
    page = request.args.get("page", 1)
    per_page = request.args.get("per_page", 50)
    data = list_nutrition_logs(user, date=date_str, page=page, per_page=per_page)
    return jsonify(data)


@bp.post("/api/v1/nutrition/logs")
def api_log_food():
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        res = log_food(user, data)
        audit("create", "nutrition_log", str(res["id"]), actor=user)
        return jsonify({"nutrition_log": res}), 201
    except ValueError as err:
        return _api_error(err)


@bp.get("/api/v1/nutrition/summary")
def api_nutrition_summary():
    user, error = require_api_user()
    if error:
        return error
    date_str = request.args.get("date")
    summary = get_nutrition_summary(user, date=date_str)
    return jsonify({"nutrition_summary": summary})


@bp.get("/api/v1/hydration/logs")
def api_list_hydration_logs():
    user, error = require_api_user()
    if error:
        return error
    date_str = request.args.get("date")
    data = list_hydration_logs(user, date=date_str)
    return jsonify(data)


@bp.post("/api/v1/hydration/logs")
def api_log_water():
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    ml = data.get("ml")
    if ml is None:
        return jsonify({"error": {"code": 400, "message": "ml is required."}}), 400
    try:
        res = log_water(user, ml)
        audit("create", "hydration_log", str(res["id"]), actor=user)
        return jsonify({"hydration_log": res}), 201
    except ValueError as err:
        return _api_error(err)


@bp.get("/api/v1/hydration/summary")
def api_hydration_summary():
    user, error = require_api_user()
    if error:
        return error
    date_str = request.args.get("date")
    summary = get_hydration_summary(user, date=date_str)
    return jsonify({"hydration_summary": summary})
