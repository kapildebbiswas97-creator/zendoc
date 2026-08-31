# Demo Release Checklist

Status is evidence-based as of Milestone 8.3 + Selection Beta Hardening. `PASS` means covered by the automated suite or repository audit. `FAIL` means a required external condition has not been configured or verified.

| Check | Result | Evidence / blocker |
| --- | --- | --- |
| Registration works | PASS | Patient and provider registration tests |
| Duplicate registration handled | PASS | Normalized duplicate returns login guidance |
| Login works | PASS | Web/API patient, provider, and configured-owner tests |
| Logout works | PASS | Rotated session plus CSRF-protected production POST |
| Login again works | PASS | Logout/login and restart integration tests |
| App restart preserves account | PASS | Same isolated database reopened by a new Flask app |
| Role preserved | PASS | Stable patient/doctor/owner IDs and roles verified |
| Profile/data preserved | PASS | Profile, metric, notification, appointment, provider schedule, conversation, and message verified |
| Admin remains owner-only | PASS | Public/Admin manipulation blocked; owner preserved after restart |
| Patient isolation works | PASS | Existing record/grant tests plus post-restart notification isolation |
| Provider isolation works | PASS | Existing provider/consultation/message authorization tests |
| Major demo routes return successfully | PASS | Representative patient and doctor route smoke test |
| No fake integrations | PASS | Password recovery and persistence use truthful status labels |
| Mobile critical flow usable | PASS | Existing responsive/auth/API tests; device-level visual QA remains recommended |
| All POST forms have CSRF protection | PASS | AUD-01: 18 forms across 10 templates fixed; re-scan shows 0 missing |
| IoT device sync measurements persist | PASS | AUD-02: `get_db().commit()` added to `create_measurement()`; end-to-end verified |
| Ambulance endpoint and response key correct | PASS | AUD-03: `/api/v1/ambulance/requests`, key `ambulance_request`; confirmed in test suite |
| Doctor availability status values correct | PASS | AUD-04: `"available"/"busy"/"offline"/"consultation_only"`; confirmed in test suite |
| Complete automated suite green | PASS | **192 passed, 1 warning in 206.76 seconds** (includes 10-suite hardening regression) |
| Production persistence configured | **FAIL** | No durable hosted database credentials/infrastructure configured — intentional pre-selection decision |
| Production restart/redeploy persistence manually verified | **FAIL** | Requires controlled verification against the configured production store |
| No secrets committed | PASS | Placeholder-only configuration; final secret scan required before production deploy |

## Release decision

Permanent production persistence is intentionally not configured before the selection round. This limitation is disclosed to all testers and does **not** block the Selection Beta.

**SELECTION BETA READY — PERSISTENCE LIMITATION DISCLOSED**

All P0/P1 issues found during the final hardening audit have been fixed and verified. The persistence limitation is a known, pre-declared selection-beta condition, not a regression or blocking defect. See `docs/FINAL_RELEASE_AUDIT.md` for full audit detail.
