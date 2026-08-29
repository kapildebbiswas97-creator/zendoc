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
from .telehealth import get_doctor_availability, request_consultation
from .agent_executor import execute_plan
from .agent_planner import build_plan
from .agent_registry import list_agents
from .agent_task_engine import create_agent_task, execute_safe_task, set_task_waiting

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
        "agent_tasks": "agent_tasks",
        "agent_alerts": "agent_alerts",
        "model_executions": "model_execution_logs",
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
    plan = build_plan(actor, command)
    if plan.authorization_error:
        raise PermissionError(plan.authorization_error)

    task = create_agent_task(
        task_type="core_agent_command",
        requested_by=_user_id(actor),
        assigned_agent=plan.assigned_agent,
        priority="critical" if plan.urgency == "emergency" else "normal",
        risk_level=plan.risk_level,
        metadata={"intent": plan.intent, "plan_id": plan.plan_id},
        actor=actor,
    )

    if plan.intent == "emergency":
        safety = plan.safety
        task = execute_safe_task(task["id"], actor, handler_fn=lambda _task: safety["guidance"])
        duration = int((time.perf_counter() - started) * 1000)
        run_id = create_agent_run(actor, command, "emergency", "completed", "emergency", safety["guidance"], duration_ms=duration)
        log_agent_action(run_id, actor, "emergency_escalation", "SafetyAgent.assess", "safety_alert", str(run_id), message=safety["guidance"])
        log_platform_event(actor, "emergency_escalation", "agent_run", str(run_id), "info", "Safety Agent", duration_ms=duration)
        get_db().commit()
        return {
            "run_id": run_id,
            "task_id": task["id"],
            "plan": plan.to_dict(),
            "intent": "emergency",
            "urgency": "emergency",
            "message": f"{safety['reason']} {safety['guidance']}",
            "actions": [{"type": "emergency_care", "label": "Call emergency services now"}],
            "requires_confirmation": False,
        }

    execution = {"status": "waiting_human", "tool_results": []}
    if plan.requires_confirmation:
        task = set_task_waiting(task["id"], "waiting_human", "Explicit user confirmation is required before execution.")
    else:
        execution_holder = {}

        def _run_plan(_task):
            execution_holder["result"] = execute_plan(plan, actor)
            return f"{plan.assigned_agent} completed {len(plan.steps)} bounded tool step(s)."

        task = execute_safe_task(task["id"], actor, handler_fn=_run_plan)
        if task["status"] == "failed":
            raise ValueError(task.get("result_summary") or "Core Agent plan failed.")
        execution = execution_holder.get("result") or execution

    tool_results = execution.get("tool_results", [])
    tool_output = tool_results[0]["output"] if tool_results else None
    actions = []
    requires_confirmation = plan.requires_confirmation

    if plan.intent == "platform_health":
        payload = tool_output or get_platform_health()
        if isinstance(payload, dict) and "created_alerts" in payload:
            message = f"Operational alert scan completed and created {len(payload['created_alerts'])} new alert(s)."
            actions = [{"type": "alert_check", "label": "Reviewed operational alerts", "data": payload}]
        else:
            message = f"Platform health is {payload['status']}. Active counts: {payload['counts']}."
            actions = [{"type": "platform_health", "label": "Reviewed platform health", "data": payload}]
        intent = "platform_health"
    elif plan.intent == "failed_operations":
        payload = tool_output or []
        message = f"Found {len(payload)} failed or errored platform events."
        intent = "failed_operations"
        actions = [{"type": "failed_operations", "label": "Show failed operations", "data": payload}]
    elif plan.intent == "contact_discovery":
        contacts = tool_output or []
        message = f"Found {len(contacts)} permitted contact(s) for your account."
        intent = "contact_discovery"
        actions = [{"type": "contact_list", "label": "View permitted contacts", "data": contacts, "url": "/messages"}]
    elif plan.intent == "record_share_request":
        message = "Sharing medical records requires patient owner consent or explicit communication grant. Please confirm the recipient and report."
        intent = "record_share_request"
        actions = [{"type": "confirm_record_share", "label": "Select conversation and verify consent", "url": "/messages"}]
    elif plan.intent == "video_share":
        message = "You can share educational videos into active conversations through ZENDOC Connect after confirming the destination."
        intent = "video_share"
        actions = [{"type": "video_share", "label": "Open Videos or Messages", "url": "/videos"}]
    elif plan.intent == "messages_inbox":
        count = int((tool_output or {}).get("unread_count", 0))
        message = f"You have {count} unread message(s) in ZENDOC Connect."
        intent = "messages_inbox"
        actions = [{"type": "messages_inbox", "label": "Open Messages", "url": "/messages"}]
    elif plan.intent == "video_intelligence":
        payload = tool_output or {}
        message = payload.get("reason") or f"Found {len(payload.get('results', []))} educational video results."
        intent = "video_intelligence"
        actions = [{"type": "video_results", "label": "Review educational videos", "data": payload}]
    elif plan.intent == "iot_status":
        payload = tool_output or []
        message = f"I found {len(payload)} connected device records available to this account."
        intent = "iot_status"
        actions = [{"type": "iot_devices", "label": "Open Connected Devices", "url": "/iot-hub"}]
    elif plan.intent == "telehealth_request":
        message = "Telehealth requests are available as a beta workflow. A doctor must accept before chat, voice, or video room controls are shown."
        intent = "telehealth_request"
        actions = [{"type": "telehealth", "label": "Open Telehealth", "url": "/telehealth"}]
    elif plan.intent == "care_coordination":
        message = "I can route this to Family Care or Home Healthcare, but another adult patient's care requires an active family access grant."
        intent = "care_coordination"
        actions = [{"type": "home_health", "label": "Open Home Healthcare", "url": "/home-health"}]
    else:
        from .model_router import get_model_router
        model_response = get_model_router().route(
            command,
            intent="general",
            task_type="core_agent_guidance",
            privacy_sensitive=True,
            allow_cloud=False,
            actor_id=_user_id(actor),
        )
        message = model_response.text
        intent = "general_agent"
        actions = [{"type": "agent_help", "label": "Show available agent tools"}]

    # Compatibility: the M7 response shape is preserved and M8 metadata is additive.
    duration = int((time.perf_counter() - started) * 1000)
    run_id = create_agent_run(actor, command, intent, "completed", "routine", message, duration_ms=duration)
    for result in tool_results:
        get_db().execute(
            """
            INSERT INTO agent_tool_calls
            (run_id, actor_id, tool_name, input_summary, output_summary, status, duration_ms, created_at)
            VALUES (?, ?, ?, ?, ?, 'completed', ?, ?)
            """,
            (
                run_id,
                _user_id(actor),
                result["tool_name"],
                "Validated planner arguments",
                f"Bounded {result['tool_name']} result",
                result.get("duration_ms"),
                now_iso(),
            ),
        )
    for action in actions:
        log_agent_action(run_id, actor, action["type"], entity_type=intent, message=action.get("label"))
    log_platform_event(actor, intent, "agent_run", str(run_id), "info", plan.assigned_agent, duration_ms=duration)
    get_db().commit()
    try:
        from .event_bus import publish_event
        publish_event(
            "agent.run.completed",
            actor=actor,
            entity_type="agent_run",
            entity_id=str(run_id),
            status="completed",
            agent_name=plan.assigned_agent,
            duration_ms=duration,
            correlation_id=plan.plan_id,
            payload={"intent": intent, "task_id": task["id"], "tool_count": len(tool_results)},
        )
    except Exception:
        pass
    return {
        "run_id": run_id,
        "task_id": task["id"],
        "plan": plan.to_dict(),
        "intent": intent,
        "urgency": "routine",
        "message": message,
        "actions": actions,
        "requires_confirmation": requires_confirmation,
    }


