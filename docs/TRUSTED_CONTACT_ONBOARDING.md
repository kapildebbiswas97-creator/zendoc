# Trusted-contact provider onboarding

The owner can import a small JSON or CSV batch of referrals supplied by a medical student, doctor, pharmacist, or hospital contact through:

- `POST /api/v1/admin/startup/provider-network/trusted-contacts/preview`
- `POST /api/v1/admin/startup/provider-network/trusted-contacts/apply`

The preview endpoint is read-only. Applying a batch requires `apply: true` and revalidates every row. Each row must include:

- `provider_type`: `doctor`, `hospital`, or `pharmacy`;
- `source_type`: `referral`, `college_network`, or `institution_pilot`;
- a stable `source_reference` supplied by the contact or source system;
- at least one provider/contact identifier;
- `permission_to_share: true`.

`institution_pilot` rows also require an existing `linked_pilot_id`. Re-importing the same source reference and unchanged contact is idempotent. A changed row with an existing source reference is reported as a conflict and cannot overwrite the earlier record.

Imported rows become `discovered` provider prospects in the existing owner-managed network. They do not create user accounts, mark providers verified, publish schedules, or assert certification, availability, medicine stock, bed counts, or booking connectivity. Patient records, prescriptions, diagnoses, passwords, and other private or operational fields are rejected.

