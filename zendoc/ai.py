MODEL_VERSION = "rules-engine-v1-ready-for-ml"

from .safety import SafetyEngine


def doctor_prediction(symptoms):
    """Legacy compatibility entry point for non-diagnostic symptom guidance.

    Despite the historical function/route name, this function does not diagnose,
    prescribe, recommend medicine changes, or claim a likely condition. It only
    provides a bounded urgency level and safe next-step guidance.
    """
    text = (symptoms or "").lower()
    safety = SafetyEngine().assess(text)
    if safety["emergency"]:
        return {
            "summary": safety["reason"],
            "risk_level": "high",
            "next_steps": safety["guidance"],
            "emergency": True,
            "scope": "non_diagnostic_symptom_guidance",
            "diagnosis": None,
            "prescription": None,
            "medication_change": None,
        }

    rules = [
        (
            ("fever", "cough"),
            "Fever together with cough can have many causes and may need clinical assessment, especially if symptoms persist or worsen.",
            "medium",
        ),
        (
            ("headache", "nausea"),
            "Headache together with nausea can have several causes. Hydration, duration, severity, and other symptoms matter for a clinician's assessment.",
            "medium",
        ),
        (
            ("rash", "itch"),
            "An itchy rash can have many causes. Avoid guessing the cause from symptoms alone and seek clinical review if it is spreading, severe, or persistent.",
            "low",
        ),
        (
            ("fatigue", "thirst"),
            "Fatigue together with increased thirst deserves attention if it persists. A clinician may need history, examination, or tests to understand the cause.",
            "medium",
        ),
        (
            ("stress", "insomnia"),
            "Stress and poor sleep can affect wellbeing. If either is persistent, severe, or affecting daily function, consider professional support.",
            "medium",
        ),
    ]
    for keywords, summary, risk in rules:
        if all(keyword in text for keyword in keywords):
            return {
                "summary": summary,
                "risk_level": risk,
                "next_steps": "Consider booking a qualified clinician for assessment. ZENDOC does not diagnose conditions from symptoms.",
                "emergency": False,
                "scope": "non_diagnostic_symptom_guidance",
                "diagnosis": None,
                "prescription": None,
                "medication_change": None,
            }
    return {
        "summary": "More information is required for useful non-diagnostic guidance.",
        "risk_level": "low",
        "next_steps": (
            "If symptoms concern you, add duration and severity for context and consider a qualified clinician. "
            "ZENDOC does not diagnose conditions from symptoms."
        ),
        "emergency": False,
        "scope": "non_diagnostic_symptom_guidance",
        "diagnosis": None,
        "prescription": None,
        "medication_change": None,
    }


def assistant_answer(message):
    """Small deterministic navigation helper used by the legacy guided-tool form.

    This helper intentionally does not make clinical decisions or claim that an
    external partner action happened. The main ZENDOC AI path uses
    ``ZendocIntelligence`` and the governed model/tool routing layer.
    """
    text = message or ""
    safety = SafetyEngine().assess(text)
    if safety["emergency"]:
        return f"{safety['reason']} {safety['guidance']}"

    text = text.lower()
    if "appointment" in text or "doctor" in text:
        return (
            "Open Find Care to review currently available provider records and request a visit. "
            "A request is not a confirmed appointment until ZENDOC shows a confirmed status."
        )
    if "report" in text or "record" in text:
        return (
            "Open Records & reports to upload or review supported files. ZENDOC keeps source and "
            "access boundaries visible and does not treat an uploaded document as clinician-verified by default."
        )
    if "medicine" in text or "pharmacy" in text:
        return (
            "Open Pharmacy to search ZENDOC's current records and use the available medicine fulfilment workflow. "
            "Stock, price, delivery, and external partner execution are shown only when they are actually confirmed; "
            "otherwise ZENDOC keeps the request pending or marks the integration as required."
        )
    if "ambulance" in text or "emergency" in text:
        return (
            "For emergencies, contact local emergency services immediately. ZENDOC can provide guidance and "
            "workflow status, but it does not claim an ambulance was dispatched unless a real connected provider confirms it."
        )
    if "ai" in text or "model" in text:
        return (
            "ZENDOC AI uses deterministic safety checks plus governed local or configured model routes. "
            "AI can suggest actions, but server-side permissions, consent, approvals, and audit controls decide what can run."
        )
    return (
        "I can guide you to appointments, records, health monitoring, symptom guidance, pharmacy workflows, "
        "and account navigation. For clinical decisions, use a qualified healthcare professional."
    )


def mental_health_support(age_group, context, stress_level):
    safety = SafetyEngine().assess(context or "")
    if safety["emergency"]:
        return {
            "summary": safety["reason"],
            "risk_level": "high",
            "next_steps": safety["guidance"],
            "emergency": True,
        }
    try:
        stress = max(0, min(10, int(stress_level)))
    except (TypeError, ValueError):
        stress = 0
    if stress >= 8:
        risk = "high"
        advice = "Your stress score is high. Contact a trusted person or licensed professional today."
    elif stress >= 5:
        risk = "medium"
        advice = "Your stress score is moderate. Try a short break, hydration, sleep hygiene, and scheduled support."
    else:
        risk = "low"
        advice = "Your stress score is low. Keep monitoring sleep, mood, and routine."
    return {
        "summary": f"{age_group.title()} support: {advice}",
        "risk_level": risk,
        "next_steps": f"Context noted: {context or 'general wellbeing'}.",
    }
