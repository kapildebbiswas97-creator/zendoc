# ZENDOC Connect: Unified Permissioned Care Communication & Video Intelligence

## 1. Overview

ZENDOC Connect is a role-aware, privacy-preserving communication and video guidance platform built into the ZENDOC ecosystem. It enables structured, permissioned messaging, call readiness checks, consent-driven medical record sharing, and educational video intelligence across patients, doctors, caregivers, family members, pharmacy partners, and operational staff.

---

## 2. Core Architecture & Privacy Principles

### 2.1 Communication Policy Matrix

All communication (contact discovery, conversations, messages, voice/video calls, and record attachments) is governed centrally by `zendoc.communication_policy`.

| Initiator | Target | Condition / Policy | Permitted Actions |
|:---|:---|:---|:---|
| **Patient** | **Doctor** | Doctor availability `patient_message_policy`: `anyone`, or `appointment` (active booking), or `accepted_consultation` | Chat message, structured records (with consent); Voice/Video if doctor toggles `allow_voice_requests`/`allow_video_requests` |
| **Doctor** | **Doctor** | Always permitted for clinical coordination and peer referrals | Chat, Voice, Video, Record sharing |
| **Doctor** | **Patient** | Existing patient, active appointment, or active consultation | Chat, Voice, Video, Care plans, Video demos |
| **Patient** | **Pharmacy** | Requires active `medicine_orders` context or explicit grant | Chat, prescription clarification, order updates |
| **User** | **Staff / Nurse / Physio** | Requires assigned `staff_tasks` context or service booking | Chat, task status updates, location instructions |
| **Family Member** | **Patient / Elder** | Requires active `family_access_grants` with `care_tasks` scope | Care check-ins, record coordination |
| **Admin** | **Any User** | Requires `support` context or explicit user communication grant | Support assistance (admin metrics aggregate operational counts but *never* expose private clinical chat content) |

### 2.2 Contact Discovery Privacy

The contact discovery service (`/api/v1/contacts`) strictly returns public contact records:
- **Exposed Fields**: `id`, `name`, `role`, `city`, `specialty`, `organization`, `provider_type`, `verified`, `reason`.
- **Hidden / Redacted Fields**: Phone numbers, raw emails, password hashes, and internal identifiers are **never** returned.
- **Searchable Attributes**: Search matches user names, roles, cities, doctor specialties (`pp.specialty`), organizations (`pp.organization`), and provider types (`pp.provider_type`).

---

## 3. Database Schema

ZENDOC Connect adds the following tables to SQLite:

### `communication_permissions`
Explicit or contextual grants between two parties:
- `id`: Primary key
- `requester_id`, `target_user_id`: Participating user IDs
- `context_type`, `context_id`: e.g. `appointment`, `order`, `family_care`, `support`
- `allow_chat`, `allow_voice`, `allow_video`, `allow_record_sharing`: Boolean flags (1/0)
- `status`: `active`, `revoked`, `expired`
- `created_by`, `expires_at`, `revoked_at`, `created_at`, `updated_at`

### `conversations`
Persistent communication threads:
- `id`: Primary key
- `conversation_type`: `direct`, `consultation`, `care_team`, `support`
- `title`: Subject / participant title
- `created_by`: Initiating user ID
- `context_type`, `context_id`: Associated domain context
- `status`: `active`, `archived`
- `created_at`, `updated_at`

### `conversation_participants`
- `conversation_id`, `user_id`: Composite Primary Key
- `role`: `owner`, `member`, `doctor`, `caregiver`, `staff`
- `joined_at`, `last_read_at`: Read receipt tracking
- `muted`: Boolean flag

### `messages`
- `id`: Primary key
- `conversation_id`: Foreign key to `conversations`
- `sender_id`: Foreign key to `users`
- `message_type`: `text`, `appointment`, `consultation`, `record`, `report`, `video`, `service_update`, `task_update`, `system`
- `body`: Text content (up to 4000 characters)
- `metadata_json`: JSON payload (video URLs, report IDs, status data)
- `created_at`, `edited_at`, `deleted_at`

### `message_receipts`
- `message_id`, `user_id`: Composite Primary Key
- `status`: `delivered`, `read`
- `delivered_at`, `read_at`: Timestamp tracking

### `message_attachments`
- `id`: Primary key
- `message_id`: Foreign key to `messages`
- `attachment_type`: `record`, `video`, `device_reading`, `prescription`
- `record_id`: Medical record ID (if record attachment)
- `url`: Video or asset URL
- `title`: Display title
- `metadata_json`: JSON metadata
- `created_at`

