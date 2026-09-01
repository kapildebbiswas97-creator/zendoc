import time
from datetime import datetime, timedelta, timezone

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from .ai import MODEL_VERSION, assistant_answer, doctor_prediction, mental_health_support
from .auth import ACCOUNT_EXISTS_MESSAGE, INVALID_CREDENTIALS_MESSAGE, email_exists, user_by_normalized_email, validate_email
from .db import ROLES, get_db, is_integrity_error, now_iso
from .health_analytics import METRIC_TYPES, create_measurement, get_health_trend
from .healthcare_finder import HealthcareFinder, normalize_query
from .intelligence import ZendocIntelligence
from .provider_service import (
    PROVIDER_ROLES,
    SPECIALTIES,
    VERIFICATION_STATES,
    available_slots,
    book_provider_slot,
    create_schedule,
    get_provider_profile_for_user,
    get_public_provider_profile,
    upsert_provider_profile,
)
from .report_intelligence import REPORT_TYPES, store_report_upload
from .record_storage import get_record_storage
from .security import csrf_token, hash_token, is_owner, load_user_and_check_csrf, login_required, new_token, owner_required, role_required, start_user_session


bp = Blueprint("main", __name__)
ALLOWED_UPLOADS = {"pdf", "png", "jpg", "jpeg", "txt", "doc", "docx"}
ALLOWED_MIME_PREFIXES = ("application/pdf", "image/", "text/plain")
RATE_BUCKETS = {}


@bp.before_app_request
def before_request():
    auth_response = load_user_and_check_csrf()
    if auth_response is not None:
        return auth_response
    check_rate_limit()


def future_iso(minutes):
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat(timespec="seconds")


@bp.app_errorhandler(400)
def bad_request(error):
    return render_error(error, 400, "Bad request")


@bp.app_errorhandler(401)
def unauthorized(error):
    return render_error(error, 401, "Unauthorized")


@bp.app_errorhandler(403)
def forbidden(error):
    return render_error(error, 403, "Forbidden")


@bp.app_errorhandler(404)
def not_found(error):
    return render_error(error, 404, "Not found")


@bp.app_errorhandler(429)
def too_many_requests(error):
    return render_error(error, 429, "Too many requests")


@bp.app_errorhandler(500)
def server_error(error):
    current_app.logger.exception("Unhandled server error: %s", error)
    return render_error(error, 500, "Internal server error")


def render_error(error, status, message):
    if request.path.startswith("/api/"):
        return jsonify({"error": {"code": status, "message": message}}), status
    return render_template("error.html", status=status, message=message), status


def check_rate_limit():
    if not request.path.startswith("/api/"):
        return
    limit = current_app.config.get("RATE_LIMIT_PER_MINUTE", 120)
    bucket_key = f"{request.remote_addr}:{request.path}"
    now = int(time.time())
    window = now // 60
    bucket = RATE_BUCKETS.get(bucket_key)
    if not bucket or bucket["window"] != window:
        RATE_BUCKETS[bucket_key] = {"window": window, "count": 1}
        return
    bucket["count"] += 1
    if bucket["count"] > limit:
        abort(429)


@bp.app_context_processor
def globals_for_templates():
    return {"csrf_token": csrf_token(), "current_user": g.get("user"), "roles": ROLES, "specialties": SPECIALTIES}


def normalize_role(role):
    role = (role or "").lower()
    if role not in ROLES:
        abort(404)
    return role


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_UPLOADS


def allowed_mimetype(mimetype):
    return not mimetype or mimetype in ALLOWED_MIME_PREFIXES or any(mimetype.startswith(prefix) for prefix in ALLOWED_MIME_PREFIXES)


def require_form_fields(*fields):
    missing = [field for field in fields if not request.form.get(field, "").strip()]
    if missing:
        flash(f"Missing required fields: {', '.join(missing)}.", "error")
        return False
    return True


def require_json_fields(data, *fields):
    missing = [field for field in fields if not str(data.get(field, "")).strip()]
    if missing:
        return jsonify({"error": {"code": 400, "message": f"Missing required fields: {', '.join(missing)}"}}), 400
    return None


def create_notification(user_id, title, message):
    from .notification_providers import deliver_notification
    return deliver_notification(user_id, title, message, channel="in_app")


def get_or_create_conversation(user_id, conversation_id=None, title=None):
    db = get_db()
    if conversation_id:
        row = db.execute(
            "SELECT * FROM ai_conversations WHERE id=? AND user_id=?",
            (conversation_id, user_id),
        ).fetchone()
        if row:
            return row
    now = now_iso()
    cursor = db.execute(
        "INSERT INTO ai_conversations (user_id,title,created_at,updated_at) VALUES (?,?,?,?)",
        (user_id, title or "ZENDOC conversation", now, now),
    )
    db.commit()
    return db.execute("SELECT * FROM ai_conversations WHERE id=?", (cursor.lastrowid,)).fetchone()


