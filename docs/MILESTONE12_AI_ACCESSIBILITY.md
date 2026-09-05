# M12 Specialized AI & Voice Access Beta

## Product shape

ZENDOC now exposes four separate AI workspaces rather than sending every prompt
through one generic UI.

1. **ZENDOC AI** — top-level healthcare/platform orchestrator. It connects
   authorized Health Memory context, provider discovery, family care and
   permissioned workflows.
2. **Doctor AI** — safety-first symptom and medicine education. It is **not a
   licensed doctor**, does not diagnose, prescribe antibiotics or change doses,
   and provides a direct path to request a real clinician/telehealth session.
3. **Mental Wellness AI** — focused support for stress, sleep, overwhelm and
   everyday wellbeing. It is not therapy or a diagnosis.
4. **General Assistant** — general-purpose LLM/SLM workspace for writing,
   learning, coding, planning and everyday questions. Health-sensitive content
   is routed away from the generic model path.

All modes share the deterministic emergency safety gate.

## LLM / SLM boundary

The General Assistant uses the existing Model Router. Suitable PUBLIC/INTERNAL
requests may use a configured local model and, when policy allows it, a
configured cloud provider. PERSONAL requests remain local-only.
HEALTH_SENSITIVE and HIGH_RISK content is not sent through the generic
assistant.

ZENDOC AI continues to use the ZENDOC-SLM product layer: approved
provenance-bearing product context, privacy classification, structured model
output, post-generation validation and deterministic fallback.

No proprietary medically trained model is claimed.

## Doctor AI medicine boundary

Doctor AI may name common non-prescription examples for education, such as
paracetamol/acetaminophen, ORS or some antihistamines, together with suitability
warnings. It does not choose prescription medicines, antibiotics, dose changes
or treatment plans for a patient.

A real clinician consultation remains a separate provider workflow and must
follow provider acceptance and the telehealth capability state.

## Voice Access Beta

Voice Access Beta is implemented in the shared web shell so it is available
throughout the web application when the browser provides speech recognition and
speech synthesis.

Current beta capabilities:

- voice navigation to major ZENDOC areas;
- separate commands for ZENDOC AI, Doctor AI, Mental Wellness AI and General
  Assistant;
- page/latest-answer read-aloud;
- AI message dictation;
- explicit voice confirmation before navigation;
- explicit voice confirmation before sending an AI message;
- cancel and stop commands.

Voice Access intentionally does **not** automatically confirm bookings, orders,
payments, record sharing, consent changes or other consequential healthcare
actions. Those remain behind their normal confirmation controls.

### Browser limitation

A browser normally requires a user gesture and microphone permission before
speech recognition may start. Therefore the web beta cannot truthfully promise
"voice control from application launch with no touch" on every browser.

For a future native Android/iOS app, ZENDOC can add an accessibility-first
startup mode after the user grants microphone/accessibility permissions. That
native mode can preserve the same confirmation protocol while supporting a
more continuous hands-free experience.

## Accessibility position

Voice Access is an additional access channel, not a replacement for:

- semantic HTML;
- keyboard navigation;
- screen readers;
- visible focus;
- ARIA live regions;
- text controls;
- consent and confirmation.

The beta must not be described as complete WCAG certification or as a uniquely
unavailable feature elsewhere without evidence.

## Voice confirmation protocol

For navigation or AI message send:

1. user speaks a command;
2. ZENDOC repeats the requested action;
3. ZENDOC asks for "confirm" or "cancel";
4. only "confirm" proceeds.

This confirmation protocol does not authorize consequential clinical or
commercial actions.
