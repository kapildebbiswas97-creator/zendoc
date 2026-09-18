# ZENDOC Public Web + Android/Google Play Release Runbook

Status: engineering runbook for the current ZENDOC competition branch.
Last reviewed: 18 September 2026.

This document separates repository work from steps that require a real domain, hosting account, credentials, Android signing key, developer account, testers, or Google review.

## Release architecture

Use one ZENDOC backend/web product:

- Flask/ZENDOC backend with PostgreSQL.
- Durable S3-compatible medical-record object storage.
- HTTPS custom domain.
- Transactional SMTP for account email verification, password recovery, and off-app account deletion.
- Installable PWA for direct mobile installation.
- Android Trusted Web Activity generated from the live PWA for Play distribution.
- Digital Asset Links to prove the Android package and website belong together.

Do not build a second healthcare backend inside Android. The Android application is a distribution shell around the same server-side safety, consent, and data authority.

## Public-launch gate

The Founder Readiness page includes a Public Launch Gate. Do not open the product to ordinary public users while it reports PUBLIC_LAUNCH_BLOCKED.

Required environment values include:

    ZENDOC_ENV=production
    ZENDOC_PUBLIC_BASE_URL=https://your-domain.example
    ZENDOC_PUBLIC_RELEASE_REQUIRED=true
    ZENDOC_SUPPORT_EMAIL=support@your-domain.example

    DATABASE_URL=postgresql://...
    ZENDOC_PERSISTENCE_VERIFIED=true
    ZENDOC_REQUIRE_DURABLE_DATABASE=true
    ZENDOC_BACKUP_VERIFIED=true

    ZENDOC_EMAIL_PROVIDER=smtp
    ZENDOC_EMAIL_VERIFIED=true
    ZENDOC_SMTP_HOST=...
    ZENDOC_SMTP_PORT=587
    ZENDOC_SMTP_USERNAME=...
    ZENDOC_SMTP_PASSWORD=...
    ZENDOC_SMTP_FROM_EMAIL=...
    ZENDOC_SMTP_USE_TLS=true

    ZENDOC_STORAGE_PROVIDER=s3
    ZENDOC_STORAGE_VERIFIED=false
    ZENDOC_TELEHEALTH_PROVIDER=internal_chat
    ZENDOC_S3_ENDPOINT_URL=...
    ZENDOC_S3_REGION=...
    ZENDOC_S3_BUCKET=...
    ZENDOC_S3_ACCESS_KEY_ID=...
    ZENDOC_S3_SECRET_ACCESS_KEY=...

After the real object-storage smoke test succeeds, set ZENDOC_STORAGE_VERIFIED=true only for that unchanged configuration.

## Web release sequence

1. Require blocking repository CI to pass.
2. Deploy the exact validated release commit with PostgreSQL and production secrets.
3. Configure S3-compatible record storage.
4. In the target deployment environment run: python scripts/verify_record_storage.py
5. Configure SMTP and run: python scripts/verify_transactional_email.py you@example.com
6. Configure a protected scratch PostgreSQL database and run the guarded restore test:
   DATABASE_URL=<production-db> ZENDOC_BACKUP_VERIFY_DATABASE_URL=<scratch-verify-db> ZENDOC_BACKUP_VERIFY_ALLOW_RESET=true python scripts/verify_postgres_backup_restore.py
7. Verify the hosting provider's scheduled backup/PITR retention, then set ZENDOC_BACKUP_VERIFIED=true.
8. Buy/connect the domain and enable HTTPS.
9. Set ZENDOC_PUBLIC_BASE_URL to that exact HTTPS origin.
10. Configure a real support email.
11. Set ZENDOC_EMAIL_VERIFIED=true and ZENDOC_STORAGE_VERIFIED=true only after their real smoke tests pass.
12. Set ZENDOC_PUBLIC_RELEASE_REQUIRED=true only when the complete public configuration is ready.
13. Run: python scripts/verify_public_launch.py https://your-domain.example
14. Create a separate test account, accept the live Privacy Policy and Terms, verify the email link, confirm login is blocked before verification and allowed after verification.
15. Test account data export, password reset, signed-in deletion and public deletion-request flows using that test account.
16. Open Founder Readiness and require zero Public Launch blockers.
17. Test using a physical phone/PWA before inviting real users.