def log_ai_interaction(user_id, feature, input_text, result, latency_ms=None, conversation_id=None):
    if isinstance(result, dict):
        intent = result.get("intent", feature)
        output_text = result.get("message") or result.get("summary", "")
        risk_level = result.get("urgency") or result.get("risk_level", "low")
        provider = result.get("provider", "legacy")
        emergency = result.get("emergency", False)
        success = result.get("success", True)
    else:
        intent = getattr(result, "intent", feature)
        output_text = getattr(result, "message", "")
        risk_level = getattr(result, "urgency", "low")
        provider = getattr(result, "provider", "structured")
        emergency = getattr(result, "emergency", False)
        success = getattr(result, "success", True)
    get_db().execute(
        """
        INSERT INTO ai_interactions
        (user_id,conversation_id,feature,intent,input_text,output_text,risk_level,model_version,provider,emergency,success,latency_ms,created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            user_id,
            conversation_id,
            feature,
            intent,
            input_text[:500],
            output_text,
            risk_level,
            MODEL_VERSION,
            provider,
            1 if emergency else 0,
            1 if success else 0,
            latency_ms,
            now_iso(),
        ),
    )


def audit(action, entity_type, entity_id=None, actor=None):
    audit_actor = actor or g.get("user")
    actor_id = audit_actor["id"] if audit_actor else None
    get_db().execute(
        "INSERT INTO audit_logs (actor_id, action, entity_type, entity_id, created_at) VALUES (?, ?, ?, ?, ?)",
        (actor_id, action, entity_type, entity_id, now_iso()),
    )


def stats_for(user):
    db = get_db()
    if user["role"] == "admin":
        return {
            "Users": db.execute("SELECT COUNT(*) c FROM users").fetchone()["c"],
            "Appointments": db.execute("SELECT COUNT(*) c FROM appointments").fetchone()["c"],
            "Records": db.execute("SELECT COUNT(*) c FROM medical_records").fetchone()["c"],
            "Providers": db.execute("SELECT COUNT(*) c FROM provider_profiles").fetchone()["c"],
        }
    return {
        "Appointments": db.execute(
            "SELECT COUNT(*) c FROM appointments WHERE patient_id=? OR provider_id=?",
            (user["id"], user["id"]),
        ).fetchone()["c"],
        "Records": db.execute("SELECT COUNT(*) c FROM medical_records WHERE owner_id=?", (user["id"],)).fetchone()["c"],
        "Unread": db.execute(
            "SELECT COUNT(*) c FROM notifications WHERE user_id=? AND is_read=0",
            (user["id"],),
        ).fetchone()["c"],
        "AI Uses": db.execute("SELECT COUNT(*) c FROM ai_interactions WHERE user_id=?", (user["id"],)).fetchone()["c"],
    }


@bp.get("/")
def home():
    return render_template("index.html")


@bp.route("/register/<role>", methods=("GET", "POST"))
def register(role):
    role = normalize_role(role)
    if role == "admin":
        abort(403)
    if request.method == "POST":
        if not require_form_fields("name", "email", "password"):
            return render_template("register.html", role=role), 400
        password = request.form.get("password", "")
        try:
            email = validate_email(request.form.get("email", ""))
        except ValueError as error:
            flash(str(error), "error")
            return render_template("register.html", role=role), 400
        if email_exists(email):
            flash(ACCOUNT_EXISTS_MESSAGE, "error")
            return render_template("register.html", role=role), 409
        if len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
            return render_template("register.html", role=role), 400
        try:
            now = now_iso()
            get_db().execute(
                """
                INSERT INTO users
                (name,email,email_normalized,password_hash,role,phone,age,gender,city,emergency_contact,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    request.form.get("name", "").strip(),
                    email,
                    email,
                    generate_password_hash(password),
                    role,
                    request.form.get("phone", "").strip(),
                    request.form.get("age") or None,
                    request.form.get("gender", "").strip(),
                    request.form.get("city", "").strip(),
                    request.form.get("emergency_contact", "").strip(),
                    now,
                    now,
                ),
            )
            get_db().commit()
            flash("Registration complete. Please log in.", "success")
            return redirect(url_for("main.login", role=role))
        except Exception as error:
            if not is_integrity_error(error):
                raise
            get_db().rollback()
            flash(ACCOUNT_EXISTS_MESSAGE, "error")
            return render_template("register.html", role=role), 409
    return render_template("register.html", role=role)


@bp.route("/login/<role>", methods=("GET", "POST"))
def login(role):
    role = normalize_role(role)
    if request.method == "POST":
        if not require_form_fields("email", "password"):
            return render_template("login.html", role=role), 400
        try:
            email = validate_email(request.form.get("email", ""))
        except ValueError:
            email = ""
        user = user_by_normalized_email(email, role=role) if email else None
        if user and user["role"] == "admin" and not is_owner(user):
            user = None
        if user and check_password_hash(user["password_hash"], request.form.get("password", "")):
            start_user_session(user, remember=bool(request.form.get("remember_me")))
            audit("login", "user", str(user["id"]))
            get_db().commit()
            return redirect(url_for("main.dashboard"))
        flash(INVALID_CREDENTIALS_MESSAGE, "error")
    return render_template("login.html", role=role)


