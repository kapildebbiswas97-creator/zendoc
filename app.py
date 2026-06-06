import os
import re
import secrets
import sqlite3
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from statistics import mean

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
ALLOWED_UPLOAD_MIMES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "text/plain",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
OWNER_NAME = os.environ.get("ZENDOC_OWNER_NAME", "KAPILDEB BISWAS")
OWNER_EMAIL = os.environ.get("ZENDOC_OWNER_EMAIL", "bhimchandrabiswas267@gmail.com")
OWNER_PASSWORD = os.environ.get("ZENDOC_OWNER_PASSWORD")
PRODUCTION_MODE = os.environ.get("FLASK_ENV") == "production" or os.environ.get("ZENDOC_ENV") == "production"


app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("ZENDOC_SECRET_KEY", "dev-change-this-zendoc-secret"),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=PRODUCTION_MODE,
    UPLOAD_FOLDER=str(UPLOAD_DIR),
    MAX_CONTENT_LENGTH=10 * 1024 * 1024,
)

if PRODUCTION_MODE and app.config["SECRET_KEY"] == "dev-change-this-zendoc-secret":
    raise RuntimeError("Set ZENDOC_SECRET_KEY before running ZENDOC in production.")


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def hash_token(token):
    import hashlib

    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def clean_text(value, max_length=500, required=False):
    text = re.sub(r"\s+", " ", (value or "").strip())
    if required and not text:
        raise ValueError("Required field is missing")
    return text[:max_length]


def clean_email(value):
    email = clean_text(value, 254).lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise ValueError("Enter a valid email address")
    return email


def parse_age(value):
    if value in (None, ""):
        return None
    try:
        age = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Age must be a number") from exc
    if age < 0 or age > 130:
        raise ValueError("Age must be between 0 and 130")
    return age


