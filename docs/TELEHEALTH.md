# ZENDOC Telehealth

## Current Status

Telehealth is a beta architecture, not production telemedicine.

## Working

- Doctors/hospitals manage availability and communication policies (`patient_message_policy`, `allow_voice_requests`, `allow_video_requests`).
- Patients request chat, voice, or video consultation.
- Doctors accept, reject, schedule, or end consultations.
- Secure consultation messages are scoped to the patient and doctor.
- ZENDOC Connect permission matrix validates calling and video permissions before signaling controls are unlocked.
- Accepted or scheduled consultations create a local demo room record.
- Browser media controls require user action before camera or microphone permission is requested.

## Integration with ZENDOC Connect

- Doctor availability toggles determine whether patients can initiate direct chat (`/messages`) or must first submit a formal consultation request (`/telehealth`).
- Voice and video call buttons in ZENDOC Connect indicate real-time readiness or display lock status with actionable explanations.
- Structured medical records and educational videos can be shared directly into consultations or active conversation threads.

## Not Production Yet

- No production WebRTC signaling server.
- No TURN/STUN configuration.
- No payment or insurance workflow.
- No automatic recording.
- No clinical compliance certification.

## Safety

Patients cannot automatically activate a doctor's microphone or camera. Doctors cannot automatically activate a patient's microphone or camera. Each browser asks for local permission only after the user clicks a join/start control.