@bp.route("/forgot-password", methods=("GET", "POST"))
def forgot_password():
    if request.method == "POST":
        if current_app.config.get("PASSWORD_RECOVERY_MODE") != "local_demo":
            flash(
                "Password recovery delivery is not integrated yet. Contact the ZENDOC owner for controlled account recovery.",
                "warning",
            )
            return render_template("forgot_password.html"), 503
        email = ""
        try:
            email = validate_email(request.form.get("email", ""))
        except ValueError:
            pass
        user = user_by_normalized_email(email) if email else None
        if user:
            token = new_token()
            get_db().execute(
                "INSERT INTO api_tokens (user_id, token_hash, token_type, expires_at, created_at) VALUES (?, ?, 'password_reset', ?, ?)",
                (user["id"], hash_token(token), future_iso(30), now_iso()),
            )
            get_db().commit()
            flash("Local beta recovery token generated. It expires in 30 minutes; email delivery is not connected.", "success")
            return redirect(url_for("main.reset_password", token=token))
        flash("If the account exists, instructions have been generated.", "success")
    return render_template("forgot_password.html")


@bp.route("/reset-password", methods=("GET", "POST"))
def reset_password():
    token = request.args.get("token") or request.form.get("token", "")
    if request.method == "POST":
        password = request.form.get("password", "")
        if len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
            return render_template("reset_password.html", token=token), 400
        token_digest = hash_token(token)
        tok_row = get_db().execute(
            """
            SELECT * FROM api_tokens
            WHERE token_hash=? AND token_type='password_reset' AND revoked_at IS NULL
              AND expires_at IS NOT NULL AND expires_at>?
            """,
            (token_digest, now_iso()),
        ).fetchone()
        if not tok_row:
            flash("Invalid or expired password reset token.", "error")
            return render_template("reset_password.html", token=token), 400
        user_id = tok_row["user_id"]
        get_db().execute("UPDATE users SET password_hash=?, updated_at=? WHERE id=?", (generate_password_hash(password), now_iso(), user_id))
        get_db().execute("UPDATE api_tokens SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL", (now_iso(), user_id))
        get_db().commit()
        flash("Password reset successful. Please log in with your new password.", "success")
        return redirect(url_for("main.login", role="patient"))
    return render_template("reset_password.html", token=token)


@bp.route("/logout", methods=("GET", "POST"))
def logout():
    if request.method == "GET" and not current_app.config.get("ALLOW_LEGACY_GET_LOGOUT", False):
        abort(405)
    session.clear()
    flash("Logged out.", "success")
    return redirect(url_for("main.home"))


@bp.get("/dashboard")
@login_required
def dashboard():
    rows = get_db().execute(
        """
        SELECT a.*, p.name patient_name
        FROM appointments a JOIN users p ON p.id=a.patient_id
        WHERE a.patient_id=? OR a.provider_id=? OR ?='admin'
        ORDER BY a.created_at DESC LIMIT 6
        """,
        (g.user["id"], g.user["id"], g.user["role"]),
    ).fetchall()
    return render_template("dashboard.html", stats=stats_for(g.user), appointments=rows)


@bp.route("/profile", methods=("GET", "POST"))
@login_required
def profile():
    if request.method == "POST":
        get_db().execute(
            """
            UPDATE users SET name=?, phone=?, age=?, gender=?, city=?, emergency_contact=?, updated_at=? WHERE id=?
            """,
            (
                request.form.get("name", "").strip(),
                request.form.get("phone", "").strip(),
                request.form.get("age") or None,
                request.form.get("gender", "").strip(),
                request.form.get("city", "").strip(),
                request.form.get("emergency_contact", "").strip(),
                now_iso(),
                g.user["id"],
            ),
        )
        audit("update", "profile", str(g.user["id"]))
        get_db().commit()
        flash("Profile updated.", "success")
        return redirect(url_for("main.profile"))
    return render_template("profile.html")


