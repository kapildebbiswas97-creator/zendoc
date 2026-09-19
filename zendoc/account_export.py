"""User-scoped ZENDOC data portability export.

This module exports data the authenticated user owns or is already authorized
to read. It deliberately excludes password hashes, API/reset tokens, security
secrets, internal record storage keys, and bulk patient-health payloads from
provider account exports.
"""
from __future__ import annotations

from typing import Any

from .db import get_db, now_iso
from .policy_acceptance import list_policy_acceptances
from .email_verification import email_verification_status


def _value(user: Any, key: str, default=None):
    if user is None:
        return default
    if hasattr(user, "keys") and key in user.keys():
        return user[key]
    if isinstance(user, dict):
        return user.get(key, default)
    return default


def _rows(sql: str, params=()) -> list[dict]:
    return [dict(row) for row in get_db().execute(sql, params).fetchall()]


def _row(sql: str, params=()) -> dict | None:
    row = get_db().execute(sql, params).fetchone()
    return dict(row) if row else None


def _conversation_export(user_id: int) -> dict:
    conversations = _rows(
        """
        SELECT c.id,c.conversation_type,c.title,c.context_type,c.context_id,
               c.status,c.created_at,c.updated_at,
               cp.role participant_role,cp.joined_at,cp.last_read_at,cp.muted
        FROM conversation_participants cp
        JOIN conversations c ON c.id=cp.conversation_id
        WHERE cp.user_id=?
        ORDER BY c.updated_at DESC,c.id DESC
        """,
        (user_id,),
    )
    conversation_ids = [int(item["id"]) for item in conversations]
    messages = []
    for conversation_id in conversation_ids:
        messages.extend(
            _rows(
                """
                SELECT m.id,m.conversation_id,m.message_type,m.body,
                       m.created_at,m.edited_at,m.deleted_at,
                       u.name sender_name,u.role sender_role,
                       CASE WHEN m.sender_id=? THEN 1 ELSE 0 END AS sent_by_exporting_user
                FROM messages m
                JOIN users u ON u.id=m.sender_id
                WHERE m.conversation_id=?
                ORDER BY m.created_at,m.id
                """,
                (user_id, conversation_id),
            )
        )
    return {
        "conversations": conversations,
        "messages": messages,
        "notice": (
            "Conversation history contains messages already shared with this account. "
            "Other participants' email addresses and authentication data are not exported."
        ),
    }


