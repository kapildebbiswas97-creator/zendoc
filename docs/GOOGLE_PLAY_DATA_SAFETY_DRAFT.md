# ZENDOC Google Play Data Safety + Health Declaration Worksheet

Purpose: pre-submission worksheet only.

Do not copy answers blindly into Play Console. Verify them against the exact deployed build and every configured third-party service.

## Product identity

- App: ZENDOC
- Core surface: healthcare services/navigation, patient Health Memory, bounded AI, and wellness.
- Account creation: yes.
- Public-release account email verification: yes.
- Registration records accepted Privacy Policy and Terms versions: yes.
- Authenticated structured data export: yes.
- In-app deletion path: Profile -> Delete ZENDOC account.
- Public deletion resource: https://<production-domain>/account-deletion
- Privacy policy: https://<production-domain>/privacy
- Medical disclaimer: https://<production-domain>/medical-disclaimer

## Data categories handled by current ZENDOC code

Depending on the features a user uses, ZENDOC can handle the following data.

### Personal information

- name
- email
- phone
- age/date of birth where entered
- gender/sex-at-birth fields where entered
- city/address/saved locations
- emergency contact

### Health information

- health profile
- allergies
- medication/prescription-related records
- conditions/history entered by the user
- appointments
- medical records/reports
- measurements/vitals
- wellness/fitness/nutrition records
- Health Timeline / Health Memory
- family/dependent care information where entered

### User content and communications

- messages
- uploaded records
- AI prompts/responses
- patient-entered clinician-handoff questions and reason for visit

### App activity, diagnostics, and security

- product activity
- audit/security events
- request observations
- model-execution metadata
- error/operational state

## Purposes implemented in code

Potential purposes include:

- core app functionality
- account management and authentication
- healthcare workflow continuity
- user-requested AI assistance
- security/fraud/abuse prevention
- app reliability and operations
- owner product analytics

Do not claim advertising use unless advertising is actually added. Current ZENDOC public-launch code does not add an ad network.

## Third-party processing: verify before Play submission

Complete this table from the actual production deployment.

| Provider | Purpose | Data sent | Encryption in transit | Retention/deletion reviewed | Play disclosure updated |
|---|---|---|---|---|---|
| Hosting provider | Web/API hosting | TBD | HTTPS required | TBD | TBD |
| PostgreSQL host | Durable database | TBD | TBD | TBD | TBD |
| S3-compatible storage | Medical-record objects | Uploaded files/object metadata | TLS required | TBD | TBD |
| SMTP/email provider | Email verification, password reset, deletion email | Recipient email + transactional content | TLS configured | TBD | TBD |
| Maps/Places provider | Care discovery if enabled | Search/location query as configured | TBD | TBD | TBD |
| Cloud AI provider | Only if enabled | Exact configured scope | TBD | TBD | TBD |
| Video provider | Only if enabled | Search query as configured | TBD | TBD | TBD |

If a provider is not enabled in production, do not describe it as an active transfer merely because adapter code exists.

## Collection vs sharing

Google Play uses specific definitions for "collected" and "shared." Review those definitions for every data category in the final Play Console form.

Important ZENDOC distinctions:

- storing data in the ZENDOC backend is collection;
- sending data to a service provider may need disclosure according to Google's definitions and exceptions;
- public healthcare search input may be sent to an enabled map/directory provider;
- model/cloud AI data flow depends on the actual configured routing;
- do not assume "not shared" without reviewing every enabled production processor.

## Security behavior to verify

Current code includes:

- HTTPS required by the public-launch gate;
- HttpOnly/SameSite sessions;
- Secure session cookies in production;
- CSRF protection for browser mutations;
- scoped consent/authorization;
- password hashing;
- hashed API tokens for newly stored tokens;
- audit/security boundaries;
- public-release email ownership verification before ordinary user login;
- versioned Privacy Policy and Terms acceptance records;
- no offline service-worker caching of authenticated health HTML/API responses.

Do not select a Play security claim that requires an external certification unless ZENDOC actually has that certification.

## Account deletion disclosure

Current deletion implementation:

- hard-deletes the ordinary user account;
- deletes directly attributed AI/history/analytics/observability rows covered by the deletion service;
- deletes account email-verification and policy-acceptance records;
- cascades account-owned database records according to the schema;
- deletes owned medical-record objects through the configured storage adapter;
- may preserve another user's necessary operational history only after removing or de-identifying the deleted provider's user identity.

Before launch:

- test deletion against production-like PostgreSQL;
- test deletion against the real S3-compatible storage;
- verify hosting/backups retention behavior;
- accurately describe any legally or operationally retained data in the live privacy policy.

## Health apps declaration worksheet

Review the exact public build. Current categories to evaluate include:

- Healthcare services and management: provider discovery, connected appointments, care continuity.
- Medication and treatment management: pharmacy, prescription, and reminder flows where enabled.
- Activity and fitness: fitness profile/plans/sessions.
- Nutrition and weight management: nutrition and hydration functionality.
- Stress management, relaxation, mental acuity: Mental Wellness & Awareness.
- Diseases and conditions management: select only if the shipping experience actually manages conditions rather than merely storing history.
- Clinical decision support: do not select merely because ZENDOC has AI; compare the exact professional-facing functionality with Google's definition.
- Medical device apps: do not select unless ZENDOC is actually regulated as a medical device and the required regulatory evidence exists.

## Store-listing safety wording

The store listing should state clearly:

- ZENDOC offers healthcare navigation, personal health organization, and bounded AI guidance.
- AI guidance is informational and can be wrong.
- ZENDOC does not independently diagnose, prescribe, or change medication.
- External/public provider results are discovery-only unless marked connected/verified.
- ZENDOC does not claim autonomous emergency dispatch.
- Users should seek qualified professionals for diagnosis/treatment and use local emergency services for emergencies.

## Final sign-off checklist

- [ ] Exact production domain inserted in Privacy/Delete URLs.
- [ ] Privacy policy publicly accessible without login and not a PDF.
- [ ] In-app deletion tested.
- [ ] Public deletion tested without requiring app reinstall.
- [ ] Registration policy acceptance tested.
- [ ] Account email verification and resend tested without account enumeration.
- [ ] Account structured export tested.
- [ ] Password-reset email tested.
- [ ] Record-storage deletion tested.
- [ ] Every enabled third-party production processor listed above.
- [ ] Data Safety answers reviewed against actual network/config behavior.
- [ ] Health apps declaration matches exact public features.
- [ ] Store description matches medical disclaimer/truth boundaries.
- [ ] Target SDK 36+ verified.
- [ ] Digital Asset Links verified for final Play signing certificate.
- [ ] Closed-testing requirements satisfied for the developer account if applicable.