@bp.route("/appointments", methods=("GET", "POST"))
@login_required
def appointments():
    db = get_db()
    if request.method == "POST":
        provider_profile_id = request.form.get("provider_profile_id") or None
        provider_profile = None
        if provider_profile_id:
            try:
                book_provider_slot(g.user, int(provider_profile_id), request.form.get("scheduled_for"), request.form.get("reason", "").strip())
                create_notification(g.user["id"], "Appointment requested", "Your connected appointment request was saved.")
                audit("create", "connected_appointment")
                db.commit()
                flash("Connected appointment saved.", "success")
                return redirect(url_for("main.appointments"))
            except (ValueError, PermissionError) as error:
                flash(str(error), "error")
                return redirect(url_for("main.appointments"))
        provider_email = request.form.get("provider_email", "").strip().lower()
        provider = db.execute("SELECT id,name FROM users WHERE email=?", (provider_email,)).fetchone()
        provider_id = provider["id"] if provider else None
        provider_name = provider["name"] if provider else request.form.get("provider_name", "Provider").strip()
        db.execute(
            """
            INSERT INTO appointments
            (patient_id,provider_id,provider_name,scheduled_for,reason,status,created_at,updated_at)
            VALUES (?,?,?,?,?,'requested',?,?)
            """,
            (
                g.user["id"],
                provider_id,
                provider_name,
                request.form.get("scheduled_for"),
                request.form.get("reason", "").strip(),
                now_iso(),
                now_iso(),
            ),
        )
        create_notification(g.user["id"], "Appointment requested", "Your appointment request was saved.")
        audit("create", "appointment")
        db.commit()
        flash("Appointment saved.", "success")
        return redirect(url_for("main.appointments"))
    rows = db.execute(
        """
        SELECT a.*, p.name patient_name
        FROM appointments a JOIN users p ON p.id=a.patient_id
        WHERE a.patient_id=? OR a.provider_id=? OR ?='admin'
        ORDER BY a.scheduled_for DESC
        """,
        (g.user["id"], g.user["id"], g.user["role"]),
    ).fetchall()
    providers = db.execute(
        """
        SELECT p.*, u.name FROM provider_profiles p
        JOIN users u ON u.id=p.user_id
        WHERE p.verification_status='verified'
        ORDER BY p.specialty, p.organization
        """
    ).fetchall()
    return render_template("appointments.html", appointments=rows, providers=providers)


@bp.post("/appointments/<int:appointment_id>/status")
@role_required("doctor", "hospital", "admin")
def appointment_status(appointment_id):
    status = request.form.get("status", "requested")
    if status not in {"requested", "confirmed", "completed", "cancelled"}:
        abort(400)
    row = get_db().execute("SELECT patient_id, provider_id FROM appointments WHERE id=?", (appointment_id,)).fetchone()
    if not row:
        abort(404)
    if g.user["role"] != "admin" and row["provider_id"] != g.user["id"]:
        abort(403)
    get_db().execute("UPDATE appointments SET status=?, updated_at=? WHERE id=?", (status, now_iso(), appointment_id))
    create_notification(row["patient_id"], "Appointment updated", f"Appointment status changed to {status}.")
    audit("update_status", "appointment", str(appointment_id))
    get_db().commit()
    flash("Appointment status updated.", "success")
    return redirect(url_for("main.appointments"))


@bp.route("/records", methods=("GET", "POST"))
@login_required
def records():
    db = get_db()
    if request.method == "POST":
        upload = request.files.get("record_file")
        if not require_form_fields("title", "category"):
            return redirect(url_for("main.records"))
        try:
            record_id = store_report_upload(upload, g.user["id"], g.user["id"], request.form)
        except ValueError as error:
            flash(str(error), "error")
            return redirect(url_for("main.records"))
        create_notification(g.user["id"], "Record uploaded", "A medical record was added.")
        audit("upload", "medical_record", str(record_id))
        db.commit()
        flash("Record uploaded.", "success")
        return redirect(url_for("main.records"))
    rows = db.execute(
        """
        SELECT mr.*, rm.report_uid, rm.report_type, rm.document_date, rm.extraction_status
        FROM medical_records mr LEFT JOIN report_metadata rm ON rm.record_id=mr.id
        WHERE mr.owner_id=? OR ?='admin' ORDER BY mr.created_at DESC
        """,
        (g.user["id"], g.user["role"]),
    ).fetchall()
    return render_template("records.html", records=rows, report_types=REPORT_TYPES)


@bp.get("/records/<int:record_id>/download")
@login_required
def download_record(record_id):
    record = get_db().execute("SELECT * FROM medical_records WHERE id=?", (record_id,)).fetchone()
    if not record:
        abort(404)
    if g.user["role"] != "admin" and record["owner_id"] != g.user["id"]:
        abort(403)
    audit("download", "medical_record", str(record_id))
    get_db().commit()
    return get_record_storage().response(record["stored_filename"], record["original_filename"])


@bp.route("/health", methods=("GET", "POST"))
@login_required
def health():
    if request.method == "POST":
        if not require_form_fields("metric_type", "metric_value"):
            return render_template(
                "health.html", metrics=[], metric_types=METRIC_TYPES, trend=None, selected_metric="weight"
            ), 400
        try:
            if g.user["role"] == "patient":
                create_measurement(g.user, request.form)
            else:
                get_db().execute(
                    "INSERT INTO health_metrics (user_id,metric_type,metric_value,unit,recorded_at,source) VALUES (?,?,?,?,?,'manual')",
                    (
                        g.user["id"], request.form.get("metric_type", "").strip(),
                        request.form.get("metric_value", "").strip(), request.form.get("unit", "").strip(), now_iso(),
                    ),
                )
        except ValueError as error:
            flash(str(error), "error")
            return redirect(url_for("main.health"))
        audit("create", "health_metric")
        get_db().commit()
        flash("Health metric saved.", "success")
        return redirect(url_for("main.health"))
    rows = get_db().execute(
        "SELECT * FROM health_metrics WHERE user_id=? ORDER BY recorded_at DESC LIMIT 50",
        (g.user["id"],),
    ).fetchall()
    trend = None
    if g.user["role"] == "patient":
        selected_metric = request.args.get("metric", "weight")
        try:
            trend = get_health_trend(g.user, selected_metric, period=request.args.get("period", "90d"))
        except ValueError:
            selected_metric = "weight"
            trend = get_health_trend(g.user, selected_metric, period="90d")
    return render_template("health.html", metrics=rows, metric_types=METRIC_TYPES, trend=trend, selected_metric=selected_metric if g.user["role"] == "patient" else None)