## Public resources

The following must remain reachable:

- /privacy
- /terms
- /medical-disclaimer
- /account-deletion
- /register/patient
- /resend-verification
- /verify-email
- /manifest.webmanifest
- /sw.js
- /healthz

The service worker intentionally does not cache authenticated HTML or API health data. Offline mode uses a generic connection page.

## Account identity, export and deletion

For public release, ZENDOC records the Privacy Policy and Terms versions accepted at registration and requires verification of the account email before ordinary user login.

Authenticated users can download a structured account export from Profile. Password hashes, API/reset tokens, secret keys and internal medical-record storage object keys are excluded.

ZENDOC supports account deletion through:


- in-app/profile deletion,
- signed-in web password-confirmed deletion,
- public web deletion request by email when SMTP is configured,
- mobile API deletion through DELETE /api/v1/account.

Do not replace deletion with account freezing or deactivation. Provider/staff deletion may retain only a de-identified inactive operational anchor when another patient's care history depends on that foreign-key reference.

## Android Trusted Web Activity

Generate the Android shell only after the final domain is live.

Windows:

    .\scripts\bootstrap_android_twa.ps1 -BaseUrl "https://your-domain.example" -PackageId "com.yourbrand.zendoc"

macOS/Linux:

    bash scripts/bootstrap_android_twa.sh https://your-domain.example com.yourbrand.zendoc

Bubblewrap reads the live web manifest and generates the Android project.

## Android target requirement

As of 18 September 2026, new Google Play apps and app updates must target Android 16 / API 36 or higher. Verify the generated project before submission instead of assuming a generator default is compliant.

## Digital Asset Links

After signing the Android app, obtain the SHA-256 certificate fingerprint for the signing certificate used by the installed app.

Configure:

    ZENDOC_ANDROID_PACKAGE_NAME=com.yourbrand.zendoc
    ZENDOC_ANDROID_SHA256_CERT_FINGERPRINT=AA:BB:CC:...

Then verify:

    https://your-domain.example/.well-known/assetlinks.json

If Play App Signing uses a different app-signing certificate from the local/upload key, configure the fingerprint corresponding to the app users receive from Google Play.

## Developer-account and testing gates

For broad distribution, current Android Developer Console guidance lists a one-time USD 25 full-distribution registration fee.

For personal Google Play developer accounts created after 13 November 2023, Google currently requires a closed test with at least 12 testers continuously opted in for 14 days before applying for production access.

These are external account/testing gates. Repository code cannot legitimately bypass them.

## Health app declaration

ZENDOC provides health-related functionality and must complete the Play Console Health apps declaration accurately.

Evaluate the exact shipping build against relevant categories, including where applicable:

- Healthcare services and management.
- Medication and treatment management.
- Activity and fitness.
- Nutrition and weight management.
- Stress management, relaxation, mental acuity.
- Diseases and conditions management only where the shipping product really provides management features.

Do not declare ZENDOC as a regulated medical device unless it actually meets that legal definition and all required evidence exists.

Keep store wording aligned to the app truth boundaries:

- AI is bounded/informational and may be wrong.
- No autonomous diagnosis or prescribing.
- No fake emergency dispatch.
- Public/external provider results remain discovery-only unless connected and verified.
- No stock, bed, payment, insurance, or fulfilment claim without real evidence.

## Play data-safety preparation

Review docs/GOOGLE_PLAY_DATA_SAFETY_DRAFT.md against the exact production deployment.

The Play form must reflect real deployed data flows. If hosting, analytics, email, maps, AI, storage, or another provider changes, update the declaration before submission.

## Release evidence to preserve

Before Android upload preserve:

- exact web release commit SHA,
- CI run result,
- public-domain verification output,
- storage smoke output,
- Android package ID,
- version name/code,
- target SDK evidence (36 or higher),
- signing/upload certificate fingerprints,
- live Digital Asset Links response,
- privacy URL,
- account-deletion URL,
- Data safety worksheet,
- Health apps declaration answers,
- closed-test feedback/tester evidence.

## Truth boundary

A green public software gate does not prove regulatory approval, medical-device status, clinical effectiveness, provider network breadth, Snapdragon/NPU execution, Google Play approval, or fundraising success.
