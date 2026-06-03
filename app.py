import os
import re
import secrets
import sqlite3
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

from flask import (
    Flask,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename


BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
UPLOAD_DIR = BASE_DIR / "uploads"
DATABASE = INSTANCE_DIR / "zendoc.db"

ROLES = {"patient", "doctor", "hospital", "pharmacy", "government", "admin"}
PUBLIC_ROLES = ROLES - {"admin"}
ALLOWED_UPLOAD_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "txt", "doc", "docx"}
OWNER_NAME = os.environ.get("ZENDOC_OWNER_NAME", "KAPILDEB BISWAS")
OWNER_EMAIL = os.environ.get("ZENDOC_OWNER_EMAIL", "bhimchandrabiswas267@gmail.com")
OWNER_PASSWORD = os.environ.get("ZENDOC_OWNER_PASSWORD", "Kapil@2007")


app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("ZENDOC_SECRET_KEY", "dev-change-this-zendoc-secret"),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    UPLOAD_FOLDER=str(UPLOAD_DIR),
    MAX_CONTENT_LENGTH=10 * 1024 * 1024,
)


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    INSTANCE_DIR.mkdir(exist_ok=True)
    UPLOAD_DIR.mkdir(exist_ok=True)
    db = sqlite3.connect(DATABASE)
    db.executescript(
        """
        PRAGMA foreign_keys = ON;

        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('patient','doctor','hospital','pharmacy','government','admin')),
            phone TEXT,
            age INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);

        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            provider_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            provider_name TEXT,
            scheduled_for TEXT NOT NULL,
            reason TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'requested',
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_appointments_patient ON appointments(patient_id);
        CREATE INDEX IF NOT EXISTS idx_appointments_provider ON appointments(provider_id);
        CREATE INDEX IF NOT EXISTS idx_appointments_status ON appointments(status);

        CREATE TABLE IF NOT EXISTS medical_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            uploaded_by INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            original_filename TEXT NOT NULL,
            stored_filename TEXT NOT NULL UNIQUE,
            mime_type TEXT,
            file_size INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_records_owner ON medical_records(owner_id);

        CREATE TABLE IF NOT EXISTS health_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            metric_type TEXT NOT NULL,
            metric_value TEXT NOT NULL,
            unit TEXT,
            recorded_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_metrics_user ON health_metrics(user_id);

        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            is_read INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, is_read);

        CREATE TABLE IF NOT EXISTS ai_interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            feature TEXT NOT NULL,
            input_text TEXT NOT NULL,
            output_text TEXT NOT NULL,
            risk_level TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_ai_user ON ai_interactions(user_id);

        CREATE TABLE IF NOT EXISTS api_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        );
        """
    )
    owner = db.execute("SELECT id FROM users WHERE email = ?", (OWNER_EMAIL,)).fetchone()
    if owner is None:
        db.execute(
            """
            INSERT INTO users (name, email, password_hash, role, created_at, updated_at)
            VALUES (?, ?, ?, 'admin', ?, ?)
            """,
            (OWNER_NAME, OWNER_EMAIL, generate_password_hash(OWNER_PASSWORD), now_iso(), now_iso()),
        )
    else:
        db.execute(
            """
            UPDATE users
            SET name = ?, password_hash = ?, role = 'admin', updated_at = ?
            WHERE email = ?
            """,
            (OWNER_NAME, generate_password_hash(OWNER_PASSWORD), now_iso(), OWNER_EMAIL),
        )
    db.commit()
    db.close()


def normalize_role(role):
    role = (role or "").lower()
    if role not in ROLES:
        abort(404)
    return role


def display_role(role):
    return role.capitalize()


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


@app.before_request
def load_current_user():
    g.user = current_user()
    if request.method == "POST" and not request.path.startswith("/api/"):
        sent_token = request.form.get("csrf_token")
        if not sent_token or sent_token != session.get("csrf_token"):
            abort(400, "Invalid form token")


@app.context_processor
def inject_globals():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return {
        "csrf_token": session["csrf_token"],
        "current_user": g.get("user"),
        "roles": sorted(PUBLIC_ROLES),
    }


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login", user="patient"))
        return view(*args, **kwargs)

    return wrapped