def build_account_export(user: Any) -> dict:
    user_id = int(_value(user, "id", 0) or 0)
    if not user_id:
        raise PermissionError("Authentication is required.")

    account = _row(
        """
        SELECT id,name,email,email_normalized,role,phone,age,gender,city,
               emergency_contact,verified,active,created_at,updated_at
        FROM users WHERE id=? AND active=1
        """,
        (user_id,),
    )
    if not account:
        raise LookupError("Active account not found.")

    role = str(account["role"])
    payload = {
        "export_version": "zendoc-account-export-v2",
        "generated_at": now_iso(),
        "account": account,
        "email_verification": email_verification_status(account),
        "policy_acceptances": list_policy_acceptances(user_id),
        "communications": _conversation_export(user_id),
        "scope_notice": (
            "This export contains data owned by or already exposed to the authenticated account. "
            "It excludes passwords, API/reset tokens, secret keys, internal storage object keys, "
            "and administrative security configuration."
        ),
        "community_data": {
            "posts": _rows(
                "SELECT id,lane,body,media_type,media_url,media_mime_type,media_original_name,media_size_bytes,sponsorship_label,visibility,moderation_status,created_at,updated_at FROM health_social_posts WHERE author_id=? ORDER BY created_at,id",
                (user_id,),
            ),
            "stories": _rows(
                "SELECT id,lane,body,media_url,media_mime_type,media_original_name,media_size_bytes,moderation_status,created_at,expires_at FROM health_social_stories WHERE author_id=? ORDER BY created_at,id",
                (user_id,),
            ),
            "comments": _rows(
                "SELECT id,post_id,body,moderation_status,created_at FROM health_social_comments WHERE author_id=? ORDER BY created_at,id",
                (user_id,),
            ),
            "likes": _rows(
                "SELECT post_id,created_at FROM health_social_likes WHERE user_id=? ORDER BY created_at,post_id",
                (user_id,),
            ),
            "following": _rows(
                "SELECT followed_id,created_at FROM health_social_follows WHERE follower_id=? ORDER BY created_at,followed_id",
                (user_id,),
            ),
            "followers": _rows(
                "SELECT follower_id,created_at FROM health_social_follows WHERE followed_id=? ORDER BY created_at,follower_id",
                (user_id,),
            ),
            "blocked_accounts": _rows(
                "SELECT blocked_id,created_at FROM health_social_blocks WHERE blocker_id=? ORDER BY created_at,blocked_id",
                (user_id,),
            ),
            "reports_submitted": _rows(
                "SELECT id,entity_type,entity_id,reason,status,created_at FROM health_social_reports WHERE reporter_id=? ORDER BY created_at,id",
                (user_id,),
            ),
            "notice": "Community content is user-generated and is not exported as clinical evidence.",
        },
        "health_commerce_data": {
            "outbound_clicks": _rows(
                """
                SELECT click_uid,merchant_id,query_text,category,destination_url,affiliate_configured,created_at
                FROM health_commerce_clicks WHERE user_id=? ORDER BY created_at,id
                """,
                (user_id,),
            ),
            "notice": (
                "Outbound merchant records show searches/handoffs initiated from ZENDOC. "
                "They do not prove purchase, delivery or commission."
            ),
        },
        "payment_data": {
            "invoices": _rows(
                """
                SELECT id,invoice_uid,patient_id,payee_user_id,resource_type,resource_id,
                       amount_paise,currency,description,status,gateway,gateway_order_id,
                       gateway_payment_id,created_at,updated_at,paid_at
                FROM care_invoices
                WHERE patient_id=? OR payee_user_id=?
                ORDER BY created_at,id
                """,
                (user_id, user_id),
            ),
            "events": _rows(
                """
                SELECT pe.id,pe.invoice_id,pe.event_type,pe.provider_event_ref,
                       pe.signature_verified,pe.created_at
                FROM payment_events pe
                JOIN care_invoices i ON i.id=pe.invoice_id
                WHERE i.patient_id=? OR i.payee_user_id=?
                ORDER BY pe.created_at,pe.id
                """,
                (user_id, user_id),
            ),
            "notice": (
                "Payment export includes ZENDOC invoice and gateway reference metadata, "
                "not payment-provider secret credentials or raw signed webhook payloads."
            ),
        },
    }

    if role == "patient":
        payload["patient_data"] = {
            "health_profile": _row(
                "SELECT * FROM patient_health_profiles WHERE patient_id=?",
                (user_id,),
            ),
            "health_metrics": _rows(
                "SELECT * FROM health_metrics WHERE user_id=? ORDER BY recorded_at,id",
                (user_id,),
            ),
            "appointments": _rows(
                """
                SELECT id,provider_name,specialty,scheduled_for,reason,status,notes,created_at,updated_at
                FROM appointments WHERE patient_id=? ORDER BY scheduled_for,id
                """,
                (user_id,),
            ),
            "medical_records": _rows(
                """
                SELECT id,title,category,original_filename,mime_type,file_size,created_at
                FROM medical_records WHERE owner_id=? ORDER BY created_at,id
                """,
                (user_id,),
            ),
            "report_metadata": _rows(
                """
                SELECT rm.*
                FROM report_metadata rm
                JOIN medical_records mr ON mr.id=rm.record_id
                WHERE mr.owner_id=?
                ORDER BY rm.created_at,rm.id
                """,
                (user_id,),
            ),
            "report_results": _rows(
                """
                SELECT rr.*
                FROM report_results rr
                JOIN medical_records mr ON mr.id=rr.record_id
                WHERE mr.owner_id=?
                ORDER BY rr.measurement_date,rr.id
                """,
                (user_id,),
            ),
            "timeline": _rows(
                """
                SELECT id,event_type,event_at,title,summary,provider_name,source,source_ref,created_at
                FROM health_timeline_events
                WHERE patient_id=?
                ORDER BY event_at,id
                """,
                (user_id,),
            ),
            "health_access_grants": _rows(
                """
                SELECT id,provider_id,provider_profile_id,scopes,expires_at,revoked_at,created_at,updated_at
                FROM health_access_grants WHERE patient_id=? ORDER BY created_at,id
                """,
                (user_id,),
            ),
            "notifications": _rows(
                "SELECT id,title,message,channel,is_read,created_at FROM notifications WHERE user_id=? ORDER BY created_at,id",
                (user_id,),
            ),
            "ai_interactions": _rows(
                """
                SELECT id,conversation_id,feature,intent,input_text,output_text,risk_level,
                       model_version,provider,emergency,success,latency_ms,created_at
                FROM ai_interactions WHERE user_id=? ORDER BY created_at,id
                """,
                (user_id,),
            ),
            "ai_conversations": _rows(
                "SELECT id,title,last_intent,created_at,updated_at FROM ai_conversations WHERE user_id=? ORDER BY created_at,id",
                (user_id,),
            ),
            "fitness_profile": _row("SELECT * FROM fitness_profiles WHERE user_id=?", (user_id,)),
            "workout_plans": _rows("SELECT * FROM workout_plans WHERE user_id=? ORDER BY created_at,id", (user_id,)),
            "workout_sessions": _rows("SELECT * FROM workout_sessions WHERE user_id=? ORDER BY started_at,id", (user_id,)),
            "nutrition_logs": _rows("SELECT * FROM nutrition_logs WHERE user_id=? ORDER BY logged_at,id", (user_id,)),
            "hydration_logs": _rows("SELECT * FROM hydration_logs WHERE user_id=? ORDER BY logged_at,id", (user_id,)),
            "family_members": _rows("SELECT * FROM family_members WHERE user_id=? ORDER BY created_at,id", (user_id,)),
            "family_care_tasks": _rows("SELECT * FROM family_care_tasks WHERE user_id=? ORDER BY created_at,id", (user_id,)),
            "saved_locations": _rows("SELECT * FROM saved_locations WHERE user_id=? ORDER BY created_at,id", (user_id,)),
            "health_devices": _rows("SELECT * FROM health_devices WHERE user_id=? ORDER BY created_at,id", (user_id,)),
            "home_health_requests": _rows(
                "SELECT * FROM home_health_requests WHERE patient_id=? ORDER BY created_at,id",
                (user_id,),
            ),
            "ambulance_requests": _rows(
                "SELECT * FROM ambulance_requests WHERE patient_id=? ORDER BY created_at,id",
                (user_id,),
            ),
            "medicine_orders": _rows(
                "SELECT * FROM medicine_orders WHERE patient_id=? ORDER BY created_at,id",
                (user_id,),
            ),
            "medicine_reminders": _rows(
                "SELECT * FROM medicine_reminders WHERE user_id=? ORDER BY created_at,id",
                (user_id,),
            ),
            "consultations": _rows(
                """
                SELECT id,doctor_id,appointment_id,consultation_type,status,reason,scheduled_for,created_at,updated_at
                FROM consultation_requests WHERE patient_id=? ORDER BY created_at,id
                """,
                (user_id,),
            ),
        }
    elif role in {"doctor", "hospital", "pharmacy"}:
        profile = _row("SELECT * FROM provider_profiles WHERE user_id=?", (user_id,))
        profile_id = int(profile["id"]) if profile else None
        payload["provider_data"] = {
            "profile": profile,
            "schedules": (
                _rows(
                    "SELECT * FROM provider_schedules WHERE provider_profile_id=? ORDER BY weekday,start_time,id",
                    (profile_id,),
                )
                if profile_id
                else []
            ),
            "doctor_availability": _row(
                "SELECT * FROM doctor_availability WHERE doctor_id=?",
                (user_id,),
            ),
            "consultation_metadata": _rows(
                """
                SELECT id,consultation_type,status,scheduled_for,created_at,updated_at
                FROM consultation_requests WHERE doctor_id=? ORDER BY created_at,id
                """,
                (user_id,),
            ),
            "notice": (
                "Provider export omits patient consultation reasons and patient-owned medical records. "
                "Those belong to the patient and are not copied into a provider portability export."
            ),
        }

    return payload
