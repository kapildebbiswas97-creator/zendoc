# Demo Release Checklist

Status is evidence-based as of Milestone 8.3. `PASS` means covered by the automated suite or repository audit. `FAIL` means a required external condition has not been configured or verified.

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
| Production persistence configured | **FAIL** | No durable hosted database credentials/infrastructure were available |
| Production restart/redeploy persistence manually verified | **FAIL** | Requires controlled verification against the configured production store |
| No secrets committed | PASS | Placeholder-only configuration and final secret scan required |
| Complete automated suite green | PASS | 182 passed in 560.36 seconds; M8.3 focused suite 13/13 |

## Release decision

External tester readiness must not be declared while either production persistence item is `FAIL`.

**DEMO FREEZE BLOCKED — PERSISTENCE INTEGRATION REQUIRED**