def role_required(*allowed_roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if g.user is None:
                return redirect(url_for("login", user="patient"))
            if g.user["role"] not in allowed_roles and g.user["role"] != "admin":
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_UPLOAD_EXTENSIONS


def create_notification(user_id, title, message):
    get_db().execute(
        "INSERT INTO notifications (user_id, title, message, created_at) VALUES (?, ?, ?, ?)",
        (user_id, title, message, now_iso()),
    )


def dashboard_stats(user):
    db = get_db()
    if user["role"] == "admin":
        return {
            "users": db.execute("SELECT COUNT(*) AS count FROM users").fetchone()["count"],
            "appointments": db.execute("SELECT COUNT(*) AS count FROM appointments").fetchone()["count"],
            "records": db.execute("SELECT COUNT(*) AS count FROM medical_records").fetchone()["count"],
            "ai_interactions": db.execute("SELECT COUNT(*) AS count FROM ai_interactions").fetchone()["count"],
        }
    return {
        "appointments": db.execute(
            "SELECT COUNT(*) AS count FROM appointments WHERE patient_id = ? OR provider_id = ?",
            (user["id"], user["id"]),
        ).fetchone()["count"],
        "records": db.execute(
            "SELECT COUNT(*) AS count FROM medical_records WHERE owner_id = ?",
            (user["id"],),
        ).fetchone()["count"],
        "notifications": db.execute(
            "SELECT COUNT(*) AS count FROM notifications WHERE user_id = ? AND is_read = 0",
            (user["id"],),
        ).fetchone()["count"],
        "ai_interactions": db.execute(
            "SELECT COUNT(*) AS count FROM ai_interactions WHERE user_id = ?",
            (user["id"],),
        ).fetchone()["count"],
    }


RISK_LEVELS = {"low": 1, "medium": 2, "high": 3}


CONDITION_RULES = [
    {
        "name": "cardiac or respiratory emergency pattern",
        "risk": "high",
        "keywords": {
            "chest pain": 5,
            "shortness of breath": 5,
            "breathless": 4,
            "left arm pain": 4,
            "sweating": 3,
            "fainting": 5,
            "blue lips": 5,
        },
        "advice": "Seek urgent medical care now, especially if symptoms are severe, sudden, or worsening.",
    },
    {
        "name": "stroke warning pattern",
        "risk": "high",
        "keywords": {
            "face droop": 5,
            "slurred speech": 5,
            "weakness one side": 5,
            "confusion": 4,
            "sudden severe headache": 4,
            "vision loss": 4,
        },
        "advice": "Treat stroke warning signs as an emergency and call local emergency services immediately.",
    },
    {
        "name": "respiratory infection pattern",
        "risk": "medium",
        "keywords": {
            "fever": 3,
            "cough": 3,
            "sore throat": 2,
            "runny nose": 1,
            "body ache": 2,
            "fatigue": 1,
            "chills": 2,
        },
        "advice": "Rest, hydrate, monitor temperature, and book a doctor visit if fever is high or lasts more than 3 days.",
    },
    {
        "name": "digestive illness pattern",
        "risk": "medium",
        "keywords": {
            "vomiting": 3,
            "diarrhea": 3,
            "stomach pain": 2,
            "abdominal pain": 3,
            "dehydration": 4,
            "blood in stool": 5,
        },
        "advice": "Use oral fluids if tolerated and seek care quickly for blood, dehydration, severe pain, or repeated vomiting.",
    },
    {
        "name": "migraine or neurological discomfort pattern",
        "risk": "medium",
        "keywords": {
            "headache": 3,
            "nausea": 2,
            "light sensitivity": 3,
            "dizziness": 2,
            "blurred vision": 3,
        },
        "advice": "Rest in a quiet place, hydrate, and consult a clinician if headache is sudden, severe, repeated, or with weakness.",
    },
    {
        "name": "allergy or skin irritation pattern",
        "risk": "low",
        "keywords": {
            "rash": 3,
            "itch": 2,
            "swelling": 3,
            "hives": 3,
            "redness": 1,
        },
        "advice": "Avoid suspected triggers and seek urgent care if swelling affects lips, throat, breathing, or dizziness appears.",
    },
    {
        "name": "metabolic wellness pattern",
        "risk": "medium",
        "keywords": {
            "fatigue": 2,
            "thirst": 3,
            "frequent urination": 4,
            "weight loss": 3,
            "blurred vision": 2,
        },
        "advice": "Consider checking glucose and scheduling a clinician review, especially if symptoms persist.",
    },
]


def normalized_text(value):
    return re.sub(r"\s+", " ", (value or "").lower()).strip()


def score_rule(text, rule):
    score = 0
    matches = []
    for keyword, weight in rule["keywords"].items():
        if keyword in text:
            score += weight
            matches.append(keyword)
    return score, matches


def risk_from_matches(best_rule, score):
    if best_rule is None or score == 0:
        return "low"
    if best_rule["risk"] == "high" and score >= 5:
        return "high"
    if score >= 6:
        return "medium"
    return best_rule["risk"] if score >= 3 else "low"


def ai_doctor_prediction(symptoms):
    text = normalized_text(symptoms)
    if not text:
        return "Please describe symptoms, duration, age, and severity so ZENDOC AI can triage the case.", "low"

    scored = []
    for rule in CONDITION_RULES:
        score, matches = score_rule(text, rule)
        if score:
            scored.append((score, rule, matches))
    scored.sort(key=lambda item: (item[0], RISK_LEVELS[item[1]["risk"]]), reverse=True)

    if not scored:
        return (
            "ZENDOC AI could not find a strong symptom pattern. Add details such as duration, fever value, pain location, "
            "age, medicine history, and whether symptoms are getting worse. This is not a diagnosis; consult a qualified clinician.",
            "low",
        )

    best_score, best_rule, best_matches = scored[0]
    risk = risk_from_matches(best_rule, best_score)
    confidence = min(95, 45 + best_score * 6)
    alternatives = [item[1]["name"] for item in scored[1:3]]
    alt_text = ", ".join(alternatives) if alternatives else "No close secondary pattern found"
    matched_text = ", ".join(best_matches)

    response = (
        f"ML-style triage result: {best_rule['name']}.\n"
        f"Estimated confidence: {confidence}%.\n"
        f"Matched signals: {matched_text}.\n"
        f"Possible alternatives: {alt_text}.\n"
        f"Care guidance: {best_rule['advice']}\n"
        "Safety note: ZENDOC AI supports triage and preparation only. It does not replace a doctor or emergency care."
    )
    return response, risk


def smart_assistant_response(message):
    text = normalized_text(message)
    intents = [
        (
            ("appointment", "book", "schedule", "doctor"),
            "To book care, open Appointments, enter the provider email or clinic name, choose date/time, and write the reason. "
            "Your dashboard will track requested, confirmed, completed, and cancelled states.",
        ),
        (
            ("report", "record", "upload", "medical file", "prescription"),
            "Use Medical Records to upload reports. ZENDOC accepts PDF, images, TXT, DOC, and DOCX files and stores them under your account.",
        ),
        (
            ("password", "login", "account", "admin"),
            "Use the correct role login page for your account. Admin users should use Admin Login; normal users should register first.",
        ),
        (
            ("emergency", "urgent", "chest pain", "stroke", "breathing"),
            "If symptoms are severe, sudden, or life-threatening, contact local emergency services immediately before using the app.",
        ),
        (
            ("mental", "stress", "anxiety", "depression", "sleep"),
            "Use Mental Health AI with an honest stress score from 0 to 10. For self-harm thoughts or immediate danger, contact emergency support now.",
        ),
        (
            ("owner", "founder", "kapildeb", "zendoc"),
            f"{OWNER_NAME} is configured as the ZENDOC owner/admin in this local application.",
        ),
    ]
    for keywords, answer in intents:
        if any(keyword in text for keyword in keywords):
            return answer
    return (
        "ZENDOC Assistant can help with appointments, records, login roles, emergency direction, mental health workflow, "
        "and how to use the AI Doctor. Ask one focused question for the best answer."
    )


def mental_health_support(age_group, context, stress_level):
    try:
        stress = int(stress_level or 0)
    except (TypeError, ValueError):
        stress = 0
    stress = max(0, min(stress, 10))
    if stress >= 8:
        risk = "high"
        advice = "Your stress score is high. Consider contacting a trusted person or licensed professional today."
    elif stress >= 5:
        risk = "medium"
        advice = "Your stress score is moderate. Try a short break, hydration, breathing practice, and schedule support if it persists."
    else:
        risk = "low"
        advice = "Your stress score is low. Keep monitoring mood, sleep, and routine."
    return f"{age_group.title()} support: {advice} Context noted: {context or 'general wellbeing'}.", risk


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/register/<user>", methods=["GET", "POST"])
def register(user):
    role = normalize_role(user)
    if role == "admin":
        abort(403)
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        age = request.form.get("age") or None
        phone = request.form.get("phone", "").strip() or None
        if len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
            return render_template("register.html", user=role, display_user=display_role(role))
        try:
            get_db().execute(
                """
                INSERT INTO users (name, email, password_hash, role, phone, age, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (name, email, generate_password_hash(password), role, phone, age, now_iso(), now_iso()),
            )
            get_db().commit()
            flash("Registration successful. Please log in.", "success")
            return redirect(url_for("login", user=role))
        except sqlite3.IntegrityError:
            flash("An account with this email already exists.", "error")
    return render_template("register.html", user=role, display_user=display_role(role))


@app.route("/login/<user>", methods=["GET", "POST"])
def login(user):
    role = normalize_role(user)
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        db_user = get_db().execute(
            "SELECT * FROM users WHERE email = ? AND role = ?",
            (email, role),
        ).fetchone()
        if db_user and check_password_hash(db_user["password_hash"], password):
            session.clear()
            session["user_id"] = db_user["id"]
            session["csrf_token"] = secrets.token_urlsafe(32)
            flash("Welcome back.", "success")
            return redirect(url_for("dashboard", user=role))
        flash("Invalid login details.", "error")
    return render_template("login.html", user=role, display_user=display_role(role))


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("home"))


@app.route("/dashboard/<user>")
@login_required
def dashboard(user):
    role = normalize_role(user)
    if g.user["role"] != role and g.user["role"] != "admin":
        abort(403)
    stats = dashboard_stats(g.user)
    appointments = get_db().execute(
        """
        SELECT a.*, p.name AS patient_name, COALESCE(pr.name, a.provider_name) AS provider_display
        FROM appointments a
        JOIN users p ON p.id = a.patient_id
        LEFT JOIN users pr ON pr.id = a.provider_id
        WHERE a.patient_id = ? OR a.provider_id = ? OR ? = 'admin'
        ORDER BY a.created_at DESC LIMIT 5
        """,
        (g.user["id"], g.user["id"], g.user["role"]),
    ).fetchall()
    return render_template(
        "dashboard.html",
        name=g.user["name"],
        user=display_role(role),
        stats=stats,
        appointments=appointments,
    )


@app.route("/appointments", methods=["GET", "POST"])
@login_required
def appointments():
    db = get_db()
    if request.method == "POST":
        patient_id = g.user["id"]
        provider_email = request.form.get("provider_email", "").strip().lower()
        provider = db.execute("SELECT id, name FROM users WHERE email = ?", (provider_email,)).fetchone()
        provider_id = provider["id"] if provider else None
        provider_name = provider["name"] if provider else request.form.get("provider_name", "Provider").strip()
        db.execute(
            """
            INSERT INTO appointments (patient_id, provider_id, provider_name, scheduled_for, reason, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'requested', ?, ?)
            """,
            (
                patient_id,
                provider_id,
                provider_name,
                request.form.get("scheduled_for"),
                request.form.get("reason", "").strip(),
                now_iso(),
                now_iso(),
            ),
        )
        create_notification(patient_id, "Appointment requested", "Your appointment request has been saved.")
        db.commit()
        flash("Appointment saved.", "success")
        return redirect(url_for("appointments"))
    rows = db.execute(
        """
        SELECT a.*, p.name AS patient_name, COALESCE(pr.name, a.provider_name) AS provider_display
        FROM appointments a
        JOIN users p ON p.id = a.patient_id
        LEFT JOIN users pr ON pr.id = a.provider_id
        WHERE a.patient_id = ? OR a.provider_id = ? OR ? = 'admin'
        ORDER BY a.scheduled_for DESC
        """,
        (g.user["id"], g.user["id"], g.user["role"]),
    ).fetchall()
    return render_template("appointments.html", appointments=rows)


@app.post("/appointments/<int:appointment_id>/status")
@role_required("doctor", "hospital", "admin")
def update_appointment_status(appointment_id):
    status = request.form.get("status", "requested")
    if status not in {"requested", "confirmed", "completed", "cancelled"}:
        abort(400)
    get_db().execute(
        "UPDATE appointments SET status = ?, updated_at = ? WHERE id = ?",
        (status, now_iso(), appointment_id),
    )
    get_db().commit()
    flash("Appointment status updated.", "success")
    return redirect(url_for("appointments"))


@app.route("/records", methods=["GET", "POST"])
@login_required
def records():
    db = get_db()
    if request.method == "POST":
        upload = request.files.get("record_file")
        if not upload or upload.filename == "":
            flash("Choose a file to upload.", "error")
            return redirect(url_for("records"))
        if not allowed_file(upload.filename):
            flash("Unsupported file type.", "error")
            return redirect(url_for("records"))
        original = secure_filename(upload.filename)
        stored = f"{secrets.token_hex(16)}-{original}"
        destination = UPLOAD_DIR / stored
        upload.save(destination)
        db.execute(
            """
            INSERT INTO medical_records
            (owner_id, uploaded_by, title, category, original_filename, stored_filename, mime_type, file_size, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                g.user["id"],
                g.user["id"],
                request.form.get("title", original).strip(),
                request.form.get("category", "General").strip(),
                original,
                stored,
                upload.mimetype,
                destination.stat().st_size,
                now_iso(),
            ),
        )
        create_notification(g.user["id"], "Record uploaded", "A medical record was added to your account.")
        db.commit()
        flash("Medical record uploaded.", "success")
        return redirect(url_for("records"))
    rows = db.execute(
        "SELECT * FROM medical_records WHERE owner_id = ? OR ? = 'admin' ORDER BY created_at DESC",
        (g.user["id"], g.user["role"]),
    ).fetchall()
    return render_template("records.html", records=rows)


@app.route("/records/<int:record_id>/download")
@login_required
def download_record(record_id):
    record = get_db().execute("SELECT * FROM medical_records WHERE id = ?", (record_id,)).fetchone()
    if record is None:
        abort(404)
    if g.user["role"] != "admin" and record["owner_id"] != g.user["id"]:
        abort(403)
    return send_from_directory(UPLOAD_DIR, record["stored_filename"], as_attachment=True, download_name=record["original_filename"])


@app.route("/health", methods=["GET", "POST"])
@login_required
def health_monitoring():
    db = get_db()
    if request.method == "POST":
        db.execute(
            "INSERT INTO health_metrics (user_id, metric_type, metric_value, unit, recorded_at) VALUES (?, ?, ?, ?, ?)",
            (
                g.user["id"],
                request.form.get("metric_type", "").strip(),
                request.form.get("metric_value", "").strip(),
                request.form.get("unit", "").strip(),
                now_iso(),
            ),
        )
        db.commit()
        flash("Health metric saved.", "success")
        return redirect(url_for("health_monitoring"))
    rows = db.execute(
        "SELECT * FROM health_metrics WHERE user_id = ? ORDER BY recorded_at DESC LIMIT 30",
        (g.user["id"],),
    ).fetchall()
    return render_template("health.html", metrics=rows)


@app.route("/ai", methods=["GET", "POST"])
@login_required
def ai_center():
    result = None
    if request.method == "POST":
        feature = request.form.get("feature")
        if feature == "doctor":
            result_text, risk = ai_doctor_prediction(request.form.get("symptoms", ""))
            input_text = request.form.get("symptoms", "")
        elif feature == "assistant":
            result_text = smart_assistant_response(request.form.get("message", ""))
            risk = "low"
            input_text = request.form.get("message", "")
        elif feature == "mental_health":
            result_text, risk = mental_health_support(
                request.form.get("age_group", "adult"),
                request.form.get("context", ""),
                request.form.get("stress_level", 0),
            )
            input_text = f"{request.form.get('age_group')} | stress={request.form.get('stress_level')} | {request.form.get('context')}"
        else:
            abort(400)
        get_db().execute(
            "INSERT INTO ai_interactions (user_id, feature, input_text, output_text, risk_level, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (g.user["id"], feature, input_text, result_text, risk, now_iso()),
        )
        get_db().commit()
        result = {"text": result_text, "risk": risk}
    history = get_db().execute(
        "SELECT * FROM ai_interactions WHERE user_id = ? ORDER BY created_at DESC LIMIT 10",
        (g.user["id"],),
    ).fetchall()
    return render_template("ai.html", result=result, history=history)


@app.route("/admin")
@role_required("admin")
def admin():
    return render_template("admin.html", stats=dashboard_stats(g.user), owner_name=OWNER_NAME, owner_email=OWNER_EMAIL)


def api_user_from_token():
    header = request.headers.get("Authorization", "")
    token = header.removeprefix("Bearer ").strip()
    if not token:
        return None
    return get_db().execute(
        """
        SELECT users.* FROM api_tokens
        JOIN users ON users.id = api_tokens.user_id
        WHERE api_tokens.token = ?
        """,
        (token,),
    ).fetchone()


def api_login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        g.api_user = api_user_from_token()
        if g.api_user is None:
            return jsonify({"error": "Unauthorized"}), 401
        return view(*args, **kwargs)

    return wrapped


@app.get("/api/v1/health")
def api_health():
    return jsonify({"status": "ok", "service": "zendoc", "time": now_iso()})


@app.post("/api/v1/auth/register")
def api_register():
    payload = request.get_json(silent=True) or {}
    role = normalize_role(payload.get("role", "patient"))
    if role == "admin":
        return jsonify({"error": "Admin registration is disabled"}), 403
    password = payload.get("password", "")
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400
    try:
        get_db().execute(
            """
            INSERT INTO users (name, email, password_hash, role, phone, age, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.get("name", "").strip(),
                payload.get("email", "").strip().lower(),
                generate_password_hash(password),
                role,
                payload.get("phone"),
                payload.get("age"),
                now_iso(),
                now_iso(),
            ),
        )
        get_db().commit()
        return jsonify({"status": "created"}), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": "Email already exists"}), 409


@app.post("/api/v1/auth/login")
def api_login():
    payload = request.get_json(silent=True) or {}
    user = get_db().execute(
        "SELECT * FROM users WHERE email = ? AND role = ?",
        (payload.get("email", "").strip().lower(), payload.get("role", "patient")),
    ).fetchone()
    if not user or not check_password_hash(user["password_hash"], payload.get("password", "")):
        return jsonify({"error": "Invalid credentials"}), 401
    token = secrets.token_urlsafe(40)
    get_db().execute(
        "INSERT INTO api_tokens (user_id, token, created_at) VALUES (?, ?, ?)",
        (user["id"], token, now_iso()),
    )
    get_db().commit()
    return jsonify({"token": token, "user": {"id": user["id"], "name": user["name"], "role": user["role"]}})


@app.get("/api/v1/dashboard")
@api_login_required
def api_dashboard():
    return jsonify({"stats": dashboard_stats(g.api_user)})


@app.post("/api/v1/ai/doctor")
@api_login_required
def api_ai_doctor():
    payload = request.get_json(silent=True) or {}
    output, risk = ai_doctor_prediction(payload.get("symptoms", ""))
    return jsonify({"prediction": output, "risk_level": risk, "model_status": "rules_engine_ready_for_ml_provider"})


@app.post("/api/v1/ai/assistant")
@api_login_required
def api_ai_assistant():
    payload = request.get_json(silent=True) or {}
    return jsonify({"answer": smart_assistant_response(payload.get("message", ""))})


@app.post("/api/v1/ai/mental-health")
@api_login_required
def api_ai_mental_health():
    payload = request.get_json(silent=True) or {}
    output, risk = mental_health_support(
        payload.get("age_group", "adult"),
        payload.get("context", ""),
        payload.get("stress_level", 0),
    )
    return jsonify({"support": output, "risk_level": risk})


init_db()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