def bootstrap_owner_password():
    if OWNER_PASSWORD:
        return OWNER_PASSWORD
    password = secrets.token_urlsafe(18)
    INSTANCE_DIR.mkdir(exist_ok=True)
    bootstrap_file = INSTANCE_DIR / "owner_bootstrap.txt"
    if not bootstrap_file.exists():
        bootstrap_file.write_text(
            f"ZENDOC owner bootstrap credential\nEmail: {OWNER_EMAIL}\nPassword: {password}\n"
            "Set ZENDOC_OWNER_PASSWORD and delete this file after first login.\n",
            encoding="utf-8",
        )
    return password


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

        CREATE TABLE IF NOT EXISTS mood_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            mood TEXT NOT NULL,
            stress_level INTEGER NOT NULL,
            context TEXT,
            wellness_score INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_mood_user ON mood_entries(user_id, created_at);

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

        CREATE TABLE IF NOT EXISTS audit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            action TEXT NOT NULL,
            target TEXT,
            ip_address TEXT,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_events(user_id, created_at);
        """
    )
    owner = db.execute("SELECT id FROM users WHERE email = ?", (OWNER_EMAIL,)).fetchone()
    if owner is None:
        owner_password = bootstrap_owner_password()
        db.execute(
            """
            INSERT INTO users (name, email, password_hash, role, created_at, updated_at)
            VALUES (?, ?, ?, 'admin', ?, ?)
            """,
            (OWNER_NAME, OWNER_EMAIL, generate_password_hash(owner_password), now_iso(), now_iso()),
        )
    else:
        if OWNER_PASSWORD:
            db.execute(
                """
                UPDATE users
                SET name = ?, password_hash = ?, role = 'admin', updated_at = ?
                WHERE email = ?
                """,
                (OWNER_NAME, generate_password_hash(OWNER_PASSWORD), now_iso(), OWNER_EMAIL),
            )
        else:
            db.execute(
                """
                UPDATE users
                SET name = ?, role = 'admin', updated_at = ?
                WHERE email = ?
                """,
                (OWNER_NAME, now_iso(), OWNER_EMAIL),
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


@app.after_request
def add_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    if not request.path.startswith("/static/"):
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'self'; img-src 'self' data:; script-src 'self'; base-uri 'self'; frame-ancestors 'none'",
        )
    return response


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


def audit_event(action, target=None, user_id=None):
    get_db().execute(
        "INSERT INTO audit_events (user_id, action, target, ip_address, created_at) VALUES (?, ?, ?, ?, ?)",
        (
            user_id or (g.user["id"] if getattr(g, "user", None) else None),
            clean_text(action, 80),
            clean_text(target, 240) if target else None,
            request.headers.get("X-Forwarded-For", request.remote_addr or "")[:80],
            now_iso(),
        ),
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


def investor_analytics():
    db = get_db()
    total_users = db.execute("SELECT COUNT(*) AS count FROM users").fetchone()["count"]
    active_ai_users = db.execute("SELECT COUNT(DISTINCT user_id) AS count FROM ai_interactions WHERE user_id IS NOT NULL").fetchone()["count"]
    appointments = db.execute("SELECT COUNT(*) AS count FROM appointments").fetchone()["count"]
    completed = db.execute("SELECT COUNT(*) AS count FROM appointments WHERE status = 'completed'").fetchone()["count"]
    high_risk = db.execute("SELECT COUNT(*) AS count FROM ai_interactions WHERE risk_level = 'high'").fetchone()["count"]
    records = db.execute("SELECT COUNT(*) AS count FROM medical_records").fetchone()["count"]
    role_rows = db.execute("SELECT role, COUNT(*) AS count FROM users GROUP BY role ORDER BY count DESC").fetchall()
    feature_rows = db.execute("SELECT feature, COUNT(*) AS count FROM ai_interactions GROUP BY feature ORDER BY count DESC").fetchall()
    engagement = round((active_ai_users / total_users) * 100, 1) if total_users else 0
    conversion = round((completed / appointments) * 100, 1) if appointments else 0
    return {
        "growth_metrics": {
            "registered_users": total_users,
            "role_mix": [{"label": row["role"].title(), "value": row["count"]} for row in role_rows],
            "record_uploads": records,
        },
        "engagement_metrics": {
            "ai_active_users": active_ai_users,
            "ai_engagement_rate": engagement,
            "care_completion_rate": conversion,
            "feature_usage": [{"label": row["feature"].replace("_", " ").title(), "value": row["count"]} for row in feature_rows],
        },
        "patient_insights": {
            "high_risk_ai_events": high_risk,
            "appointments_requested": appointments,
            "completed_appointments": completed,
        },
    }


RISK_LEVELS = {"low": 1, "medium": 2, "high": 3}


CLINICAL_PATTERNS = [
    {
        "label": "possible heart or breathing emergency",
        "risk": "high",
        "signals": {
            "chest pain": 5,
            "pressure in chest": 5,
            "shortness of breath": 5,
            "breathless": 4,
            "left arm pain": 4,
            "sweating": 3,
            "fainting": 5,
            "blue lips": 5,
        },
        "reasoning": "Chest discomfort with breathing difficulty, fainting, sweating, or pain spreading to the arm can be time-sensitive.",
        "next_actions": [
            "Call local emergency services or go to the nearest emergency department now.",
            "Avoid driving yourself if you feel faint, breathless, or weak.",
            "Keep a list of current medicines and allergies ready for the clinician.",
        ],
    },
    {
        "label": "possible stroke warning signs",
        "risk": "high",
        "signals": {
            "face droop": 5,
            "facial droop": 5,
            "slurred speech": 5,
            "weakness one side": 5,
            "one side weakness": 5,
            "confusion": 4,
            "sudden severe headache": 4,
            "vision loss": 4,
        },
        "reasoning": "Sudden speech, face, vision, confusion, or one-sided weakness symptoms need immediate assessment.",
        "next_actions": [
            "Call emergency services immediately and note the time symptoms began.",
            "Do not wait for symptoms to improve on their own.",
            "Do not eat or drink until a clinician advises it is safe.",
        ],
    },
    {
        "label": "respiratory infection or flu-like illness",
        "risk": "medium",
        "signals": {
            "fever": 3,
            "cough": 3,
            "sore throat": 2,
            "runny nose": 1,
            "body ache": 2,
            "fatigue": 1,
            "chills": 2,
        },
        "reasoning": "Fever, cough, sore throat, chills, and body aches often cluster around respiratory infections.",
        "next_actions": [
            "Rest, hydrate, and monitor temperature.",
            "Book a clinician visit if fever is high, lasts more than 3 days, or breathing becomes difficult.",
            "Avoid close contact with vulnerable people until symptoms improve.",
        ],
    },
    {
        "label": "digestive illness or dehydration risk",
        "risk": "medium",
        "signals": {
            "vomiting": 3,
            "diarrhea": 3,
            "stomach pain": 2,
            "abdominal pain": 3,
            "dehydration": 4,
            "blood in stool": 5,
        },
        "reasoning": "Vomiting, diarrhea, abdominal pain, and dehydration symptoms can worsen quickly if fluids cannot be kept down.",
        "next_actions": [
            "Use small frequent sips of oral rehydration fluid if tolerated.",
            "Seek care quickly for blood, severe pain, fainting, dehydration, or repeated vomiting.",
            "Avoid heavy meals until symptoms settle.",
        ],
    },
    {
        "label": "headache or neurological discomfort",
        "risk": "medium",
        "signals": {
            "headache": 3,
            "nausea": 2,
            "light sensitivity": 3,
            "dizziness": 2,
            "blurred vision": 3,
        },
        "reasoning": "Headache with nausea, dizziness, visual changes, or light sensitivity needs context such as onset and severity.",
        "next_actions": [
            "Rest in a quiet place and hydrate.",
            "Seek urgent care if the headache is sudden, severe, after injury, or comes with weakness or confusion.",
            "Track triggers such as sleep, meals, stress, and screen exposure.",
        ],
    },
    {
        "label": "allergy or skin irritation",
        "risk": "low",
        "signals": {
            "rash": 3,
            "itch": 2,
            "swelling": 3,
            "hives": 3,
            "redness": 1,
        },
        "reasoning": "Rash, itching, redness, hives, and localized swelling often point toward irritation or allergy.",
        "next_actions": [
            "Avoid the suspected trigger and photograph the rash if it changes.",
            "Seek urgent care if swelling affects the lips, tongue, throat, breathing, or causes dizziness.",
            "Ask a pharmacist or clinician before using new medicines if you have allergies.",
        ],
    },
    {
        "label": "possible blood sugar or metabolic concern",
        "risk": "medium",
        "signals": {
            "fatigue": 2,
            "thirst": 3,
            "frequent urination": 4,
            "weight loss": 3,
            "blurred vision": 2,
        },
        "reasoning": "Fatigue with increased thirst, frequent urination, weight change, or blurred vision can benefit from glucose review.",
        "next_actions": [
            "Schedule a clinician review if symptoms persist or are new for you.",
            "Consider recording fasting or random glucose if you already have a monitoring plan.",
            "Keep hydration, meals, sleep, and activity consistent while waiting for review.",
        ],
    },
]


def normalized_text(value):
    return re.sub(r"\s+", " ", (value or "").lower()).strip()


def score_pattern(text, pattern):
    score = 0
    signals = []
    for keyword, weight in pattern["signals"].items():
        if keyword in text:
            score += weight
            signals.append(keyword)
    return score, signals


def risk_from_pattern(best_pattern, score):
    if best_pattern is None or score == 0:
        return "low"
    if best_pattern["risk"] == "high" and score >= 5:
        return "high"
    if score >= 6:
        return "medium"
    return best_pattern["risk"] if score >= 3 else "low"


def recent_ai_context(feature):
    context = session.get("ai_context", {})
    return context.get(feature, [])[-3:]


def remember_ai_context(feature, user_input, output_summary):
    context = session.setdefault("ai_context", {})
    turns = context.setdefault(feature, [])
    turns.append({"input": clean_text(user_input, 600), "summary": clean_text(output_summary, 240), "time": now_iso()})
    context[feature] = turns[-6:]
    session["ai_context"] = context


def missing_consultation_details(text):
    questions = []
    if not re.search(r"\b(hour|hours|day|days|week|weeks|since|yesterday|today)\b", text):
        questions.append("How long has this been happening?")
    if not re.search(r"\b(mild|moderate|severe|10/10|[0-9]\s*/\s*10)\b", text):
        questions.append("How severe is it on a 0 to 10 scale?")
    if "fever" in text and not re.search(r"\b(temperature|temp|[0-9]{2,3}(\.[0-9])?)\b", text):
        questions.append("What is the highest temperature you measured?")
    if not re.search(r"\b(age|years old|yo|male|female|pregnant|diabetes|bp|pressure)\b", text):
        questions.append("What is your age and any important medical history?")
    return questions[:3]


def ai_doctor_prediction(symptoms):
    current_text = clean_text(symptoms, 1200)
    prior = [turn["input"] for turn in recent_ai_context("doctor")]
    text = normalized_text(" ".join(prior[-2:] + [current_text]))
    if not text:
        return {
            "text": "Tell me what symptoms you are having, when they started, your age, and how severe they feel. I will help you decide what level of care makes sense.",
            "risk": "low",
            "confidence": 0,
            "banner": None,
            "next_actions": ["Describe the main symptom, duration, severity, and any existing conditions."],
            "questions": ["What symptom is worrying you most right now?"],
            "summary": "Awaiting symptom details",
        }

    scored = []
    for pattern in CLINICAL_PATTERNS:
        score, signals = score_pattern(text, pattern)
        if score:
            scored.append((score, pattern, signals))
    scored.sort(key=lambda item: (item[0], RISK_LEVELS[item[1]["risk"]]), reverse=True)

    if not scored:
        questions = missing_consultation_details(text)
        response = (
            "I do not have enough detail yet to estimate the most likely concern. "
            "The safest next step is to share timing, severity, location, temperature if relevant, medicines, and whether symptoms are improving or worsening."
        )
        return {
            "text": response,
            "risk": "low",
            "confidence": 35,
            "banner": None,
            "next_actions": [
                "Add the missing details so the consultation can be more specific.",
                "If symptoms are severe, sudden, or rapidly worsening, seek urgent medical care.",
            ],
            "questions": questions or ["What changed today that made you seek help?"],
            "summary": "Insufficient symptom detail",
        }

    best_score, best_pattern, _signals = scored[0]
    risk = risk_from_pattern(best_pattern, best_score)
    confidence = min(94, 48 + best_score * 5 + (8 if len(scored) == 1 else 0))
    questions = missing_consultation_details(text)
    urgency = {
        "high": "This needs urgent medical attention.",
        "medium": "This deserves timely clinical review if it persists, worsens, or feels unusual for you.",
        "low": "This currently looks suitable for careful monitoring, unless it worsens or new symptoms appear.",
    }[risk]
    banner = None
    if risk == "high":
        banner = "Urgent warning: please seek emergency care now."
    elif risk == "medium":
        banner = "Care advisory: monitor closely and arrange medical review if symptoms persist or worsen."
    response = (
        f"Thanks for sharing that. {urgency}\n\n"
        f"What I am considering: {best_pattern['label']}.\n"
        f"Why: {best_pattern['reasoning']}\n"
        f"Confidence: {confidence}%.\n\n"
        "This is guidance for triage and preparation, not a diagnosis. A qualified clinician can confirm what is happening."
    )
    return {
        "text": response,
        "risk": risk,
        "confidence": confidence,
        "banner": banner,
        "next_actions": best_pattern["next_actions"],
        "questions": questions,
        "summary": best_pattern["label"],
    }


def smart_assistant_response(message):
    user_message = clean_text(message, 1000)
    text = normalized_text(user_message)
    previous = recent_ai_context("assistant")
    context_note = " I will keep this in mind for the rest of this session." if previous else ""
    response = "I can help with care navigation, records, appointments, medication routines, nutrition, and daily health planning."
    next_actions = ["Tell me the care goal you want help with today."]
    questions = ["Are you asking for appointments, records, medicines, lifestyle, nutrition, or coaching?"]
    risk = "low"

    if any(term in text for term in ("emergency", "urgent", "chest pain", "stroke", "breathing", "faint")):
        risk = "high"
        response = "If this may be urgent, please contact local emergency services first. I can help you organize details for the care team after immediate safety is handled."
        next_actions = ["Call emergency services for severe, sudden, or life-threatening symptoms.", "Write down symptom start time, medicines, allergies, and existing conditions."]
        questions = ["Are you safe right now, and is someone with you?"]
    elif any(term in text for term in ("appointment", "book", "schedule", "doctor", "clinic")):
        response = "I can help you prepare a focused appointment request so the provider understands the priority quickly."
        next_actions = ["Open Appointments.", "Choose a provider or clinic name.", "Add date, main concern, symptom duration, and urgency."]
        questions = ["What specialty or provider type do you need, and how soon do you want to be seen?"]
    elif any(term in text for term in ("report", "record", "upload", "medical file", "prescription", "lab")):
        response = "For records, I can help you organize reports into a useful timeline and turn confusing results into questions for your clinician."
        next_actions = ["Upload the file in Medical Records.", "Use a clear title such as 'CBC report - June 2026'.", "Ask me to summarize what the report is for and what to discuss with your doctor."]
        questions = ["What type of report is it: lab, imaging, prescription, discharge summary, or something else?"]
    elif any(term in text for term in ("medicine", "medication", "tablet", "dose", "reminder", "pill")):
        response = "I can help you build a simple medication routine and reminder plan. I will not change doses, but I can help you stay organized."
        next_actions = ["List medicine name, dose, timing, and prescribing doctor.", "Set morning/evening reminder windows.", "Flag missed doses or side effects for clinician review."]
        questions = ["Which medicine do you want to track, and when are you supposed to take it?"]
    elif any(term in text for term in ("diet", "nutrition", "food", "weight", "protein", "meal")):
        response = "I can support practical nutrition planning based on your goal, routine, and any medical restrictions."
        next_actions = ["Share your goal: energy, weight, diabetes support, digestion, or heart health.", "Log weight and meals consistently.", "Prefer balanced meals with protein, fiber, hydration, and regular timing."]
        questions = ["Do you have diabetes, blood pressure, kidney disease, allergies, or a clinician-advised diet?"]
    elif any(term in text for term in ("lifestyle", "exercise", "sleep", "habit", "coach", "daily")):
        response = "Let us make this manageable. A good health plan should be small enough to repeat on a busy day."
        next_actions = ["Pick one anchor habit: sleep time, 20-minute walk, hydration, or medicine adherence.", "Track it daily for a week.", "Review trends in Health Intelligence."]
        questions = ["Which habit would improve your week the most if it became consistent?"]
    elif any(term in text for term in ("mental", "stress", "anxiety", "burnout", "lonely", "sleep")):
        response = "I can support a calm check-in and a short plan for the next 24 hours. If you feel at risk of harming yourself, contact emergency support immediately."
        next_actions = ["Open Mental Wellness.", "Record mood and stress level.", "Try a two-minute breathing reset and write one honest journal line."]
        questions = ["Is this stress coming mostly from study, work, relationships, health, or loneliness?"]
    elif any(term in text for term in ("owner", "founder", "kapildeb", "zendoc")):
        response = f"{OWNER_NAME} is configured as the ZENDOC owner/admin for this installation."
        next_actions = ["Use the Admin area for platform metrics and operations."]
        questions = []

    return {
        "text": response + context_note,
        "risk": risk,
        "confidence": 82 if text else 45,
        "banner": "Urgent warning: handle immediate safety before using the app." if risk == "high" else None,
        "next_actions": next_actions,
        "questions": questions,
        "summary": "Healthcare copilot response",
    }


def mental_health_support(age_group, context, stress_level, mood="neutral"):
    try:
        stress = int(stress_level or 0)
    except (TypeError, ValueError):
        stress = 0
    stress = max(0, min(stress, 10))
    age_group = clean_text(age_group, 60) or "adult"
    context = clean_text(context, 1000)
    mood = clean_text(mood, 60) or "neutral"
    text = normalized_text(f"{context} {mood}")
    high_risk_terms = ("self harm", "suicide", "kill myself", "end my life", "not want to live")
    pressure_flags = []
    if any(term in text for term in ("exam", "study", "student", "marks", "college", "school")):
        pressure_flags.append("student pressure")
    if any(term in text for term in ("work", "job", "manager", "deadline", "office", "salary")):
        pressure_flags.append("workplace pressure")
    if any(term in text for term in ("lonely", "alone", "isolated", "no friends")):
        pressure_flags.append("loneliness")
    if any(term in text for term in ("panic", "worry", "anxiety", "fear", "overthinking")):
        pressure_flags.append("anxiety indicators")
    if any(term in text for term in ("burnout", "exhausted", "drained", "can't focus", "cannot focus")):
        pressure_flags.append("burnout")

    crisis = any(term in text for term in high_risk_terms)
    if crisis:
        risk = "high"
        wellness_score = max(10, 35 - stress * 2)
        advice = "Your safety matters first. Please contact emergency services or a trusted person immediately and do not stay alone right now."
    elif stress >= 8:
        risk = "high"
        wellness_score = 45 - min(15, stress)
        advice = "Your stress looks high today. You deserve support from a trusted person or licensed professional, ideally today."
    elif stress >= 5:
        risk = "medium"
        wellness_score = 68 - stress
        advice = "Your stress is moderate. A short reset and a clearer plan for the next few hours can help reduce the load."
    else:
        risk = "low"
        wellness_score = 86 - stress
        advice = "Your stress level is in a steadier range. Keep protecting sleep, movement, connection, and routine."
    wellness_score = max(5, min(95, wellness_score))
    focus = ", ".join(pressure_flags) if pressure_flags else "general wellbeing"
    next_actions = [
        "Try 4-6 breathing for two minutes: inhale for 4, exhale for 6.",
        "Write one journal line: 'What I need most today is...'",
        "Choose one small stabilizer: water, food, a walk, a shower, or messaging someone safe.",
    ]
    if risk == "high":
        next_actions.insert(0, "Contact a trusted person or professional support today.")
    response = (
        f"I hear you. For a {age_group}, this check-in points to {focus}.\n"
        f"Wellness score: {wellness_score}/100.\n"
        f"{advice}\n\n"
        "Daily motivation: You do not have to solve the whole week today; start with the next steady step."
    )
    return {
        "text": response,
        "risk": risk,
        "confidence": 84 if context else 58,
        "banner": "Safety priority: reach emergency or crisis support now if you may harm yourself." if crisis else None,
        "next_actions": next_actions,
        "questions": ["What is one pressure you can reduce or share with someone today?"],
        "summary": f"Mental wellness: {focus}",
        "wellness_score": wellness_score,
        "mood": mood,
        "stress": stress,
    }


def metric_key(metric_type):
    value = normalized_text(metric_type)
    if "height" in value:
        return "height"
    if "weight" in value:
        return "weight"
    if "blood pressure" in value or value in {"bp", "pressure"}:
        return "blood_pressure"
    if "glucose" in value or "sugar" in value:
        return "glucose"
    if "heart" in value or "pulse" in value:
        return "heart_rate"
    if "sleep" in value:
        return "sleep"
    if "stress" in value:
        return "stress"
    if "mood" in value:
        return "mood"
    return value[:40] or "general"


def extract_numbers(value):
    return [float(item) for item in re.findall(r"\d+(?:\.\d+)?", value or "")]


def latest_metric_map(metrics):
    latest = {}
    history = {}
    for metric in metrics:
        key = metric_key(metric["metric_type"])
        history.setdefault(key, []).append(metric)
        latest.setdefault(key, metric)
    return latest, history


def metric_value(row):
    return row["metric_value"] if row else ""


def calculate_health_intelligence(metrics, moods=None):
    latest, history = latest_metric_map(metrics)
    insights = []
    recommendations = []
    risk_points = 0
    score = 82
    bmi = None

    weight_values = extract_numbers(metric_value(latest.get("weight")))
    height_values = extract_numbers(metric_value(latest.get("height")))
    if weight_values and height_values:
        weight_kg = weight_values[0]
        height = height_values[0]
        height_m = height / 100 if height > 3 else height
        if height_m > 0:
            bmi = round(weight_kg / (height_m * height_m), 1)
            if bmi < 18.5:
                insights.append(f"BMI is {bmi}, which is below the usual healthy range.")
                recommendations.append("Discuss nutrition, weight goals, and energy levels with a clinician or dietitian.")
                risk_points += 10
            elif bmi >= 30:
                insights.append(f"BMI is {bmi}, which can increase metabolic and heart-health risk.")
                recommendations.append("Prioritize sustainable nutrition, walking, sleep, and clinician-guided weight planning.")
                risk_points += 14
            elif bmi >= 25:
                insights.append(f"BMI is {bmi}, slightly above the usual healthy range.")
                recommendations.append("A small weekly activity and meal consistency plan may improve long-term risk.")
                risk_points += 7
            else:
                insights.append(f"BMI is {bmi}, within the usual healthy range.")

    bp = latest.get("blood_pressure")
    if bp:
        nums = extract_numbers(bp["metric_value"])
        if len(nums) >= 2:
            systolic, diastolic = nums[0], nums[1]
            if systolic >= 140 or diastolic >= 90:
                insights.append("Recent blood pressure is elevated.")
                recommendations.append("Recheck blood pressure when rested and arrange clinician review if readings stay high.")
                risk_points += 14
            elif systolic >= 130 or diastolic >= 80:
                insights.append("Recent blood pressure is borderline high.")
                recommendations.append("Track blood pressure trends, salt intake, sleep, and stress for the next week.")
                risk_points += 7

    glucose = latest.get("glucose")
    if glucose:
        nums = extract_numbers(glucose["metric_value"])
        if nums and nums[0] >= 180:
            insights.append("Recent glucose reading is high.")
            recommendations.append("Follow your diabetes care plan if you have one and seek medical review for repeated high readings.")
            risk_points += 14
        elif nums and nums[0] >= 126:
            insights.append("Recent glucose reading needs follow-up.")
            recommendations.append("Consider fasting/repeat glucose review with a clinician.")
            risk_points += 8

    sleep = latest.get("sleep")
    if sleep:
        nums = extract_numbers(sleep["metric_value"])
        if nums and nums[0] < 6:
            insights.append("Sleep duration appears low.")
            recommendations.append("Protect a consistent sleep window and reduce screens/caffeine before bed.")
            risk_points += 6

    stress_values = []
    if latest.get("stress"):
        stress_values.extend(extract_numbers(latest["stress"]["metric_value"]))
    if moods:
        stress_values.extend([entry["stress_level"] for entry in moods[:5]])
    if stress_values:
        avg_stress = round(mean(stress_values[:5]), 1)
        if avg_stress >= 8:
            insights.append("Recent stress trend is high.")
            recommendations.append("Use Mental Wellness daily and consider professional support if this continues.")
            risk_points += 12
        elif avg_stress >= 5:
            insights.append("Recent stress trend is moderate.")
            recommendations.append("Add a daily breathing reset and one realistic recovery break.")
            risk_points += 6

    for key, values in history.items():
        nums = [extract_numbers(item["metric_value"])[0] for item in values[:5] if extract_numbers(item["metric_value"])]
        if len(nums) >= 3 and nums[0] > nums[-1]:
            insights.append(f"{key.replace('_', ' ').title()} is trending upward.")
            break

    if not insights:
        insights.append("Add weight, height, blood pressure, glucose, sleep, and stress metrics to unlock richer insights.")
    if not recommendations:
        recommendations.append("Keep logging a few key metrics consistently; trends are more useful than single readings.")

    score = max(35, min(96, score - risk_points + min(8, len(metrics))))
    risk_score = max(4, min(95, risk_points + max(0, 20 - len(metrics))))
    return {
        "bmi": bmi,
        "health_score": score,
        "risk_score": risk_score,
        "insights": insights[:5],
        "recommendations": recommendations[:5],
        "summary": "Your health picture improves as ZENDOC sees consistent vitals, mood, and lifestyle trends.",
    }


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/register/<user>", methods=["GET", "POST"])
def register(user):
    role = normalize_role(user)
    if role == "admin":
        abort(403)
    if request.method == "POST":
        try:
            name = clean_text(request.form.get("name"), 120, required=True)
            email = clean_email(request.form.get("email"))
            age = parse_age(request.form.get("age"))
            phone = clean_text(request.form.get("phone"), 30) or None
        except ValueError as exc:
            flash(str(exc), "error")
            return render_template("register.html", user=role, display_user=display_role(role))
        password = request.form.get("password", "")
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
        try:
            email = clean_email(request.form.get("email"))
        except ValueError:
            flash("Invalid login details.", "error")
            return render_template("login.html", user=role, display_user=display_role(role))
        password = request.form.get("password", "")
        db_user = get_db().execute(
            "SELECT * FROM users WHERE email = ? AND role = ?",
            (email, role),
        ).fetchone()
        if db_user and check_password_hash(db_user["password_hash"], password):
            session.clear()
            session["user_id"] = db_user["id"]
            session["csrf_token"] = secrets.token_urlsafe(32)
            audit_event("login", role, db_user["id"])
            get_db().commit()
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
    metrics = get_db().execute(
        "SELECT * FROM health_metrics WHERE user_id = ? ORDER BY recorded_at DESC LIMIT 30",
        (g.user["id"],),
    ).fetchall()
    moods = get_db().execute(
        "SELECT * FROM mood_entries WHERE user_id = ? ORDER BY created_at DESC LIMIT 10",
        (g.user["id"],),
    ).fetchall()
    return render_template(
        "dashboard.html",
        name=g.user["name"],
        user=display_role(role),
        stats=stats,
        appointments=appointments,
        intelligence=calculate_health_intelligence(metrics, moods),
    )


@app.route("/appointments", methods=["GET", "POST"])
@login_required
def appointments():
    db = get_db()
    if request.method == "POST":
        patient_id = g.user["id"]
        try:
            provider_email_raw = clean_text(request.form.get("provider_email"), 254)
            provider_email = clean_email(provider_email_raw) if provider_email_raw else ""
            provider_name_fallback = clean_text(request.form.get("provider_name", "Provider"), 120, required=True)
            scheduled_for = clean_text(request.form.get("scheduled_for"), 40, required=True)
            reason = clean_text(request.form.get("reason"), 1000, required=True)
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("appointments"))
        provider = db.execute("SELECT id, name FROM users WHERE email = ?", (provider_email,)).fetchone() if provider_email else None
        provider_id = provider["id"] if provider else None
        provider_name = provider["name"] if provider else provider_name_fallback
        db.execute(
            """
            INSERT INTO appointments (patient_id, provider_id, provider_name, scheduled_for, reason, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'requested', ?, ?)
            """,
            (
                patient_id,
                provider_id,
                provider_name,
                scheduled_for,
                reason,
                now_iso(),
                now_iso(),
            ),
        )
        create_notification(patient_id, "Appointment requested", "Your appointment request has been saved.")
        audit_event("appointment_requested", provider_name, patient_id)
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
    appointment = get_db().execute("SELECT * FROM appointments WHERE id = ?", (appointment_id,)).fetchone()
    if appointment is None:
        abort(404)
    if g.user["role"] not in {"admin", "hospital"} and appointment["provider_id"] != g.user["id"]:
        abort(403)
    get_db().execute(
        "UPDATE appointments SET status = ?, updated_at = ? WHERE id = ?",
        (status, now_iso(), appointment_id),
    )
    audit_event("appointment_status_updated", str(appointment_id))
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
        if upload.mimetype not in ALLOWED_UPLOAD_MIMES:
            flash("Unsupported or unsafe file type.", "error")
            return redirect(url_for("records"))
        original = secure_filename(upload.filename)
        if not original:
            flash("Invalid filename.", "error")
            return redirect(url_for("records"))
        stored = f"{secrets.token_hex(16)}-{original}"
        destination = UPLOAD_DIR / stored
        if destination.resolve().parent != UPLOAD_DIR.resolve():
            abort(400)
        upload.save(destination)
        if destination.stat().st_size == 0:
            destination.unlink(missing_ok=True)
            flash("Uploaded file is empty.", "error")
            return redirect(url_for("records"))
        db.execute(
            """
            INSERT INTO medical_records
            (owner_id, uploaded_by, title, category, original_filename, stored_filename, mime_type, file_size, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                g.user["id"],
                g.user["id"],
                clean_text(request.form.get("title", original), 160, required=True),
                clean_text(request.form.get("category", "General"), 80, required=True),
                original,
                stored,
                upload.mimetype,
                destination.stat().st_size,
                now_iso(),
            ),
        )
        create_notification(g.user["id"], "Record uploaded", "A medical record was added to your account.")
        audit_event("record_uploaded", original)
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
    audit_event("record_downloaded", record["original_filename"])
    get_db().commit()
    return send_from_directory(UPLOAD_DIR, record["stored_filename"], as_attachment=True, download_name=record["original_filename"])


