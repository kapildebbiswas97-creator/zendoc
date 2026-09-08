"""ZENDOC multilingual foundation.

Canonical healthcare data remains language-neutral/English-keyed internally.
This module handles language preference, script detection, safe templates, and
translation capability boundaries without pretending a translation model exists.
"""
from __future__ import annotations

from dataclasses import dataclass


SUPPORTED_LANGUAGES = {
    "en": "English",
    "bn": "Bengali",
    "hi": "Hindi",
}

SAFE_TEMPLATES = {
    "emergency_notice": {
        "en": "If this may be life-threatening, contact local emergency services now.",
        "bn": "এটি জীবন-সঙ্কটজনক হতে পারে হলে এখনই স্থানীয় জরুরি পরিষেবার সঙ্গে যোগাযোগ করুন।",
        "hi": "यदि यह जानलेवा हो सकता है, तो अभी स्थानीय आपातकालीन सेवाओं से संपर्क करें।",
    },
    "not_diagnosis": {
        "en": "This information is not a confirmed diagnosis.",
        "bn": "এই তথ্যটি নিশ্চিত রোগনির্ণয় নয়।",
        "hi": "यह जानकारी किसी पुष्टि किए गए निदान का स्थान नहीं लेती।",
    },
    "coverage_not_confirmed": {
        "en": "Coverage is not confirmed until the official authority or insurer verifies it.",
        "bn": "সরকারি কর্তৃপক্ষ বা বিমা সংস্থা যাচাই না করা পর্যন্ত কভারেজ নিশ্চিত নয়।",
        "hi": "आधिकारिक प्राधिकरण या बीमाकर्ता के सत्यापन तक कवरेज की पुष्टि नहीं है।",
    },
}


@dataclass(frozen=True)
class LanguageDecision:
    language: str
    language_name: str
    source: str
    confidence: float

    def to_dict(self) -> dict:
        return {
            "language": self.language,
            "language_name": self.language_name,
            "source": self.source,
            "confidence": self.confidence,
        }


def normalize_language(value: str | None, default: str = "en") -> str:
    raw = str(value or "").strip().lower()
    aliases = {
        "english": "en",
        "eng": "en",
        "bengali": "bn",
        "bangla": "bn",
        "বাংলা": "bn",
        "hindi": "hi",
        "हिंदी": "hi",
    }
    code = aliases.get(raw, raw)
    return code if code in SUPPORTED_LANGUAGES else default


def detect_language(text: str, preferred: str | None = None) -> LanguageDecision:
    preferred_code = normalize_language(preferred, default="") if preferred else ""
    if preferred_code:
        return LanguageDecision(preferred_code, SUPPORTED_LANGUAGES[preferred_code], "user_preference", 1.0)

    value = str(text or "")
    if not value.strip():
        return LanguageDecision("en", "English", "empty_default", 0.5)

    bengali = sum(1 for char in value if "ঀ" <= char <= "৿")
    devanagari = sum(1 for char in value if "ऀ" <= char <= "ॿ")
    letters = sum(1 for char in value if char.isalpha()) or 1

    bn_ratio = bengali / letters
    hi_ratio = devanagari / letters
    if bn_ratio >= 0.25 and bengali > devanagari:
        return LanguageDecision("bn", "Bengali", "script_detection", min(0.99, 0.65 + bn_ratio / 3))
    if hi_ratio >= 0.25 and devanagari > bengali:
        return LanguageDecision("hi", "Hindi", "script_detection", min(0.99, 0.65 + hi_ratio / 3))
    return LanguageDecision("en", "English", "script_detection", 0.75)


def safe_template(template_key: str, language: str = "en") -> str:
    key = str(template_key or "").strip()
    if key not in SAFE_TEMPLATES:
        raise LookupError(f"Unknown safe language template '{key}'.")
    code = normalize_language(language)
    return SAFE_TEMPLATES[key].get(code) or SAFE_TEMPLATES[key]["en"]


def translation_capability(source_language: str, target_language: str) -> dict:
    source = normalize_language(source_language)
    target = normalize_language(target_language)
    if source == target:
        return {
            "status": "WORKING",
            "source_language": source,
            "target_language": target,
            "provider": "identity",
            "message": "No translation is required.",
        }
    return {
        "status": "INTEGRATION_REQUIRED",
        "source_language": source,
        "target_language": target,
        "provider": None,
        "message": (
            "Language detection and safety templates are working. "
            "Free-form translation requires a configured local/multilingual model or translation provider."
        ),
    }


def canonicalize_language_metadata(text: str, preferred: str | None = None) -> dict:
    decision = detect_language(text, preferred=preferred)
    return {
        **decision.to_dict(),
        "canonical_structured_language": "en",
        "supported_languages": dict(SUPPORTED_LANGUAGES),
        "translation_required": decision.language != "en",
    }
