"""Conversation-first web UI for ZENDOC AI and Doctor AI.

Presentation/orchestration layer over the existing safety-first intelligence
engine. It does not add autonomous clinical actions.
"""
from __future__ import annotations

from flask import Blueprint, g, redirect, render_template, request, url_for

from .ai_types import IntelligenceResult
from .db import get_db, now_iso
from .intelligence import ZendocIntelligence
from .security import login_required

bp = Blueprint("ai_chat", __name__)
DOCTOR_PREFIX = "[Doctor AI] "
DOCTOR_ALLOWED = {
    "emergency", "symptoms", "appointment", "doctor", "hospital", "clinic",
    "pharmacy", "medicine", "mental_wellness", "sleep", "health_records",
    "report_history", "report_intelligence", "medical_report", "health_profile",
    "health_monitoring", "general_assistant",
}
DOCTOR_HEALTH_TERMS = {
    "pain", "fever", "cough", "cold", "rash", "headache", "blood", "heart",
    "chest", "breath", "doctor", "hospital", "clinic", "medicine", "medical",
    "symptom", "report", "test", "health", "sleep", "stress", "injury", "skin",
    "eye", "ear", "stomach", "nausea", "vomit", "weak", "dizzy", "pressure",
    "sugar", "diabetes", "pregnan", "child", "mental", "anxiety", "depress",
}


def _mode(value):
    return "doctor" if str(value or "").strip().lower() == "doctor" else "zendoc"


def _conversation_title(message, mode):
    clean = " ".join(str(message or "").strip().split())[:60] or "New conversation"
    return f"{DOCTOR_PREFIX}{clean}" if mode == "doctor" else clean


def _conversation_for_user(conversation_id, user_id):
    if not conversation_id:
        return None
    try:
        conversation_id = int(conversation_id)
    except (TypeError, ValueError):
        return None
    return get_db().execute("SELECT * FROM ai_conversations WHERE id=? AND user_id=?", (conversation_id, user_id)).fetchone()


def _conversation_mode(conversation):
    title = str(conversation["title"] or "") if conversation else ""
    return "doctor" if title.startswith(DOCTOR_PREFIX) else "zendoc"


def _create_conversation(user_id, message, mode):
    now = now_iso()
    cursor = get_db().execute(
        "INSERT INTO ai_conversations (user_id,title,created_at,updated_at) VALUES (?,?,?,?)",
        (user_id, _conversation_title(message, mode), now, now),
    )
    get_db().commit()
    return get_db().execute("SELECT * FROM ai_conversations WHERE id=?", (cursor.lastrowid,)).fetchone()


def _recent_conversations(user_id, mode):
    if mode == "doctor":
        return get_db().execute(
            "SELECT * FROM ai_conversations WHERE user_id=? AND title LIKE ? ORDER BY updated_at DESC LIMIT 30",
            (user_id, f"{DOCTOR_PREFIX}%"),
        ).fetchall()
    return get_db().execute(
        "SELECT * FROM ai_conversations WHERE user_id=? AND (title IS NULL OR title NOT LIKE ?) ORDER BY updated_at DESC LIMIT 30",
        (user_id, f"{DOCTOR_PREFIX}%"),
    ).fetchall()


def _history(user_id, conversation_id):
    if not conversation_id:
        return []
    return get_db().execute(
        "SELECT * FROM ai_interactions WHERE user_id=? AND conversation_id=? ORDER BY created_at ASC,id ASC LIMIT 100",
        (user_id, conversation_id),
    ).fetchall()


def _doctor_scope(result, message):
    if result.emergency:
        return result
    lower = str(message or "").lower()
    health_related = any(term in lower for term in DOCTOR_HEALTH_TERMS)
    if result.intent not in DOCTOR_ALLOWED or (result.intent == "general_assistant" and not health_related):
        return IntelligenceResult(
            intent="doctor_ai_scope",
            urgency="routine",
            message=("Doctor AI is reserved for health concerns, symptoms, reports, medicines, care navigation, "
                     "and deciding what type of clinician to contact. Use ZENDOC AI for other platform questions."),
            follow_up_questions=["What health concern would you like help organizing?"],
            possible_actions=[{"type": "find_healthcare", "label": "Find healthcare"}],
            provider="doctor_ai_scope_guard",
            safety_notice="Educational guidance only. Doctor AI does not diagnose or prescribe.",
        )
    return result


def _log_interaction(user_id, conversation_id, message, result, latency_ms, mode):
    db = get_db()
    db.execute(
        """INSERT INTO ai_interactions
        (user_id,conversation_id,feature,intent,input_text,output_text,risk_level,model_version,provider,emergency,success,latency_ms,created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (user_id, conversation_id, "doctor_ai" if mode == "doctor" else "zendoc_ai", result.intent,
         message[:500], result.message, result.urgency, "zendoc-chat-v2", result.provider,
         1 if result.emergency else 0, 1 if result.success else 0, latency_ms, now_iso()),
    )
    db.execute("UPDATE ai_conversations SET last_intent=?,updated_at=? WHERE id=? AND user_id=?",
               (result.intent, now_iso(), conversation_id, user_id))
    db.commit()


@bp.route("/ai", methods=("GET", "POST"))
@login_required
def chat_home():
    requested_mode = _mode(request.values.get("mode"))
    conversation = _conversation_for_user(request.values.get("conversation_id"), g.user["id"])
    if conversation:
        requested_mode = _conversation_mode(conversation)
    if request.method == "POST":
        message = (request.form.get("message") or request.form.get("symptoms") or "").strip()
        if str(request.form.get("feature") or "").strip().lower() == "doctor":
            requested_mode = "doctor"
        if not message:
            return redirect(url_for("ai_chat.chat_home", mode=requested_mode))
        if conversation is None:
            conversation = _create_conversation(g.user["id"], message, requested_mode)
        result, latency_ms = ZendocIntelligence().respond(message, user=g.user, conversation=conversation)
        if requested_mode == "doctor":
            result = _doctor_scope(result, message)
        result.conversation_id = conversation["id"]
        _log_interaction(g.user["id"], conversation["id"], message, result, latency_ms, requested_mode)
        return redirect(url_for("ai_chat.chat_home", mode=requested_mode, conversation_id=conversation["id"]) + "#chat-end")
    new_chat = str(request.args.get("new") or "").lower() in {"1", "true", "yes"}
    conversations = _recent_conversations(g.user["id"], requested_mode)
    if new_chat:
        conversation = None
    elif conversation is None and conversations:
        conversation = conversations[0]
    history = _history(g.user["id"], conversation["id"] if conversation else None)
    return render_template("ai_chat.html", mode=requested_mode, selected_conversation=conversation,
                           conversations=conversations, history=history)
