# Preventive Care v1

ZENDOC Preventive Care v1 is a deterministic planning layer for preventive reminders with explicit provenance.

## Principle

The engine does not invent screening, vaccination, dental, vision, lifestyle or check-up intervals. A plan exists only when a due date was explicitly recorded by the patient/provider/owner, or when a later workflow binds it to an approved immutable medical-knowledge document.

## Provenance

Supported source states are:

- `patient_entered`
- `provider_entered`
- `owner_entered`
- `guideline_grounded`

`guideline_grounded` requires a document that already passed the ZENDOC medical-knowledge approval gate. Referencing an approved document still does not mean the plan is universally clinically applicable.

## Due-state engine

For active plans, ZENDOC computes only time-based states:

- `OVERDUE` — recorded due time is in the past;
- `DUE_SOON` — recorded due time is within 30 days;
- `UPCOMING` — recorded due time is more than 30 days away.

Completed and dismissed plans retain their historical state and provenance.

## Authorization

All patient targeting reuses the existing Health Memory `timeline` authorization/consent boundary. Cross-patient IDOR attempts fail closed. Patients cannot label their own plan as provider-entered provenance.

## Safety boundary

This layer is not a diagnosis engine, screening guideline engine, prescribing system, emergency detector or treatment recommender. Automatic guideline-derived preventive recommendations remain disabled until approved versioned medical knowledge and a separately reviewed applicability policy exist.