@bp.route("/ai", methods=("GET", "POST"))
@login_required
def ai_center():
    result = None
    intelligence_result = None
    if request.method == "POST":
        feature = request.form.get("feature")
        if feature == "zendoc_ai":
            input_text = request.form.get("message", "")
            if not input_text.strip():
                flash("Please enter a message for ZENDOC AI.", "error")
                return redirect(url_for("main.ai_center"))
            conversation = get_or_create_conversation(
                g.user["id"],
                request.form.get("conversation_id") or None,
                title=input_text[:60],
            )
            intelligence_result, latency_ms = ZendocIntelligence().respond(input_text, user=g.user, conversation=conversation)
            get_db().execute(
                "UPDATE ai_conversations SET last_intent=?, updated_at=? WHERE id=? AND user_id=?",
                (intelligence_result.intent, now_iso(), conversation["id"], g.user["id"]),
            )
            log_ai_interaction(g.user["id"], "zendoc_ai", input_text, intelligence_result, latency_ms, conversation["id"])
            audit("use", "ai", "zendoc_ai")
            get_db().commit()
        elif feature == "doctor":
            input_text = request.form.get("symptoms", "")
            result = doctor_prediction(input_text)
        elif feature == "assistant":
            input_text = request.form.get("message", "")
            result = {"summary": assistant_answer(input_text), "risk_level": "low", "next_steps": "Continue in ZENDOC."}
        elif feature == "mental_health":
            input_text = f"{request.form.get('age_group')} stress={request.form.get('stress_level')} {request.form.get('context')}"
            result = mental_health_support(
                request.form.get("age_group", "adult"),
                request.form.get("context", ""),
                request.form.get("stress_level", 0),
            )
        else:
            abort(400)
        if result is not None:
            log_ai_interaction(g.user["id"], feature, input_text, result)
            audit("use", "ai", feature)
            get_db().commit()
    history = get_db().execute(
        "SELECT * FROM ai_interactions WHERE user_id=? ORDER BY created_at DESC LIMIT 12",
        (g.user["id"],),
    ).fetchall()
    conversations = get_db().execute(
        "SELECT * FROM ai_conversations WHERE user_id=? ORDER BY updated_at DESC LIMIT 10",
        (g.user["id"],),
    ).fetchall()
    return render_template("ai.html", result=result, intelligence_result=intelligence_result, history=history, conversations=conversations)


@bp.get("/notifications")
@login_required
def notifications():
    rows = get_db().execute(
        "SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT 50",
        (g.user["id"],),
    ).fetchall()
    get_db().execute("UPDATE notifications SET is_read=1 WHERE user_id=?", (g.user["id"],))
    get_db().commit()
    return render_template("notifications.html", notifications=rows)


@bp.route("/finder", methods=("GET", "POST"))
@login_required
def finder():
    result = None
    query = normalize_query(
        request.values.get("category"),
        request.values.get("specialty"),
        request.values.get("location"),
        request.values.get("latitude"),
        request.values.get("longitude"),
        request.values.get("radius_km", 10),
    )
    if request.method == "POST" or request.args:
        result = HealthcareFinder().search(query)
        audit("search", "healthcare_finder", query["category"])
        get_db().commit()
    return render_template("finder.html", result=result, query=query)


@bp.get("/providers/<int:profile_id>")
@login_required
def provider_detail(profile_id):
    profile = get_public_provider_profile(profile_id)
    if not profile:
        abort(404)

    selected_date = (request.args.get("date") or "").strip()
    slots = available_slots(profile_id, selected_date) if selected_date else []
    if not selected_date:
        today = datetime.now(timezone.utc).date()
        for day_offset in range(0, 15):
            candidate = (today + timedelta(days=day_offset)).isoformat()
            candidate_slots = available_slots(profile_id, candidate)
            if candidate_slots:
                selected_date = candidate
                slots = candidate_slots
                break
        if not selected_date:
            selected_date = (today + timedelta(days=1)).isoformat()

    schedules = get_db().execute(
        """
        SELECT weekday, start_time, end_time, slot_minutes
        FROM provider_schedules
        WHERE provider_profile_id=? AND active=1
        ORDER BY weekday, start_time
        """,
        (profile_id,),
    ).fetchall()
    return render_template(
        "provider_detail.html",
        profile=profile,
        schedules=schedules,
        selected_date=selected_date,
        slots=slots,
    )


