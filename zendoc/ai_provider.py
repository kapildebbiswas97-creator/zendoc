import os


class ProviderResponse:
    def __init__(self, text, provider="local_fallback", success=True):
        self.text = text
        self.provider = provider
        self.success = success


class AIProvider:
    name = "base"

    def complete(self, message, context):
        raise NotImplementedError


class LocalFallbackProvider(AIProvider):
    name = "local_fallback"

    def complete(self, message, context):
        intent = context.get("intent", "general_assistant")
        if intent == "symptoms":
            return ProviderResponse(
                "I can help you think through this safely. These symptoms can have several causes, and I cannot confirm a diagnosis. A few details will help: how long has this been happening, how severe is it, and are there any other symptoms?",
                self.name,
            )
        if intent == "mental_wellness":
            return ProviderResponse(
                "I am sorry you are dealing with that. We can look at stress, sleep, support, and next steps together. If you feel unsafe or at risk of self-harm, seek urgent help immediately.",
                self.name,
            )
        return ProviderResponse(
            "I can guide you to the right ZENDOC service and suggest safe next steps. Tell me what is happening or what you want to do.",
            self.name,
        )


class ExternalProviderPlaceholder(AIProvider):
    name = "external_placeholder"

    def complete(self, message, context):
        # Credentials and live provider integration belong in environment-backed adapters.
        raise RuntimeError("External AI provider is not configured.")


def configured_provider():
    provider = os.environ.get("ZENDOC_AI_PROVIDER", "local").lower()
    if provider in {"openai", "gemini", "claude", "local_model"}:
        return ExternalProviderPlaceholder()
    return LocalFallbackProvider()
