import time

from flask import current_app

from .communication_policy import (
    can_call,
    can_discover_contact,
    can_message,
    can_share_record,
    can_start_conversation,
    can_video_call,
    permission_decision,
)
from .connect import (
    discover_contacts,
    get_conversation,
    list_conversations,
    list_messages,
    send_message,
    share_report_message,
    share_video_message,
    start_conversation,
    unread_count,
)
from .db import get_db, now_iso
from .iot_hub import list_devices
from .safety import SafetyEngine
from .telehealth import get_doctor_availability, request_consultation
from .video_intelligence import find_educational_video


SPECIALIZED_AGENTS = (
    {"name": "Care Agent", "status": "connected", "scope": "appointments, reports, family care"},
    {"name": "Doctor/Telehealth Agent", "status": "beta", "scope": "doctor availability and consultation requests"},
    {"name": "Communication Agent", "status": "connected", "scope": "permissioned messaging, contacts, video/report sharing"},
    {"name": "Fitness Agent", "status": "connected", "scope": "plans, sessions, pose coach"},
    {"name": "Operations Agent", "status": "beta", "scope": "staff tasks and operational queues"},
    {"name": "Family Care Agent", "status": "connected", "scope": "remote parent care with consent"},
    {"name": "Pharmacy Agent", "status": "beta", "scope": "medicine search and requests"},
    {"name": "Transport Agent", "status": "integration_required", "scope": "transport requests without live dispatch"},
    {"name": "Home Health Agent", "status": "integration_required", "scope": "home-care request intake"},
    {"name": "IoT Agent", "status": "beta", "scope": "authorized device measurements"},
    {"name": "Video Intelligence Agent", "status": "beta", "scope": "educational video search"},
    {"name": "Safety Agent", "status": "connected", "scope": "emergency-first routing"},
)


def _value(user, key, default=None):
    if user is None:
        return default
    if hasattr(user, "keys") and key in user.keys():
        return user[key]
    return user.get(key, default) if isinstance(user, dict) else default


def _user_id(user):
    return int(_value(user, "id", 0) or 0)


def tool_find_contact(actor, query=""):
    return discover_contacts(actor, query=query)


def tool_check_communication_permission(actor, target_user_id, channel="chat", context=None):
    return permission_decision(actor, target_user_id, context=context, channel=channel)


def tool_start_conversation(actor, target_user_id, context=None, title=None):
    data = {"target_user_id": target_user_id, "title": title}
    if context:
        data.update(context)
    return start_conversation(actor, data)


def tool_send_message(actor, conversation_id, body, message_type="text", metadata=None):
    return send_message(actor, conversation_id, {"body": body, "message_type": message_type, "metadata": metadata})


def tool_request_doctor_chat(actor, doctor_id, reason="Doctor consultation request"):
    decision = can_message(actor, doctor_id)
    if decision["allowed"]:
        return start_conversation(actor, {"target_user_id": doctor_id, "context_type": "direct"})
    availability = get_doctor_availability(doctor_id)
    if availability.get("allow_new_consultation_requests"):
        return request_consultation(actor, {"doctor_id": doctor_id, "consultation_type": "chat", "reason": reason})
    raise PermissionError(decision["reason"])


def tool_request_voice_call(actor, target_user_id, context=None):
    return can_call(actor, target_user_id, context=context)


def tool_request_video_call(actor, target_user_id, context=None):
    return can_video_call(actor, target_user_id, context=context)


def tool_share_video(actor, conversation_id, video_url, title="Educational Video"):
    return share_video_message(actor, conversation_id, {"video_url": video_url, "title": title})


def tool_share_report_with_consent(actor, conversation_id, record_id, title=None):
    return share_report_message(actor, conversation_id, {"record_id": record_id, "title": title})


