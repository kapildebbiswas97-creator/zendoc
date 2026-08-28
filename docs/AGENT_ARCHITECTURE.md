# ZENDOC Agent Architecture

## Core Rule

The ZENDOC Core Agent coordinates workflows through permissioned tools. It does not receive unrestricted database, filesystem, deployment, billing, or health-record access.

## Safety Order

User/admin command -> Safety Agent -> intent routing -> permissioned tool -> audit log -> user-facing result.

Emergency detection runs before ordinary agent routing and never waits for complex chains.

## Agent Registry

- Care Agent
- Doctor/Telehealth Agent
- Communication Agent (permissioned messaging, contact discovery, record/video sharing)
- Fitness Agent
- Operations Agent
- Family Care Agent
- Pharmacy Agent
- Transport Agent
- Home Health Agent
- IoT Agent
- Video Intelligence Agent
- Safety Agent

## Communication Tool Layer

The Core Agent delegates communication actions through strictly validated tools:
- `tool_find_contact`: Discovers permitted contacts with privacy filtering.
- `tool_check_communication_permission`: Checks central policy matrix.
- `tool_start_conversation`: Establishes permissioned threads.
- `tool_send_message`: Sends messages and triggers receipts/notifications.
- `tool_request_doctor_chat`: Evaluates doctor message policy and consultation requirements.
- `tool_request_voice_call` / `tool_request_video_call`: Evaluates calling permissions.
- `tool_share_video`: Attaches educational videos with truthfulness disclosures.
- `tool_share_report_with_consent`: Enforces owner or family consent before attaching health records.

## Tool Controls

Every tool must enforce authentication, authorization, ownership, consent, validation, and audit logging. High-impact operations (such as record sharing or irreversible deletions) require explicit confirmation and must not be executed autonomously.

## Memory Boundaries & Admin Privacy

ZENDOC separates patient health memory, conversation memory, operational memory, agent memory, and audit history.
- The **Admin Agent Command Center** displays aggregate operational metrics, service counts, and task queues.
- **Privacy Boundary**: Admins do not casually gain access to read private patient-doctor clinical chat messages unless granted explicit support authorization.