def admin_command_center_data():
    from .agent_alerts import list_alerts
    from .agent_approvals import list_pending_approvals
    from .agent_task_engine import list_agent_tasks
    from .capability_registry import get_capability_registry
    from .infrastructure import infrastructure_status
    from .model_router import get_model_router
    from .tool_registry import TOOL_REGISTRY

    db = get_db()
    agents = list_agents()
    return {
        "platform_health": get_platform_health(),
        "specialized_agents": [{**agent, "scope": agent["purpose"]} for agent in agents],
        "failed_operations": get_failed_operations(),
        "agent_runs": get_agent_audit_log(),
        "consultations": [dict(row) for row in db.execute("SELECT * FROM consultation_requests ORDER BY created_at DESC LIMIT 25").fetchall()],
        "home_health_requests": [dict(row) for row in db.execute("SELECT * FROM home_health_requests ORDER BY created_at DESC LIMIT 25").fetchall()],
        "transport_requests": [dict(row) for row in db.execute("SELECT * FROM ambulance_requests ORDER BY created_at DESC LIMIT 25").fetchall()],
        "pharmacy_requests": [dict(row) for row in db.execute("SELECT * FROM medicine_orders ORDER BY created_at DESC LIMIT 25").fetchall()],
        "staff_tasks": [dict(row) for row in db.execute("SELECT * FROM staff_tasks ORDER BY created_at DESC LIMIT 25").fetchall()],
        "platform_events": [dict(row) for row in db.execute("SELECT * FROM platform_events ORDER BY created_at DESC LIMIT 50").fetchall()],
        "agent_tasks": list_agent_tasks(limit=25),
        "pending_approvals": list_pending_approvals(),
        "active_alerts": list_alerts("active", limit=25),
        "model_router": get_model_router().status(),
        "capabilities": get_capability_registry(),
        "infrastructure": infrastructure_status(),
        "tool_registry": [tool.to_dict() for tool in TOOL_REGISTRY.values()],
        "schema_migrations": [dict(row) for row in db.execute("SELECT * FROM schema_migrations ORDER BY applied_at DESC").fetchall()],
    }
