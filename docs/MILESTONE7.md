# ZENDOC Milestone 7

## Summary

Milestone 7 adds the ZENDOC Core Agent foundation, admin command center, beta telehealth communication, secure consultation messaging, camera intelligence infrastructure, fitness pose coach, video intelligence, and human operations task architecture. The implementation is additive and does not deploy, commit, or remove Milestones 1-6.

## Authentication Fixes

- Removed the real personal/admin email fallback from source and documentation.
- Admin bootstrap now uses only `ZENDOC_ADMIN_EMAIL` and `ZENDOC_ADMIN_PASSWORD`, or explicit test config fixtures.
- Added normalized email handling through `email_normalized`.
- Added duplicate detection that documents legacy duplicates in `duplicate_account_groups` without deleting accounts.
- Registration blocks duplicate normalized emails with: `An account with this email already exists. Please log in.`
- Login, password reset, and API auth lookup trim and lowercase email consistently.

## Working

- Core Agent API: `/api/v1/agent/message` with Communication Agent tools.
- Admin Agent Command Center: `/admin/agent-command-center` (aggregate metrics without private chat exposure).
- Doctor availability: `/doctor/availability` with customizable patient message policies and call permission flags.
- Telehealth request and secure consultation messaging: `/telehealth`
- ZENDOC Connect Permissioned Messaging: `/messages` (3-pane desktop layout, single-pane mobile responsive).
- Contact Discovery with privacy preservation: `/api/v1/contacts` (searches by name, role, specialty, organization; hides phone/email).
- Conversation & Message lifecycle: `/api/v1/conversations`, `/api/v1/conversations/<id>/messages`, unread counts, and delivery/read receipts.
- Consent-driven medical record sharing and video attachments in conversations.
- Universal Search integration: searches doctors, family, providers, permitted contacts, conversations, and educational videos.
- Video Guidance & Intelligence: `/videos` and `/api/v1/video-intelligence/search` with truthful fallback labeling.
- Local demo telehealth room controls after doctor acceptance.
- Fitness Pose Coach page: `/fitness/pose-coach`
- Pose session save API: `/api/v1/fitness/pose-sessions`
- Staff profile and staff task APIs.
- Agent/platform event logging.

## Database Changes

- `email_normalized`, `duplicate_of_user_id`, `duplicate_detected_at` on `users`
- `duplicate_account_groups`
- `agent_runs`
- `agent_actions`
- `agent_tool_calls`
- `agent_approvals`
- `platform_events`
- `doctor_availability` (with `patient_message_policy`, `allow_voice_requests`, `allow_video_requests`)
- `consultation_requests`
- `consultation_rooms`
- `consultation_messages`
- `communication_permissions`
- `conversations`
- `conversation_participants`
- `messages`
- `message_receipts`
- `message_attachments`
- `staff_profiles`
- `staff_tasks`
- `staff_task_events`
- `fitness_pose_sessions`
- `fitness_pose_feedback`
- `video_search_history`

## Validation

Commands run:

- `python -m compileall zendoc tests`
- Auth-first & Milestone 7.1 tests: `python -m pytest tests/test_milestone7.py -v` passed, 22/22 tests.
- Full regression: `python -m pytest` passed, 90/90 tests across Milestones 1-7.1.