### `doctor_availability` (Enhanced)
- `doctor_id`: Primary key
- `status`: `available`, `busy`, `offline`
- `accepts_chat`, `accepts_voice`, `accepts_video`: Channel toggles
- `patient_message_policy`: `nobody`, `existing_patient`, `appointment`, `accepted_consultation`, `anyone`
- `allow_voice_requests`, `allow_video_requests`: Request permission toggles
- `allow_new_consultation_requests`: Boolean flag
- `note`, `updated_at`

---

## 4. Consent-Driven Record & Video Sharing

### 4.1 Medical Record Sharing (`share_report_message`)
- Enforces patient consent: Only the record owner, a family member with authorized `reports` scope grant, or an authorized provider with explicit consent may attach a medical record to a conversation.
- Unauthorized third parties attempting to attach a record receive `403 Permission Denied`.

### 4.2 Educational Video Intelligence & Truthfulness Rules
- **Video Discovery (`find_educational_video`)**: Searches curated educational fitness, rehabilitation, nutrition, and device guides.
- **Strict Truthfulness Rule**: If actual video content or transcripts are not retrieved from an external video API provider, step-by-step guidance is explicitly labeled:
  > *"General ZENDOC guidance for this exercise — not extracted from the video."*
- **Fabrication Prevention**: The system **never** fabricates view counts, star ratings, or doctor approvals.

---

## 5. Core Agent Communication Tools

The ZENDOC Core Agent (`zendoc.agent_core`) integrates communication tools while strictly complying with permissions:

1. `tool_find_contact(actor, query)`: Discovers permitted contacts only.
2. `tool_check_communication_permission(actor, target_user_id, channel, context)`: Evaluates permission decision matrix.
3. `tool_start_conversation(actor, target_user_id, context, title)`: Creates/opens permissioned thread.
4. `tool_send_message(actor, conversation_id, body, message_type, metadata)`: Posts message with notifications.
5. `tool_request_doctor_chat(actor, doctor_id, reason)`: Respects doctor availability policy and falls back to consultation request if required.
6. `tool_request_voice_call(actor, target_user_id, context)`: Assesses call readiness.
7. `tool_request_video_call(actor, target_user_id, context)`: Assesses video readiness.
8. `tool_share_video(actor, conversation_id, video_url, title)`: Attaches educational video.
9. `tool_share_report_with_consent(actor, conversation_id, record_id, title)`: Enforces owner consent before attaching medical reports.

---

## 6. REST API Endpoints

| Endpoint | Method | Role / Auth | Description |
|:---|:---:|:---|:---|
| `/api/v1/contacts` | `GET` | Authenticated | Discovers permitted contacts (`q` search param) |
| `/api/v1/conversations` | `GET` | Authenticated | Lists user's active conversations |
| `/api/v1/conversations` | `POST` | Authenticated | Starts a new conversation with permitted target |
| `/api/v1/conversations/<id>` | `GET` | Participant | Retrieves conversation details and participants |
| `/api/v1/conversations/<id>/messages` | `GET` | Participant | Lists messages and marks thread as read |
| `/api/v1/conversations/<id>/messages` | `POST` | Participant | Sends a message (creates receipts & notifications) |
| `/api/v1/conversations/<id>/read` | `POST` | Participant | Explicitly marks conversation as read |
| `/api/v1/conversations/<id>/share-video` | `POST` | Participant | Shares an educational video attachment |
| `/api/v1/conversations/<id>/share-report` | `POST` | Authorized | Shares a medical report with consent |
| `/api/v1/communication-permissions` | `POST` | Participant/Admin | Creates an explicit communication permission grant |
| `/api/v1/messages/unread-count` | `GET` | Authenticated | Returns total unread message count |
| `/api/v1/video-intelligence/search` | `GET` | Authenticated | Searches educational videos by query & category |
| `/api/v1/videos/guidance` | `GET` | Authenticated | Returns truthful step-by-step guidance |

---

## 7. Web UI & Responsive Layout

- **Desktop (3-Pane Layout)**:
  - **Left Pane (`.connect-list`)**: Search permitted care contacts and browse active conversation threads with unread indicators.
  - **Center Pane (`.connect-thread`)**: Active message stream with structured bubbles for text, reports, videos, and appointments, alongside the message composer.
  - **Right Pane (`.connect-info`)**: Participant details, contact privacy badges, and security information.
- **Mobile Responsive Behavior**:
  - Automatically collapses to single-pane navigation on viewports `< 720px`.
  - Includes a prominent `Back to Conversations` button when inside a thread.
