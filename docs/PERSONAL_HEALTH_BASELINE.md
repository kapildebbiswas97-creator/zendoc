# Personal Health Baseline v1

ZENDOC Personal Health Baseline provides deterministic, read-only longitudinal analytics over authorized health measurements.

## What it does

- compares a patient's recent numeric measurements with that same patient's earlier measurements;
- keeps unit families separate and chooses the latest measurement unit for the comparison;
- records baseline/recent point counts and measurement-source provenance;
- reports descriptive states: `NO_DATA`, `INSUFFICIENT_BASELINE`, `NO_RECENT_DATA`, `NEAR_PERSONAL_BASELINE`, `ABOVE_PERSONAL_BASELINE`, or `BELOW_PERSONAL_BASELINE`;
- supports primary and secondary numeric values such as the two components of blood pressure when available;
- routes all patient targeting through the existing `measurements` authorization/consent boundary.

## What it does not do

The baseline engine does not apply disease thresholds, diagnose a condition, prescribe or recommend treatment, change Health Memory records, or replace the deterministic emergency safety engine. A personal deviation means only that recent measurements differ from the patient's own prior measurements under the documented statistical rule.

## API

`GET /api/v1/health-baseline`

Required query parameter: `metric_type`.

Optional parameters: `patient_id`, `baseline_days` (14-3650, default 90), and `recent_days` (1-90, default 7, and smaller than `baseline_days`).

Provider access remains subject to the existing patient authorization and consent rules for measurement data. Cross-patient IDOR attempts must fail closed.

## Statistical rule

The prior baseline is the requested baseline window excluding the recent window. At least three prior same-unit values are required. The service computes the prior population mean and population standard deviation, and the recent mean. A recent mean more than one prior standard deviation above/below the prior mean is labeled above/below the personal baseline. This is descriptive analytics only, not a clinical reference range.
