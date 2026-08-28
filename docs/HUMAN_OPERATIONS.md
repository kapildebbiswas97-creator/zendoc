# ZENDOC Human Operations

## Principle

AI coordinates digital workflows. Humans perform physical, professional, and regulated operations.

## Staff Categories

- Home-care nurse
- Caregiver
- Physiotherapist
- Sample collection worker
- Pharmacy worker
- Medicine delivery staff
- Transport driver
- Ambulance operator
- Device technician
- Customer support
- Field operations

## Task Lifecycle

`requested -> queued -> assigned -> accepted -> in_progress -> completed`

Alternative terminal or exception states: `failed`, `escalated`, `cancelled`.

## Working

- Admin-created staff profiles.
- Operations roles can create staff tasks.
- Assigned staff or admins can update task status.
- Events are recorded for task creation and status changes.

## Not Production Yet

No staff mobile app, payroll, route optimization, background dispatch, live provider integrations, or SLA automation is implemented.