@app.route("/health", methods=["GET", "POST"])
@login_required
def health_monitoring():
    db = get_db()
    if request.method == "POST":
        try:
            metric_type = clean_text(request.form.get("metric_type"), 80, required=True)
            metric_value = clean_text(request.form.get("metric_value"), 80, required=True)
            unit = clean_text(request.form.get("unit"), 30)
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("health_monitoring"))
        db.execute(
            "INSERT INTO health_metrics (user_id, metric_type, metric_value, unit, recorded_at) VALUES (?, ?, ?, ?, ?)",
            (
                g.user["id"],
                metric_type,
                metric_value,
                unit,
                now_iso(),
            ),
        )
        audit_event("health_metric_saved", metric_type)
        db.commit()
        flash("Health metric saved.", "success")
        return redirect(url_for("health_monitoring"))
    rows = db.execute(
        "SELECT * FROM health_metrics WHERE user_id = ? ORDER BY recorded_at DESC LIMIT 30",
        (g.user["id"],),
    ).fetchall()
    moods = db.execute(
        "SELECT * FROM mood_entries WHERE user_id = ? ORDER BY created_at DESC LIMIT 10",
        (g.user["id"],),
    ).fetchall()
    intelligence = calculate_health_intelligence(rows, moods)
    return render_template("health.html", metrics=rows, moods=moods, intelligence=intelligence)


