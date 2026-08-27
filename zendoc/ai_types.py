from dataclasses import dataclass, field


@dataclass
class IntelligenceResult:
    intent: str
    urgency: str
    message: str
    follow_up_questions: list[str] = field(default_factory=list)
    possible_actions: list[dict] = field(default_factory=list)
    specialist: str | None = None
    emergency: bool = False
    provider: str = "local"
    success: bool = True
    conversation_id: str | None = None
    next_step: str | None = None

    def to_dict(self):
        return {
            "intent": self.intent,
            "urgency": self.urgency,
            "message": self.message,
            "follow_up_questions": self.follow_up_questions,
            "possible_actions": self.possible_actions,
            "specialist": self.specialist,
            "emergency": self.emergency,
            "provider": self.provider,
            "success": self.success,
            "conversation_id": self.conversation_id,
            "next_step": self.next_step,
        }
