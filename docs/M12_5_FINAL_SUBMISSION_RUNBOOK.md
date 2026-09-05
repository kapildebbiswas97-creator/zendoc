# M12.5 Final Submission Runbook

## Freeze point

Branch: `m12.5/agentic-care-os`

This branch is the final pre-submission feature freeze for the video. Do not add new features before recording unless a blocking defect is found.

## Final demo path

1. Start ZENDOC locally and sign in as a patient.
2. Open **ZENDOC AI**.
3. Click **Run Demo Scenario** or submit:
   `Run ZENDOC synthetic agentic demo`
4. Show the visible **Agent Activity** lifecycle:
   **OBSERVE → UNDERSTAND → PLAN → ACT → VERIFY → REMEMBER**.
5. Point out the selected **Care Agent**, risk state, tool-plan preview, and verification state.
6. Show that the demo stops at **WAITING_HUMAN** before any consequential real-world action.
7. Explain that provider acceptance, booking, stock, payment, delivery, and emergency dispatch are never fabricated.
8. Enable **Voice Access** and say:
   `read agent activity`
   or
   `ask ZENDOC check my unread messages`
9. Show **Doctor AI**, **Mental Wellness AI**, **General Assistant**, **Health Memory**, **Care Graph / Connected Care**, **Pharmacy**, **Diagnostics**, and **Telehealth** only as time permits.
10. End on the ZENDOC landing/dashboard and summarize the product vision.

## Suggested spoken demo message

> ZENDOC is not just a healthcare chatbot. It is a trust-first Agentic Care OS. It understands a care goal, chooses specialized agents, creates a bounded plan, uses only permissioned tools, stops for human confirmation when needed, verifies what actually happened, and remembers the care journey. If ZENDOC has no live provider data or integration, it does not pretend the real-world action succeeded.

## Truth boundary

The synthetic demo is deliberately labelled synthetic. It does not call live external providers.

Do not claim:
- a real doctor accepted a consultation unless the provider workflow records acceptance;
- a medicine is in stock unless current evidence supports it;
- an order was delivered or dispatched when only an internal request was created;
- an ambulance was dispatched;
- payment was completed without an integration;
- ZENDOC diagnosed or prescribed autonomously;
- ZENDOC-SLM is a clinically validated proprietary medical model.

## Pre-recording verification

Run:

```powershell
git pull --ff-only origin m12.5/agentic-care-os
python -m pytest tests/test_milestone12_ai_hardening.py -q
python -m pytest -q
git diff --check
python run.py
```

Expected: all tests pass; the existing Windows PytestCacheWarning may remain.

## Manual browser smoke test

- Home page loads.
- ZENDOC AI opens.
- Run Demo Scenario renders Agent Activity.
- Verify state says WAITING_HUMAN.
- Voice mic does not block the page.
- Voice `read agent activity` reads the visible trace.
- Doctor AI answers an ordinary fever/cough prompt without claiming to be a licensed doctor.
- Emergency wording still triggers deterministic emergency guidance.
- Patient login works.
- No secrets, .env, local database, or uploads are committed.

## After recording

Freeze this branch. Do not refactor, redesign, or add experimental integrations before submission. Only make a change if a reproducible blocker prevents the demo or submission.
