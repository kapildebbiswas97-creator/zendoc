"""Deterministic emergency safety gate.

This layer runs before intent routing, language models, or agent planning.  It
uses conservative phrase matching and a small negation guard so routine
statements such as "I do not have chest pain" do not trigger by themselves.

It is deliberately not a diagnostic engine.
"""
from __future__ import annotations

import re


EMERGENCY_RULES = (
    {
        "category": "cardiac",
        "phrases": ("chest pain", "crushing chest pressure", "severe chest pressure", "severe chest tightness"),
        "reason": "Chest pain or severe chest pressure can be serious and needs urgent medical evaluation.",
    },
    {
        "category": "breathing",
        "phrases": (
            "shortness of breath", "difficulty breathing", "trouble breathing", "cannot breathe",
            "can't breathe", "cant breathe", "gasping for air", "severe breathing difficulty",
        ),
        "reason": "Severe breathing difficulty can become dangerous quickly.",
    },
    {
        "category": "bleeding",
        "phrases": ("severe bleeding", "uncontrolled bleeding", "heavy bleeding", "bleeding won't stop", "bleeding wont stop"),
        "reason": "Severe or uncontrolled bleeding needs urgent medical care.",
    },
    {
        "category": "stroke",
        "phrases": (
            "stroke", "face drooping", "slurred speech", "one sided weakness", "one-sided weakness",
            "sudden weakness on one side", "sudden numbness on one side",
        ),
        "reason": "Possible stroke warning signs need emergency medical evaluation immediately.",
    },
    {
        "category": "consciousness",
        "phrases": ("unconscious", "unresponsive", "not waking up", "passed out", "fainted", "fainting"),
        "reason": "Loss of consciousness or unresponsiveness needs urgent medical evaluation.",
    },
    {
        "category": "seizure",
        "phrases": ("seizure", "convulsion", "convulsions"),
        "reason": "A seizure or convulsion may need urgent medical evaluation, especially if new, prolonged, or recurring.",
    },
    {
        "category": "allergic_reaction",
        "phrases": (
            "anaphylaxis", "severe allergic reaction", "throat swelling", "tongue swelling",
            "swelling of the throat", "swelling of the tongue",
        ),
        "reason": "A severe allergic reaction with airway swelling can become life-threatening quickly.",
    },
    {
        "category": "poisoning",
        "phrases": ("overdose", "poisoning", "poisoned"),
        "reason": "Possible overdose or poisoning needs urgent professional help.",
    },
    {
        "category": "self_harm",
        "phrases": (
            "suicide", "suicidal", "kill myself", "harm myself", "hurt myself",
            "end my life", "want to die",
        ),
        "reason": "If you may harm yourself, seek immediate crisis support or emergency care.",
    },
)

# Kept for compatibility with older imports/tests.
RED_FLAGS = {
    phrase: rule["reason"]
    for rule in EMERGENCY_RULES
    for phrase in rule["phrases"]
}

_NEGATION_RE = re.compile(
    r"\b(?:no|not|without|deny|denies|denied|don't|dont|do not|never)\b",
    re.IGNORECASE,
)


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").replace("’", "'").strip().lower())


def _is_negated(text: str, phrase_start: int) -> bool:
    """Best-effort local negation check without trying to understand medicine."""
    prefix = text[max(0, phrase_start - 60):phrase_start]
    # A punctuation/conjunction boundary usually starts a new clause, so only
    # inspect the final clause fragment immediately before the matched phrase.
    parts = re.split(r"[.!?;,]|\bbut\b|\bhowever\b", prefix, flags=re.IGNORECASE)
    tail = parts[-1] if parts else prefix
    words = re.findall(r"[a-z']+", tail)[-5:]
    return bool(_NEGATION_RE.search(" ".join(words)))


class SafetyEngine:
    def assess(self, message):
        text = _normalized(message)
        for rule in EMERGENCY_RULES:
            for phrase in rule["phrases"]:
                start = text.find(phrase)
                if start < 0 or _is_negated(text, start):
                    continue
                return {
                    "emergency": True,
                    "urgency": "emergency",
                    "reason": rule["reason"],
                    "matched": phrase,
                    "category": rule["category"],
                    "guidance": (
                        "Please contact local emergency services or go to the nearest emergency department now. "
                        "Do not wait for an AI chat if symptoms are severe, rapidly worsening, or you feel unsafe."
                    ),
                }
        return {
            "emergency": False,
            "urgency": "routine",
            "reason": None,
            "matched": None,
            "category": None,
            "guidance": None,
        }