@bp.route("/provider/profile", methods=("GET", "POST"))
@login_required
def provider_profile():
    if g.user["role"] not in PROVIDER_ROLES:
        abort(403)
    if request.method == "POST":
        try:
            upsert_provider_profile(g.user, request.form)
            audit("upsert", "provider_profile", str(g.user["id"]))
            get_db().commit()
            flash("Provider profile saved for admin verification.", "success")
            return redirect(url_for("main.provider_profile"))
        except (ValueError, PermissionError) as error:
            flash(str(error), "error")
    profile_row = get_provider_profile_for_user(g.user["id"])
    schedules = []
    if profile_row:
        schedules = get_db().execute(
            "SELECT * FROM provider_schedules WHERE provider_profile_id=? ORDER BY weekday,start_time",
            (profile_row["id"],),
        ).fetchall()
    return render_template("provider_profile.html", profile=profile_row, schedules=schedules)


@bp.post("/provider/schedules")
@login_required
def provider_schedule():
    if g.user["role"] not in PROVIDER_ROLES:
        abort(403)
    try:
        create_schedule(g.user, request.form)
        audit("create", "provider_schedule", str(g.user["id"]))
        get_db().commit()
        flash("Schedule saved.", "success")
    except (ValueError, PermissionError) as error:
        flash(str(error), "error")
    return redirect(url_for("main.provider_profile"))


@bp.get("/admin")
@owner_required
def admin():
    db = get_db()
    users = db.execute("SELECT id,name,email,role,verified,active,created_at FROM users ORDER BY created_at DESC").fetchall()
    providers = db.execute(
        """
        SELECT p.*, u.name, u.email, u.role FROM provider_profiles p
        JOIN users u ON u.id=p.user_id
        ORDER BY p.updated_at DESC
        """
    ).fetchall()
    audits = db.execute("SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT 25").fetchall()
    return render_template("admin.html", stats=stats_for(g.user), users=users, providers=providers, audits=audits)


@bp.post("/admin/users/<int:user_id>/verify")
@owner_required
def verify_user(user_id):
    get_db().execute("UPDATE users SET verified=1, updated_at=? WHERE id=?", (now_iso(), user_id))
    audit("verify", "user", str(user_id))
    get_db().commit()
    flash("User verified.", "success")
    return redirect(url_for("main.admin"))


@bp.post("/admin/providers/<int:profile_id>/status")
@owner_required
def provider_verification_status(profile_id):
    status = request.form.get("verification_status", "pending")
    if status not in VERIFICATION_STATES:
        abort(400)
    get_db().execute(
        "UPDATE provider_profiles SET verification_status=?, updated_at=? WHERE id=?",
        (status, now_iso(), profile_id),
    )
    audit("provider_verification", "provider_profile", f"{profile_id}:{status}")
    get_db().commit()
    flash("Provider verification status updated.", "success")
    return redirect(url_for("main.admin"))


def api_user():
    auth = request.headers.get("Authorization", "")
    token = auth.removeprefix("Bearer ").strip()
    if not token:
        return None
    token_digest = hash_token(token)
    user = get_db().execute(
        """
        SELECT u.*, t.id AS token_id FROM api_tokens t
        JOIN users u ON u.id=t.user_id
        WHERE t.token_hash=? AND t.token_type='access' AND t.revoked_at IS NULL AND u.active=1
        """,
        (token_digest,),
    ).fetchone()
    if user:
        return user
    legacy = get_db().execute(
        """
        SELECT u.*, t.id AS token_id FROM api_tokens t
        JOIN users u ON u.id=t.user_id
        WHERE t.token=? AND t.token_type='access' AND t.revoked_at IS NULL AND u.active=1
        """,
        (token,),
    ).fetchone()
    if legacy:
        get_db().execute("UPDATE api_tokens SET token_hash=? WHERE id=? AND token_hash IS NULL", (token_digest, legacy["token_id"]))
        get_db().commit()
    return legacy


def require_api_user():
    user = api_user()
    if not user:
        return None, (jsonify({"error": "Unauthorized"}), 401)
    if user["role"] == "admin" and not is_owner(user):
        return None, (jsonify({"error": {"code": 403, "message": "Only the ZENDOC owner may access Admin operations."}}), 403)
    return user, None


@bp.get("/api/v1/health")
def api_health():
    return jsonify({"status": "ok", "service": "zendoc", "time": now_iso()})