@app.route("/ai", methods=["GET", "POST"])
@login_required
def ai_center():
    result = None
    if request.method == "POST":
        feature = request.form.get("feature")
        if feature == "doctor":
            result = ai_doctor_prediction(request.form.get("symptoms", ""))
            result_text, risk = result["text"], result["risk"]
            input_text = request.form.get("symptoms", "")
        elif feature == "assistant":
            result = smart_assistant_response(request.form.get("message", ""))
            result_text, risk = result["text"], result["risk"]
            input_text = request.form.get("message", "")
        elif feature == "mental_health":
            result = mental_health_support(
                request.form.get("age_group", "adult"),
                request.form.get("context", ""),
                request.form.get("stress_level", 0),
                request.form.get("mood", "neutral"),
            )
            result_text, risk = result["text"], result["risk"]
            input_text = f"{request.form.get('age_group')} | stress={request.form.get('stress_level')} | {request.form.get('context')}"
            get_db().execute(
                """
                INSERT INTO mood_entries (user_id, mood, stress_level, context, wellness_score, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    g.user["id"],
                    result.get("mood", "neutral"),
                    result.get("stress", 0),
                    clean_text(request.form.get("context"), 1000),
                    result.get("wellness_score", 50),
                    now_iso(),
                ),
            )
        else:
            abort(400)
        get_db().execute(
            "INSERT INTO ai_interactions (user_id, feature, input_text, output_text, risk_level, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (g.user["id"], feature, input_text, result_text, risk, now_iso()),
        )
        remember_ai_context(feature, input_text, result.get("summary", result_text[:160]))
        audit_event("ai_interaction", feature)
        get_db().commit()
    history = get_db().execute(
        "SELECT * FROM ai_interactions WHERE user_id = ? ORDER BY created_at DESC LIMIT 10",
        (g.user["id"],),
    ).fetchall()
    return render_template("ai.html", result=result, history=history)


@app.route("/admin")
@role_required("admin")
def admin():
    return render_template(
        "admin.html",
        stats=dashboard_stats(g.user),
        analytics=investor_analytics(),
        owner_name=OWNER_NAME,
        owner_email=OWNER_EMAIL,
    )


def api_user_from_token():
    header = request.headers.get("Authorization", "")
    token = header.removeprefix("Bearer ").strip()
    if not token:
        return None
    token_lookup = hash_token(token)
    return get_db().execute(
        """
        SELECT users.* FROM api_tokens
        JOIN users ON users.id = api_tokens.user_id
        WHERE api_tokens.token = ?
        """,
        (token_lookup,),
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
        name = clean_text(payload.get("name"), 120, required=True)
        email = clean_email(payload.get("email"))
        age = parse_age(payload.get("age"))
        phone = clean_text(payload.get("phone"), 30) or None
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    try:
        get_db().execute(
            """
            INSERT INTO users (name, email, password_hash, role, phone, age, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                email,
                generate_password_hash(password),
                role,
                phone,
                age,
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
    try:
        email = clean_email(payload.get("email"))
    except ValueError:
        return jsonify({"error": "Invalid credentials"}), 401
    user = get_db().execute(
        "SELECT * FROM users WHERE email = ? AND role = ?",
        (email, payload.get("role", "patient")),
    ).fetchone()
    if not user or not check_password_hash(user["password_hash"], payload.get("password", "")):
        return jsonify({"error": "Invalid credentials"}), 401
    token = secrets.token_urlsafe(40)
    get_db().execute(
        "INSERT INTO api_tokens (user_id, token, created_at) VALUES (?, ?, ?)",
        (user["id"], hash_token(token), now_iso()),
    )
    audit_event("api_login", user["role"], user["id"])
    get_db().commit()
    return jsonify({"token": token, "user": {"id": user["id"], "name": user["name"], "role": user["role"]}})


@app.get("/api/v1/dashboard")
@api_login_required
def api_dashboard():
    metrics = get_db().execute(
        "SELECT * FROM health_metrics WHERE user_id = ? ORDER BY recorded_at DESC LIMIT 30",
        (g.api_user["id"],),
    ).fetchall()
    moods = get_db().execute(
        "SELECT * FROM mood_entries WHERE user_id = ? ORDER BY created_at DESC LIMIT 10",
        (g.api_user["id"],),
    ).fetchall()
    return jsonify({"stats": dashboard_stats(g.api_user), "health_intelligence": calculate_health_intelligence(metrics, moods)})


@app.post("/api/v1/ai/doctor")
@api_login_required
def api_ai_doctor():
    payload = request.get_json(silent=True) or {}
    result = ai_doctor_prediction(payload.get("symptoms", ""))
    remember_ai_context("doctor", payload.get("symptoms", ""), result.get("summary", ""))
    get_db().execute(
        "INSERT INTO ai_interactions (user_id, feature, input_text, output_text, risk_level, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (g.api_user["id"], "doctor", clean_text(payload.get("symptoms", ""), 1200), result["text"], result["risk"], now_iso()),
    )
    get_db().commit()
    return jsonify(result)


@app.post("/api/v1/ai/assistant")
@api_login_required
def api_ai_assistant():
    payload = request.get_json(silent=True) or {}
    result = smart_assistant_response(payload.get("message", ""))
    remember_ai_context("assistant", payload.get("message", ""), result.get("summary", ""))
    get_db().execute(
        "INSERT INTO ai_interactions (user_id, feature, input_text, output_text, risk_level, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (g.api_user["id"], "assistant", clean_text(payload.get("message", ""), 1200), result["text"], result["risk"], now_iso()),
    )
    get_db().commit()
    return jsonify(result)


@app.post("/api/v1/ai/mental-health")
@api_login_required
def api_ai_mental_health():
    payload = request.get_json(silent=True) or {}
    result = mental_health_support(
        payload.get("age_group", "adult"),
        payload.get("context", ""),
        payload.get("stress_level", 0),
        payload.get("mood", "neutral"),
    )
    remember_ai_context("mental_health", payload.get("context", ""), result.get("summary", ""))
    get_db().execute(
        """
        INSERT INTO mood_entries (user_id, mood, stress_level, context, wellness_score, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            g.api_user["id"],
            result.get("mood", "neutral"),
            result.get("stress", 0),
            clean_text(payload.get("context"), 1000),
            result.get("wellness_score", 50),
            now_iso(),
        ),
    )
    get_db().execute(
        "INSERT INTO ai_interactions (user_id, feature, input_text, output_text, risk_level, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (g.api_user["id"], "mental_health", clean_text(payload.get("context", ""), 1200), result["text"], result["risk"], now_iso()),
    )
    get_db().commit()
    return jsonify(result)


init_db()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
