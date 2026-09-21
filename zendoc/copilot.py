"""Context-aware UI metadata for the ZENDOC Copilot.

This module does not execute models or tools. It tells the global shell which
safe AI/Agent OS entry points are relevant to the page the authenticated user is
already viewing. Consequential actions remain behind their existing server-side
authorization and human-confirmation gates.
"""
from __future__ import annotations


def _matches(endpoint: str, *prefixes: str) -> bool:
    return any(endpoint == prefix or endpoint.startswith(prefix + ".") for prefix in prefixes)


def copilot_context(endpoint: str | None, role: str | None) -> dict | None:
    endpoint = str(endpoint or "")
    role = str(role or "").strip().lower()

    if not role:
        return None

    # Owner/provider workspaces keep operational AI separate from the
    # patient-facing health copilot.
    if role == "admin":
        return {
            "key": "operations",
            "title": "Operations Copilot",
            "eyebrow": "Owner AI",
            "description": "Review platform state, failed operations and bounded Agent OS maintenance.",
            "prompts": [
                "Summarize the platform status and what needs attention.",
                "Explain recent failures without changing anything.",
                "What should I verify before the next production release?",
            ],
            "agent_command": "Show the platform health summary and what needs attention today",
            "actions": [
                {"label": "Agent Center", "endpoint": "milestone7.admin_agent_command_center"},
                {"label": "Operations", "endpoint": "milestone7.operations_page"},
            ],
        }

    if role in {"doctor", "hospital", "pharmacy"}:
        if _matches(endpoint, "milestone7.messages_page", "calls"):
            return {
                "key": "provider_connect",
                "title": "Care Communication Copilot",
                "eyebrow": "Provider AI",
                "description": "Draft clearer patient communication while permissions and clinical authority remain server-controlled.",
                "prompts": [
                    "Help me write a clear follow-up message for a patient.",
                    "Summarize what information I should ask the patient to provide.",
                    "Rewrite this message in simpler language.",
                ],
                "agent_command": "Show my unread messages",
                "actions": [{"label": "Messages", "endpoint": "milestone7.messages_page"}],
            }
        return {
            "key": "provider_workspace",
            "title": "Provider Copilot",
            "eyebrow": "Provider AI",
            "description": "Navigate appointments, communication and operational work without bypassing verification or consent.",
            "prompts": [
                "Help me organize today's provider workflow.",
                "Explain what needs attention in my workspace.",
                "Help me draft a patient-friendly explanation.",
            ],
            "agent_command": "Show my unread messages",
            "actions": [
                {"label": "Appointments", "endpoint": "main.appointments"},
                {"label": "Messages", "endpoint": "milestone7.messages_page"},
            ],
        }

    # Patient contexts.
    if _matches(endpoint, "main.finder", "universal_search.search_home", "main.provider_detail"):
        return {
            "key": "find_care",
            "title": "Care Search Copilot",
            "eyebrow": "AI-assisted discovery",
            "description": "Help narrow the right care type, understand search results, and prepare the next safe step.",
            "prompts": [
                "What type of doctor should I search for based on my concern?",
                "Help me compare these care options without assuming they are verified.",
                "What should I prepare before contacting a hospital or clinic?",
            ],
            "agent_command": "Find nearby healthcare providers and explain which results are ZENDOC verified",
            "actions": [
                {"label": "Find Care", "endpoint": "universal_search.search_home"},
                {"label": "Appointments", "endpoint": "main.appointments"},
            ],
        }

    if _matches(endpoint, "health_memory", "main.records", "main.reports"):
        return {
            "key": "health_memory",
            "title": "Health Memory Copilot",
            "eyebrow": "Longitudinal AI",
            "description": "Organize your authorized Health Memory, explain records, and identify safe follow-up questions.",
            "prompts": [
                "Summarize the important points in my recent Health Memory.",
                "Help me prepare questions about my latest report.",
                "Explain the difference between patient-reported and provider-confirmed records.",
            ],
            "agent_command": "Review my health records and show the next safe non-clinical actions",
            "actions": [
                {"label": "Timeline", "endpoint": "health_memory.timeline_page"},
                {"label": "Health Summary", "endpoint": "health_memory.health_summary_page"},
            ],
        }

    if endpoint == "main.appointments":
        return {
            "key": "appointments",
            "title": "Appointment Copilot",
            "eyebrow": "Care planning AI",
            "description": "Prepare for visits, organize questions, and use Agent OS for bounded appointment workflows.",
            "prompts": [
                "Help me prepare for my next appointment.",
                "What information should I bring to this visit?",
                "Help me write questions I should ask the provider.",
            ],
            "agent_command": "Help me find an appointment with an appropriate verified connected provider",
            "actions": [
                {"label": "Find Care", "endpoint": "universal_search.search_home"},
                {"label": "Care Journey", "endpoint": "connected_care.care_journey_page"},
            ],
        }

    if _matches(endpoint, "milestone7.messages_page", "calls"):
        return {
            "key": "connect",
            "title": "Connect Copilot",
            "eyebrow": "Communication AI",
            "description": "Draft clearer messages, summarize what you want to ask, and keep communication permissions explicit.",
            "prompts": [
                "Help me write a concise message to my care team.",
                "Turn my notes into three clear questions for the provider.",
                "Rewrite my message in simple English.",
            ],
            "agent_command": "Show my unread messages",
            "actions": [{"label": "Messages", "endpoint": "milestone7.messages_page"}],
        }

    if _matches(endpoint, "mental_wellness"):
        return {
            "key": "mental_wellness",
            "title": "Wellness Copilot",
            "eyebrow": "Private reflection AI",
            "description": "Organize thoughts and wellbeing routines without presenting a diagnosis or clinical assessment.",
            "prompts": [
                "Help me turn what I am feeling into a simple journal entry.",
                "Suggest a short age-appropriate wellbeing routine for today.",
                "Help me identify what I want to talk about with a trusted person.",
            ],
            "agent_command": None,
            "actions": [{"label": "Mental Wellness", "endpoint": "mental_wellness.mental_wellness_page"}],
        }

    if _matches(endpoint, "family"):
        return {
            "key": "family",
            "title": "Family Care Copilot",
            "eyebrow": "Family coordination AI",
            "description": "Organize family-care tasks while preserving each person's consent and record boundaries.",
            "prompts": [
                "Help me organize care tasks for my family.",
                "Create a checklist for an older family member's next appointment.",
                "Explain what I can and cannot access without their consent.",
            ],
            "agent_command": "Help me organize family care and the next safe steps",
            "actions": [{"label": "Family Care", "endpoint": "family.family_page"}],
        }

    if _matches(endpoint, "fitness"):
        return {
            "key": "fitness",
            "title": "Fitness Copilot",
            "eyebrow": "Everyday coaching AI",
            "description": "Turn your goals into manageable fitness, hydration and nutrition tasks using the data you choose to provide.",
            "prompts": [
                "Build a simple workout plan for my current goal.",
                "Help me improve my hydration routine.",
                "Summarize my fitness progress and suggest the next small step.",
            ],
            "agent_command": None,
            "actions": [{"label": "Fitness Hub", "endpoint": "fitness.overview"}],
        }

    if _matches(endpoint, "health_social"):
        return {
            "key": "community",
            "title": "Community Copilot",
            "eyebrow": "Creation assistant",
            "description": "Help draft useful health-community posts and captions while keeping public sharing separate from private health records.",
            "prompts": [
                "Help me draft a helpful health-community post.",
                "Rewrite my caption so it is clear and respectful.",
                "Turn this idea into a short educational post without medical claims.",
            ],
            "agent_command": None,
            "actions": [{"label": "Community", "endpoint": "health_social.community_page"}],
        }

    if _matches(endpoint, "health_shop"):
        return {
            "key": "health_shop",
            "title": "Shopping Copilot",
            "eyebrow": "Commerce guidance AI",
            "description": "Clarify product categories and comparison questions without turning merchant listings into clinical recommendations.",
            "prompts": [
                "Help me compare what to look for in a home health device.",
                "What questions should I ask before buying a wellness product?",
                "Explain why medicine searches are handled differently from general shopping.",
            ],
            "agent_command": None,
            "actions": [{"label": "Health Shop", "endpoint": "health_shop.health_shop_page"}],
        }

    if _matches(endpoint, "payments"):
        return {
            "key": "payments",
            "title": "Payment Copilot",
            "eyebrow": "Invoice explainer",
            "description": "Explain invoice and gateway states without claiming a payment succeeded before verified evidence exists.",
            "prompts": [
                "Explain the status of my invoice in simple words.",
                "What is the difference between checkout verified and payment confirmed?",
                "What should I verify before paying a healthcare invoice?",
            ],
            "agent_command": None,
            "actions": [{"label": "Payments", "endpoint": "payments.payments_page"}],
        }

    if _matches(endpoint, "connected_care", "care_journey"):
        return {
            "key": "connected_care",
            "title": "Care Journey Copilot",
            "eyebrow": "Continuity AI",
            "description": "Understand what happened, what is confirmed, and what safe step comes next across your care journey.",
            "prompts": [
                "Summarize my current care journey.",
                "What is confirmed versus still waiting for provider action?",
                "Help me prepare for the next follow-up step.",
            ],
            "agent_command": "Review my care journey and show the next safe action",
            "actions": [{"label": "Care Journey", "endpoint": "connected_care.care_journey_page"}],
        }

    if _matches(endpoint, "carefin"):
        return {
            "key": "carefin",
            "title": "Benefits Copilot",
            "eyebrow": "Financial navigation AI",
            "description": "Discover possible support pathways without claiming eligibility, approval or payment.",
            "prompts": [
                "Explain what information I need to check healthcare benefits.",
                "Help me understand a government health scheme.",
                "What should I verify before relying on a benefit?",
            ],
            "agent_command": "Find possible government schemes, insurance benefits or financial support for healthcare",
            "actions": [{"label": "CareFin", "endpoint": "carefin.carefin_page"}],
        }

    if _matches(endpoint, "connected_care.diagnostics_page"):
        return {
            "key": "diagnostics",
            "title": "Diagnostics Copilot",
            "eyebrow": "Test navigation AI",
            "description": "Help understand test workflows and availability states without interpreting results as a diagnosis.",
            "prompts": [
                "Explain what I should prepare for before a diagnostic test.",
                "Help me understand the availability status shown here.",
                "What questions should I ask the diagnostic provider?",
            ],
            "agent_command": "Find diagnostic options and show only truthful availability states",
            "actions": [{"label": "Diagnostics", "endpoint": "connected_care.diagnostics_page"}],
        }

    if _matches(endpoint, "ecosystem.pharmacy_page", "pharmacy_order_ops"):
        return {
            "key": "pharmacy",
            "title": "Pharmacy Copilot",
            "eyebrow": "Medicine workflow AI",
            "description": "Organize medicine questions and availability checks without prescribing, substituting or changing medicines.",
            "prompts": [
                "Help me organize questions about my prescription.",
                "Explain what information a pharmacy may need from me.",
                "Why can ZENDOC not automatically substitute a medicine?",
            ],
            "agent_command": "Find prescribed medicine availability through truthful pharmacy inventory",
            "actions": [{"label": "Pharmacy", "endpoint": "ecosystem.pharmacy_page"}],
        }

    if _matches(endpoint, "ecosystem.iot_hub_page", "personal_health_baseline", "preventive_care"):
        return {
            "key": "monitoring",
            "title": "Health Monitoring Copilot",
            "eyebrow": "Personal health AI",
            "description": "Organize measurements, trends and preventive tasks while keeping device provenance and user-reported data explicit.",
            "prompts": [
                "Help me understand how to track my measurements consistently.",
                "Summarize the trend I should discuss with a clinician.",
                "Create a simple preventive-care checklist.",
            ],
            "agent_command": "Show my connected device records and health monitoring status",
            "actions": [{"label": "Connected Devices", "endpoint": "ecosystem.iot_hub_page"}],
        }

    if endpoint == "main.dashboard":
        return {
            "key": "dashboard",
            "title": "ZENDOC Copilot",
            "eyebrow": "AI command layer",
            "description": "One place to understand what needs attention and jump into the right care, memory or wellness workflow.",
            "prompts": [
                "What should I focus on in ZENDOC today?",
                "Help me organize my health tasks for this week.",
                "Show me how ZENDOC can help with my current goal.",
            ],
            "agent_command": "Review my health records and show the next safe non-clinical actions",
            "actions": [
                {"label": "Care OS", "endpoint": "care_os.care_os_home"},
                {"label": "Health Memory", "endpoint": "health_memory.health_summary_page"},
                {"label": "Find Care", "endpoint": "universal_search.search_home"},
            ],
        }

    # Generic patient fallback so every authenticated patient page has a useful
    # AI entry point even before a more specific context is added.
    return {
        "key": "general",
        "title": "ZENDOC Copilot",
        "eyebrow": "Context-aware AI",
        "description": "Ask for help with this part of ZENDOC or hand off a supported workflow to Agent OS.",
        "prompts": [
            "Explain what I can do on this page.",
            "Help me choose the next useful action.",
            "Summarize this feature in simple language.",
        ],
        "agent_command": None,
        "actions": [
            {"label": "ZENDOC AI", "endpoint": "ai_chat.chat_home"},
            {"label": "Agent OS", "endpoint": "specialist_agents.agent_os_page"},
        ],
    }
