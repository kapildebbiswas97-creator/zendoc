RED_FLAGS = {
    "chest pain": "Chest pain can be serious and needs urgent medical evaluation.",
    "shortness of breath": "Breathing difficulty can become dangerous quickly.",
    "severe bleeding": "Severe bleeding needs urgent care.",
    "stroke": "Possible stroke symptoms need emergency care immediately.",
    "fainting": "Fainting with concerning symptoms should be urgently evaluated.",
    "suicide": "If you may harm yourself, seek immediate crisis support or emergency care.",
    "kill myself": "If you may harm yourself, seek immediate crisis support or emergency care.",
}


class SafetyEngine:
    def assess(self, message):
        text = (message or "").lower()
        for phrase, reason in RED_FLAGS.items():
            if phrase in text:
                return {
                    "emergency": True,
                    "urgency": "emergency",
                    "reason": reason,
                    "matched": phrase,
                    "guidance": "Please contact local emergency services or go to the nearest emergency department now. Do not wait for an AI chat if symptoms feel severe or rapidly worsening.",
                }
        return {"emergency": False, "urgency": "routine", "reason": None, "matched": None, "guidance": None}