def log_platform_event(actor, action, entity_type, entity_id=None, status="info", agent_name=None, error=None, approval_state="not_required", duration_ms=None):
    get_db().execute(
        """
        INSERT INTO platform_events
        (actor_id, agent_name, action, entity_type, entity_id, status, error, approval_state, duration_ms, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (_user_id(actor) or None, agent_name, action, entity_type, entity_id, status, error, approval_state, duration_ms, now_iso()),
    )


def create_agent_run(actor, command_text, intent, status="completed", urgency="routine", result_summary="", approval_state="not_required", duration_ms=None):
    cursor = get_db().execute(
        """
        INSERT INTO agent_runs
        (actor_id, agent_name, command_text, intent, status, urgency, result_summary, approval_state, duration_ms, created_at)
        VALUES (?, 'ZENDOC Core Agent', ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (_user_id(actor) or None, command_text[:1000], intent, status, urgency, result_summary[:1200], approval_state, duration_ms, now_iso()),
    )
    return cursor.lastrowid


def log_agent_action(run_id, actor, action_type, tool_name=None, entity_type=None, entity_id=None, status="completed", message=None, approval_state="not_required"):
    get_db().execute(
        """
        INSERT INTO agent_actions
        (run_id, actor_id, agent_name, action_type, tool_name, entity_type, entity_id, status, approval_state, message, created_at)
        VALUES (?, ?, 'ZENDOC Core Agent', ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (run_id, _user_id(actor) or None, action_type, tool_name, entity_type, entity_id, status, approval_state, message, now_iso()),
    )


def get_platform_health():
    db = get_db()
    counts = {}
    for label, table in {
        "users": "users",
        "appointments": "appointments",
        "conversations": "conversations",
        "messages": "messages",
        "home_health_requests": "home_health_requests",
        "transport_requests": "ambulance_requests",
        "medicine_orders": "medicine_orders",
        "consultations": "consultation_requests",
        "staff_tasks": "staff_tasks",
        "agent_runs": "agent_runs",
        "devices": "health_devices",
    }.items():
        counts[label] = db.execute(f"SELECT COUNT(*) c FROM {table}").fetchone()["c"]
    failed_operations = db.execute("SELECT COUNT(*) c FROM platform_events WHERE status IN ('failed','error')").fetchone()["c"]
    integration_status = {
        "ai_provider": current_app.config.get("ZENDOC_AI_PROVIDER") or current_app.config.get("AI_PROVIDER", "local"),
        "places_provider": current_app.config.get("PLACES_PROVIDER", "none"),
        "video_provider": current_app.config.get("VIDEO_PROVIDER", "none"),
        "telehealth_signaling": "local_demo",
        "email_sms_whatsapp_push": "integration_required",
    }
    return {"status": "ok", "counts": counts, "failed_operations": failed_operations, "integration_status": integration_status}


def get_failed_operations(limit=25):
    rows = get_db().execute(
        """
        SELECT * FROM platform_events
        WHERE status IN ('failed','error')
        ORDER BY created_at DESC LIMIT ?
        """,
        (max(1, min(int(limit or 25), 100)),),
    ).fetchall()
    return [dict(row) for row in rows]


def get_agent_audit_log(limit=50):
    rows = get_db().execute(
        """
        SELECT ar.*, u.name actor_name, u.role actor_role
        FROM agent_runs ar LEFT JOIN users u ON u.id=ar.actor_id
        ORDER BY ar.created_at DESC LIMIT ?
        """,
        (max(1, min(int(limit or 50), 100)),),
    ).fetchall()
    return [dict(row) for row in rows]


def respond_with_core_agent(actor, command_text):
    if not actor:
        raise PermissionError("Authentication required.")
    started = time.perf_counter()
    command = str(command_text or "").strip()
    if not command:
        raise ValueError("Agent command is required.")

    safety = SafetyEngine().assess(command)
    if safety["emergency"]:
        duration = int((time.perf_counter() - started) * 1000)
        run_id = create_agent_run(actor, command, "emergency", "completed", "emergency", safety["guidance"], duration_ms=duration)
        log_agent_action(run_id, actor, "emergency_escalation", "SafetyAgent.assess", "safety_alert", str(run_id), message=safety["guidance"])
        log_platform_event(actor, "emergency_escalation", "agent_run", str(run_id), "info", "Safety Agent", duration_ms=duration)
        get_db().commit()
        return {
            "run_id": run_id,
            "intent": "emergency",
            "urgency": "emergency",
            "message": f"{safety['reason']} {safety['guidance']}",
            "actions": [{"type": "emergency_care", "label": "Call emergency services now"}],
            "requires_confirmation": False,
        }

    lower = command.lower()
    role = _value(actor, "role")
    actions = []
    requires_confirmation = False

    if role == "admin" and any(text in lower for text in ("summary", "platform health", "operations summary", "today")):
        payload = get_platform_health()
        message = f"Platform health is {payload['status']}. Active counts: {payload['counts']}."
        intent = "platform_health"
        actions = [{"type": "platform_health", "label": "Reviewed platform health", "data": payload}]
    elif role == "admin" and "failed" in lower:
        payload = get_failed_operations()
        message = f"Found {len(payload)} failed or errored platform events."
        intent = "failed_operations"
        actions = [{"type": "failed_operations", "label": "Show failed operations", "data": payload}]
    elif any(text in lower for text in ("find contact", "search contact", "discover contact", "who can i message", "search doctor")):
        query = command.replace("find contact", "").replace("search contact", "").replace("who can i message", "").strip()
        contacts = tool_find_contact(actor, query=query or "doctor")
        message = f"Found {len(contacts)} permitted contact(s) for your account."
        intent = "contact_discovery"
        actions = [{"type": "contact_list", "label": "View permitted contacts", "data": contacts, "url": "/messages"}]
    elif any(text in lower for text in ("share report", "send report", "share medical record")):
        message = "Sharing medical records requires patient owner consent or explicit communication grant. Please confirm the recipient and report."
        intent = "record_share_request"
        requires_confirmation = True
        actions = [{"type": "confirm_record_share", "label": "Select conversation and verify consent", "url": "/messages"}]
    elif "share video" in lower:
        message = "You can share educational videos into active conversations through ZENDOC Connect."
        intent = "video_share"
        actions = [{"type": "video_share", "label": "Open Videos or Messages", "url": "/videos"}]
    elif any(text in lower for text in ("unread message", "check message", "my message", "inbox")):
        count = unread_count(actor)
        message = f"You have {count} unread message(s) in ZENDOC Connect."
        intent = "messages_inbox"
        actions = [{"type": "messages_inbox", "label": "Open Messages", "url": "/messages"}]
    elif "video" in lower:
        payload = find_educational_video(actor, command, category=_video_category(lower))
        message = payload.get("reason") or f"Found {len(payload.get('results', []))} educational video results."
        intent = "video_intelligence"
        actions = [{"type": "video_results", "label": "Review educational videos", "data": payload}]
    elif "device" in lower or "iot" in lower or "blood pressure" in lower or "heart rate" in lower:
        payload = list_devices(actor) if role in {"patient", "admin"} else []
        message = f"I found {len(payload)} connected device records available to this account."
        intent = "iot_status"
        actions = [{"type": "iot_devices", "label": "Open Connected Devices", "url": "/iot-hub"}]
    elif "video consultation" in lower or "doctor video" in lower or "consultation" in lower:
        message = "Telehealth requests are available as a beta workflow. A doctor must accept before chat, voice, or video room controls are shown."
        intent = "telehealth_request"
        actions = [{"type": "telehealth", "label": "Open Telehealth", "url": "/telehealth"}]
    elif "home care" in lower or "nurse" in lower or "parent" in lower:
        message = "I can route this to Family Care or Home Healthcare, but another adult patient's care requires an active family access grant."
        intent = "care_coordination"
        actions = [{"type": "home_health", "label": "Open Home Healthcare", "url": "/home-health"}]
    else:
        message = "ZENDOC Core Agent can route care, telehealth, messaging, pharmacy, transport, fitness, IoT, video, and operations requests through permissioned tools."
        intent = "general_agent"
        actions = [{"type": "agent_help", "label": "Show available agent tools"}]

    duration = int((time.perf_counter() - started) * 1000)
    run_id = create_agent_run(actor, command, intent, "completed", "routine", message, duration_ms=duration)
    for action in actions:
        log_agent_action(run_id, actor, action["type"], entity_type=intent, message=action.get("label"))
    log_platform_event(actor, intent, "agent_run", str(run_id), "info", "ZENDOC Core Agent", duration_ms=duration)
    get_db().commit()
    return {
        "run_id": run_id,
        "intent": intent,
        "urgency": "routine",
        "message": message,
        "actions": actions,
        "requires_confirmation": requires_confirmation,
    }


def admin_command_center_data():
    db = get_db()
    return {
        "platform_health": get_platform_health(),
        "specialized_agents": SPECIALIZED_AGENTS,
        "failed_operations": get_failed_operations(),
        "agent_runs": get_agent_audit_log(),
        "consultations": [dict(row) for row in db.execute("SELECT * FROM consultation_requests ORDER BY created_at DESC LIMIT 25").fetchall()],
        "home_health_requests": [dict(row) for row in db.execute("SELECT * FROM home_health_requests ORDER BY created_at DESC LIMIT 25").fetchall()],
        "transport_requests": [dict(row) for row in db.execute("SELECT * FROM ambulance_requests ORDER BY created_at DESC LIMIT 25").fetchall()],
        "pharmacy_requests": [dict(row) for row in db.execute("SELECT * FROM medicine_orders ORDER BY created_at DESC LIMIT 25").fetchall()],
        "staff_tasks": [dict(row) for row in db.execute("SELECT * FROM staff_tasks ORDER BY created_at DESC LIMIT 25").fetchall()],
        "platform_events": [dict(row) for row in db.execute("SELECT * FROM platform_events ORDER BY created_at DESC LIMIT 50").fetchall()],
    }


def _video_category(text):
    if "device" in text or "iot" in text:
        return "device_setup"
    if "nutrition" in text or "diet" in text:
        return "nutrition"
    if "rehab" in text or "mobility" in text:
        return "rehabilitation"
    if "staff" in text or "training" in text:
        return "staff_training"
    if "doctor" in text or "patient education" in text:
        return "patient_education"
    return "fitness"