@bp.post("/api/v1/auth/register")
def api_register():
    data = request.get_json(silent=True) or {}
    validation_error = require_json_fields(data, "name", "email", "password", "role")
    if validation_error:
        return validation_error
    role = normalize_role(data.get("role", "patient"))
    if role == "admin":
        return jsonify({"error": "Admin registration is disabled"}), 403
    try:
        email = validate_email(data.get("email", ""))
    except ValueError as error:
        return jsonify({"error": {"code": 400, "message": str(error)}}), 400
    if email_exists(email):
        return jsonify({"error": {"code": 409, "message": ACCOUNT_EXISTS_MESSAGE}}), 409
    if len(data.get("password", "")) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400
    try:
        now = now_iso()
        get_db().execute(
            """
            INSERT INTO users (name,email,email_normalized,password_hash,role,phone,age,city,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                data.get("name", "").strip(),
                email,
                email,
                generate_password_hash(data.get("password")),
                role,
                data.get("phone"),
                data.get("age"),
                data.get("city"),
                now,
                now,
            ),
        )
        get_db().commit()
        return jsonify({"status": "created"}), 201
    except Exception as error:
        if not is_integrity_error(error):
            raise
        get_db().rollback()
        return jsonify({"error": {"code": 409, "message": ACCOUNT_EXISTS_MESSAGE}}), 409


@bp.post("/api/v1/auth/login")
def api_login():
    data = request.get_json(silent=True) or {}
    validation_error = require_json_fields(data, "email", "password", "role")
    if validation_error:
        return validation_error
    try:
        email = validate_email(data.get("email", ""))
    except ValueError:
        email = ""
    requested_role = str(data.get("role", "patient") or "patient").strip().lower()
    user = user_by_normalized_email(email, role=requested_role) if email else None
    if user and user["role"] == "admin" and not is_owner(user):
        user = None
    if not user or not check_password_hash(user["password_hash"], data.get("password", "")):
        return jsonify({"error": INVALID_CREDENTIALS_MESSAGE}), 401
    token = new_token()
    get_db().execute(
        "INSERT INTO api_tokens (user_id,token_hash,token_type,created_at) VALUES (?,?,'access',?)",
        (user["id"], hash_token(token), now_iso()),
    )
    get_db().commit()
    return jsonify({"token": token, "user": {"id": user["id"], "name": user["name"], "role": user["role"]}})


@bp.post("/api/v1/auth/logout")
def api_logout():
    user, error = require_api_user()
    if error:
        return error
    auth = request.headers.get("Authorization", "")
    token = auth.removeprefix("Bearer ").strip()
    get_db().execute(
        "UPDATE api_tokens SET revoked_at=? WHERE token_hash=? AND user_id=?",
        (now_iso(), hash_token(token), user["id"]),
    )
    get_db().commit()
    return jsonify({"status": "revoked"})


@bp.post("/api/v1/auth/forgot-password")
def api_forgot_password():
    if current_app.config.get("PASSWORD_RECOVERY_MODE") != "local_demo":
        return jsonify({
            "status": "integration_required",
            "message": "Password recovery delivery is not integrated.",
        }), 503
    data = request.get_json(silent=True) or {}
    try:
        email = validate_email(data.get("email", ""))
    except ValueError:
        return jsonify({"error": "Email is required"}), 400
    user = user_by_normalized_email(email)
    if user:
        token = new_token()
        get_db().execute(
            "INSERT INTO api_tokens (user_id, token_hash, token_type, expires_at, created_at) VALUES (?, ?, 'password_reset', ?, ?)",
            (user["id"], hash_token(token), future_iso(30), now_iso()),
        )
        get_db().commit()
        return jsonify({"status": "local_demo_token_generated", "reset_token": token, "message": "Local beta token generated; email delivery is not integrated."})
    return jsonify({"status": "local_demo_token_generated", "message": "If the account exists, the local beta recovery request was processed."})


@bp.post("/api/v1/auth/reset-password")
def api_reset_password():
    data = request.get_json(silent=True) or {}
    token = data.get("reset_token", "").strip()
    password = data.get("password", "").strip()
    if not token or not password:
        return jsonify({"error": "reset_token and password are required"}), 400
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400
    token_digest = hash_token(token)
    tok_row = get_db().execute(
        """
        SELECT * FROM api_tokens
        WHERE token_hash=? AND token_type='password_reset' AND revoked_at IS NULL
          AND expires_at IS NOT NULL AND expires_at>?
        """,
        (token_digest, now_iso()),
    ).fetchone()
    if not tok_row:
        return jsonify({"error": "Invalid or expired reset token"}), 400
    user_id = tok_row["user_id"]
    get_db().execute("UPDATE users SET password_hash=?, updated_at=? WHERE id=?", (generate_password_hash(password), now_iso(), user_id))
    get_db().execute("UPDATE api_tokens SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL", (now_iso(), user_id))
    get_db().commit()
    return jsonify({"status": "password_reset_success"})


@bp.get("/api/v1/dashboard")
def api_dashboard():
    user, error = require_api_user()
    if error:
        return error
    return jsonify({"stats": stats_for(user)})


@bp.get("/api/v1/appointments")
def api_appointments():
    user, error = require_api_user()
    if error:
        return error
    rows = get_db().execute(
        "SELECT * FROM appointments WHERE patient_id=? OR provider_id=? OR ?='admin' ORDER BY scheduled_for DESC",
        (user["id"], user["id"], user["role"]),
    ).fetchall()
    return jsonify({"appointments": [dict(row) for row in rows]})


@bp.post("/api/v1/appointments")
def api_create_appointment():
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    if data.get("provider_profile_id"):
        validation_error = require_json_fields(data, "provider_profile_id", "scheduled_for", "reason")
        if validation_error:
            return validation_error
        try:
            book_provider_slot(user, int(data["provider_profile_id"]), data["scheduled_for"], data["reason"])
            get_db().commit()
            return jsonify({"status": "created"}), 201
        except PermissionError as error:
            return jsonify({"error": {"code": 403, "message": str(error)}}), 403
        except ValueError as error:
            return jsonify({"error": {"code": 400, "message": str(error)}}), 400
    validation_error = require_json_fields(data, "provider_name", "scheduled_for", "reason")
    if validation_error:
        return validation_error
    get_db().execute(
        """
        INSERT INTO appointments (patient_id,provider_name,scheduled_for,reason,status,created_at,updated_at)
        VALUES (?,?,?,?, 'requested', ?, ?)
        """,
        (user["id"], data.get("provider_name", "Provider"), data.get("scheduled_for"), data.get("reason", ""), now_iso(), now_iso()),
    )
    get_db().commit()
    return jsonify({"status": "created"}), 201


@bp.get("/api/v1/healthcare/search")
def api_healthcare_search():
    user, error = require_api_user()
    if error:
        return error
    query = normalize_query(
        request.args.get("category"),
        request.args.get("specialty"),
        request.args.get("location"),
        request.args.get("latitude"),
        request.args.get("longitude"),
        request.args.get("radius_km", 10),
    )
    return jsonify(HealthcareFinder().search(query))


@bp.get("/api/v1/providers")
def api_providers():
    user, error = require_api_user()
    if error:
        return error
    return jsonify(HealthcareFinder().search({"category": request.args.get("category", "doctor"), "specialty": request.args.get("specialty"), "location": request.args.get("location")}))


@bp.get("/api/v1/providers/<int:profile_id>/slots")
def api_provider_slots(profile_id):
    user, error = require_api_user()
    if error:
        return error
    date_text = request.args.get("date", "")
    return jsonify({"provider_profile_id": profile_id, "date": date_text, "slots": available_slots(profile_id, date_text)})


@bp.post("/api/v1/provider/profile")
def api_provider_profile():
    user, error = require_api_user()
    if error:
        return error
    if user["role"] not in PROVIDER_ROLES:
        return jsonify({"error": {"code": 403, "message": "Only provider roles can manage provider profiles"}}), 403
    data = request.get_json(silent=True) or {}
    try:
        upsert_provider_profile(user, data)
        get_db().commit()
        return jsonify({"status": "saved", "verification_status": "pending"})
    except (ValueError, PermissionError) as error:
        return jsonify({"error": {"code": 400, "message": str(error)}}), 400


@bp.post("/api/v1/provider/schedules")
def api_provider_schedule():
    user, error = require_api_user()
    if error:
        return error
    if user["role"] not in PROVIDER_ROLES:
        return jsonify({"error": {"code": 403, "message": "Only provider roles can manage schedules"}}), 403
    data = request.get_json(silent=True) or {}
    try:
        create_schedule(user, data)
        get_db().commit()
        return jsonify({"status": "created"}), 201
    except (ValueError, PermissionError) as error:
        return jsonify({"error": {"code": 400, "message": str(error)}}), 400


@bp.post("/api/v1/ai/doctor")
def api_ai_doctor():
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    result = doctor_prediction(data.get("symptoms", ""))
    log_ai_interaction(user["id"], "doctor", data.get("symptoms", ""), result)
    get_db().commit()
    return jsonify({**result, "model_version": MODEL_VERSION})


@bp.post("/api/v1/ai/assistant")
def api_ai_assistant():
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    return jsonify({"answer": assistant_answer(data.get("message", ""))})


@bp.post("/api/v1/ai/mental-health")
def api_ai_mental_health():
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    return jsonify(mental_health_support(data.get("age_group", "adult"), data.get("context", ""), data.get("stress_level", 0)))


@bp.post("/api/v1/ai/message")
def api_ai_message():
    user, error = require_api_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"error": {"code": 400, "message": "Message is required"}}), 400
    conversation = get_or_create_conversation(user["id"], data.get("conversation_id"), title=message[:60])
    result, latency_ms = ZendocIntelligence().respond(message, user=user, conversation=conversation)
    get_db().execute(
        "UPDATE ai_conversations SET last_intent=?, updated_at=? WHERE id=? AND user_id=?",
        (result.intent, now_iso(), conversation["id"], user["id"]),
    )
    log_ai_interaction(user["id"], "zendoc_ai", message, result, latency_ms, conversation["id"])
    get_db().commit()
    return jsonify(result.to_dict())
