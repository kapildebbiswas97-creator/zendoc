"""
ZENDOC Capability Registry — Milestone 8
Central truthful registry of platform capabilities.

Statuses: WORKING | BETA | INTEGRATION_REQUIRED | DISABLED | FUTURE
"""
from __future__ import annotations

import os


STATUS_WORKING              = "WORKING"
STATUS_BETA                 = "BETA"
STATUS_INTEGRATION_REQUIRED = "INTEGRATION_REQUIRED"
STATUS_DISABLED             = "DISABLED"
STATUS_FUTURE               = "FUTURE"


def _env(key: str, default: str = "") -> str:
    return (os.environ.get(key) or default).strip()


def _env_bool(key: str, default: bool = False) -> bool:
    val = os.environ.get(key)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _local_ai_env(new_key: str, legacy_key: str, default: str = "") -> str:
    value = os.environ.get(new_key)
    if value is not None:
        return value.strip()
    return _env(legacy_key, default)


def _local_ai_enabled() -> bool:
    if "ZENDOC_LOCAL_AI_ENABLED" in os.environ:
        return _env_bool("ZENDOC_LOCAL_AI_ENABLED")
    return _env_bool("ZENDOC_SLM_ENABLED")


def get_capability_registry() -> dict:
    """
    Returns the complete truthful capability matrix.
    Used by the Command Center, API, and capability status endpoint.
    """
    local_ai_provider = _local_ai_env("ZENDOC_LOCAL_AI_PROVIDER", "ZENDOC_SLM_PROVIDER", "ollama").lower()
    local_ai_configured = (
        _local_ai_enabled()
        and local_ai_provider in {"ollama", "openai_compatible"}
        and bool(_local_ai_env("ZENDOC_LOCAL_AI_MODEL", "ZENDOC_SLM_MODEL"))
    )
    cloud_llm = bool(
        _env("ZENDOC_AI_PROVIDER") in {"openai", "openai_compatible"} and _env("ZENDOC_AI_API_KEY")
        and _env("ZENDOC_AI_MODEL")
        and (_env("ZENDOC_AI_BASE_URL") or _env("ZENDOC_AI_PROVIDER") == "openai")
    )
    places = _env("ZENDOC_PLACES_PROVIDER", "none") not in {"", "none"}
    video_provider = _env("ZENDOC_VIDEO_PROVIDER", "none") not in {"", "none"}
    database_url = bool(_env("DATABASE_URL"))
    storage_provider = _env("ZENDOC_STORAGE_PROVIDER", "local")
    s3_configured = storage_provider != "local" and bool(_env("ZENDOC_STORAGE_BUCKET"))

    return {
        # Core platform
        "zendoc_core_agent": {
            "status": STATUS_WORKING,
            "label": "ZENDOC Core Agent",
            "description": "Permissioned agent with tool registry, audit trail, safety gate.",
        },
        "connect_messaging": {
            "status": STATUS_WORKING,
            "label": "ZENDOC Connect Messaging",
            "description": "Policy-aware messaging, conversations, read receipts, report/video sharing.",
        },
        "deterministic_safety_engine": {
            "status": STATUS_WORKING,
            "label": "Deterministic Safety Engine",
            "description": "Emergency detection — always first, never routed to LLM.",
        },
        "local_slm": {
            "status": STATUS_BETA if local_ai_configured else STATUS_INTEGRATION_REQUIRED,
            "label": "Local SLM (Small Language Model)",
            "description": "Local inference is configured; owner runtime health verifies server and model readiness."
                           if local_ai_configured else
                           "Local SLM integration ready — model not configured.",
        },
        "cloud_llm": {
            "status": STATUS_BETA if cloud_llm else STATUS_INTEGRATION_REQUIRED,
            "label": "Cloud LLM Provider",
            "description": "External AI provider (ZENDOC_AI_PROVIDER + ZENDOC_AI_API_KEY)."
                           if not cloud_llm else
                           f"Configured: {_env('ZENDOC_AI_PROVIDER')}",
        },
        "model_router": {
            "status": STATUS_WORKING,
            "label": "Model Router",
            "description": "Routes tasks by safety, privacy, risk, complexity, and explicit cloud approval; model output cannot invoke tools.",
        },
        "agent_task_engine": {
            "status": STATUS_WORKING,
            "label": "Agent Task Engine",
            "description": "Persistent tasks with retry, idempotency, bounded execution.",
        },
        "approval_engine": {
            "status": STATUS_WORKING,
            "label": "Human Approval Engine",
            "description": "Owner-level and doctor-level human-in-the-loop approvals.",
        },
        "proactive_alerts": {
            "status": STATUS_WORKING,
            "label": "Proactive Operational Alerts",
            "description": "Deterministic monitoring: overdue tasks, high error rates, waiting approvals.",
        },
        "capability_registry": {
            "status": STATUS_WORKING,
            "label": "Capability Registry",
            "description": "Central truthful status for all platform features.",
        },

        # Health & Clinical
        "health_memory": {
            "status": STATUS_WORKING,
            "label": "Health Memory & Timeline",
            "description": "Secure personal health profile, records, timeline, analytics.",
        },
        "medical_records": {
            "status": STATUS_WORKING,
            "label": "Medical Records Upload",
            "description": "Provider-backed storage interface; secure local storage is working for development.",
        },
        "appointments": {
            "status": STATUS_WORKING,
            "label": "Appointments",
            "description": "Provider scheduling, slot booking, provider profiles.",
        },
        "telehealth": {
            "status": STATUS_BETA,
            "label": "Telehealth Beta",
            "description": "Consultation requests, doctor acceptance, chat. Local demo only — production WebRTC provider required.",
        },
        "report_intelligence": {
            "status": STATUS_BETA,
            "label": "Report Intelligence",
            "description": "Deterministic blood test range interpretation. Not a medical diagnosis.",
        },

        # Fitness
        "fitness_coach": {
            "status": STATUS_WORKING,
            "label": "AI Fitness Coach",
            "description": "Workout plans, session tracking, exercise library, nutrition/hydration logs.",
        },
        "pose_coach": {
            "status": STATUS_BETA,
            "label": "AI Pose Coach (Camera)",
            "description": "Camera-based form feedback via MediaPipe. Beta — not a medical device.",
        },
        "fitness_videos": {
            "status": STATUS_WORKING,
            "label": "Fitness Video Library",
            "description": "Local exercise library with guidance cards.",
        },

        # Operations
        "human_operations": {
            "status": STATUS_WORKING,
            "label": "Human Operations",
            "description": "Staff task management, status tracking (requested → completed).",
        },
        "family_care": {
            "status": STATUS_WORKING,
            "label": "Family Care",
            "description": "Remote parent care, family access grants, care tasks.",
        },
        "home_health": {
            "status": STATUS_WORKING,
            "label": "Home Healthcare",
            "description": "Service intake (actual fulfillment requires provider integration).",
        },
        "pharmacy": {
            "status": STATUS_WORKING,
            "label": "Pharmacy Services",
            "description": "Medicine search, delivery requests. Live dispensing requires pharmacy integration.",
        },
        "medical_transport": {
            "status": STATUS_WORKING,
            "label": "Medical Transport",
            "description": "Transport request intake. Live dispatch requires provider integration.",
        },
        "iot_hub": {
            "status": STATUS_BETA,
            "label": "IoT Hub",
            "description": "Manual device registration and measurement logging. Live sync requires device SDK.",
        },

        # External integrations
        "healthcare_finder": {
            "status": STATUS_WORKING if places else STATUS_BETA,
            "label": "Healthcare Finder",
            "description": "Provider search via places API." if places else "Local provider directory — real places API not configured.",
        },
        "video_intelligence": {
            "status": STATUS_WORKING if video_provider else STATUS_BETA,
            "label": "Video Intelligence",
            "description": "Educational video search." if video_provider else "General ZENDOC guidance cards — video provider not configured.",
        },
        "external_notifications": {
            "status": STATUS_INTEGRATION_REQUIRED,
            "label": "External Notifications (Email/SMS/WhatsApp/Push)",
            "description": "Configure ZENDOC_EMAIL_PROVIDER, ZENDOC_SMS_PROVIDER for real delivery.",
        },
        "in_app_notifications": {
            "status": STATUS_WORKING,
            "label": "In-App Notifications",
            "description": "Working — delivered to user notification feed.",
        },

        # Infrastructure
        "postgresql": {
            "status": STATUS_INTEGRATION_REQUIRED,
            "label": "PostgreSQL Database",
            "description": "Configure DATABASE_URL for production database."
                           if not database_url else
                           "DATABASE_URL is present, but the PostgreSQL driver and production migration run are still required.",
        },
        "object_storage": {
            "status": STATUS_INTEGRATION_REQUIRED if s3_configured else STATUS_WORKING,
            "label": "Object Storage (S3-compatible)",
            "description": "Local file storage (development)."
                           if not s3_configured else
                           f"Provider '{storage_provider}' is configured but its external adapter must be installed and tested.",
        },
        "realtime": {
            "status": STATUS_WORKING,
            "label": "Real-time Updates",
            "description": "Authenticated incremental event polling is working. WebSocket/SSE delivery requires an external adapter.",
        },

        # Future
        "zendoc_proprietary_slm": {
            "status": STATUS_FUTURE,
            "label": "ZENDOC Proprietary SLM (Future)",
            "description": "ZENDOC has NOT trained a proprietary medical SLM yet. Infrastructure is ready for future fine-tuning.",
        },
        "autonomous_prescribing": {
            "status": STATUS_FUTURE,
            "label": "Autonomous Prescribing (Future, Legally Restricted)",
            "description": "CRITICAL_BLOCKED — requires legally valid doctor workflow and regulatory approval.",
        },
    }


def get_capability_status(capability_key: str) -> dict | None:
    """Get status for a single capability."""
    registry = get_capability_registry()
    return registry.get(capability_key)
