MODEL_VERSION = "rules-engine-v1-ready-for-ml"

from .safety import SafetyEngine


def doctor_prediction(symptoms):
    text = (symptoms or "").lower()
    safety = SafetyEngine().assess(text)
    if safety["emergency"]:
        return {
            "summary": safety["reason"],
            "risk_level": "high",
            "next_steps": safety["guidance"],
            "emergency": True,
        }

    rules = [
        (("fever", "cough"), "Possible respiratory infection", "medium"),
        (("headache", "nausea"), "Possible migraine, dehydration, or infection", "medium"),
        (("rash", "itch"), "Possible allergy or skin condition", "low"),
        (("fatigue", "thirst"), "Possible metabolic, hydration, or lifestyle concern", "medium"),
        (("stress", "insomnia"), "Possible stress-related sleep disturbance", "medium"),
    ]
    for keywords, summary, risk in rules:
        if all(keyword in text for keyword in keywords):
            return {
                "summary": summary,
                "risk_level": risk,
                "next_steps": "Book a consultation and upload any recent reports for review.",
            }
    return {
        "summary": "More information is required for a useful prediction.",
        "risk_level": "low",
        "next_steps": "Add duration, severity, age, medications, and existing conditions.",
    }


def assistant_answer(message):
    text = (message or "").lower()
    if "appointment" in text:
        return "Open Appointments to request a visit, then track status from your dashboard."
    if "report" in text or "record" in text:
        return "Open Medical Records to upload or download PDF, image, DOC, DOCX, or TXT files."
    if "medicine" in text or "pharmacy" in text:
        return "Medicine delivery is planned for a future phase. Pharmacy users can already register."
    if "emergency" in text:
        return "For emergencies, use local emergency services immediately. ZENDOC is not a replacement for urgent care."
    return "I can guide appointments, medical records, health monitoring, symptom guidance, and account navigation."


def mental_health_support(age_group, context, stress_level):
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
