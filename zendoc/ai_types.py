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
    summary: str | None = None
    guidance: str | None = None
    recommended_actions: list[dict] = field(default_factory=list)
    provider_route: dict = field(default_factory=dict)
    safety_notice: str | None = None
    model_metadata: dict = field(default_factory=dict)

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
            "summary": self.summary or self.message,
            "guidance": self.guidance or self.message,
            "recommended_actions": self.recommended_actions or self.possible_actions,
            "provider_route": dict(self.provider_route),
            "safety_notice": self.safety_notice or "Educational guidance only. ZENDOC does not diagnose or prescribe.",
            "model_metadata": dict(self.model_metadata),
        }
