# ZENDOC — DHN HealthTech Innovation Challenge 2026 / IIT Kanpur Submission Package

This document maps the current ZENDOC product to the official 2026 DHN HealthTech Innovation Challenge in collaboration with IIT Kanpur. It is a submission-preparation source, not proof of eligibility or selection.

## Hard eligibility gate

Before applying, verify that the applicant satisfies the organizer's current eligibility requirements. The 2026 challenge states that applicants are HealthTech startups with:

- a market-ready solution beyond the idea stage;
- a functional product;
- proven validation such as customers, pilots, deployments, revenue, or user adoption;
- an India presence through a registered Indian entity/branch;
- incorporation within the stated company-age limits;
- annual turnover within the stated limit.

**Do not claim that ZENDOC satisfies the India-registration, incorporation, traction, pilot, deployment, revenue, or user-adoption requirements unless documentary evidence exists.**

Current published application deadline: **23 September 2026**. Current published Demo Day: **23 October 2026 at IIT Kanpur**. Recheck the organizer site immediately before submission because competition details can change.

## Suggested track

Primary fit:

**AI for Primary Care, Rural Health & Frontline Workers**

Secondary fit, depending on the final application emphasis:

- Smart Hospitals, Patient Experience & Workflow Automation
- Trusted Health Data, DPDP, ABDM & Interoperability
- Mental Health, Chronic Disease & Preventive Care

Do not claim ABDM production integration, clinical validation, regulatory approval, or hospital deployment unless actual evidence exists.

## Suggested title

**ZENDOC — Privacy-First AI Care Navigation and Longitudinal Health Memory for India**

## One-line pitch

ZENDOC is a healthcare navigation and continuity platform that combines verified-provider discovery, connected appointment workflows, longitudinal Health Memory, deterministic safety controls, and privacy-first local AI assistance to help people move from a health question to an appropriate next care step.

## Problem

Healthcare information and patient journeys are fragmented across provider directories, appointments, records, reports, family care, pharmacies, diagnostics, and follow-up. Discovery alone does not create continuity, while generic AI systems can introduce unsafe or unverifiable healthcare claims.

ZENDOC focuses on the coordination layer: discover care, distinguish verified/official/external data, request appointments where a real ZENDOC provider connection exists, maintain private longitudinal context, and use AI only within explicit safety and permission boundaries.

## Solution

The current product includes:

- Universal Healthcare Search across currently available ZENDOC provider data, official/public records and configured map sources.
- Source-tier and verification labels so discovery does not imply verification.
- Connected provider profiles with published availability and appointment requests.
- Appointment status transitions and internal CareLoop coordination for registered providers.
- Health Memory covering records, reports, timeline, vitals and consent/access controls.
- Family-care and broader care-workflow foundations.
- ZENDOC AI with emergency-first deterministic safety gates and non-executable model output.
- Optional local language-model and speech runtime for privacy-preserving EdgeCare demonstrations.
- Truthful capability/readiness reporting instead of fabricated external integrations.

## Demonstration path

Use one uninterrupted, evidence-bound flow:

1. Open ZENDOC and sign in as a patient.
2. Search for a seeded/real verified ZENDOC provider using Universal Healthcare Search.
3. Point out the distinction between ZENDOC verified, official public directory and external map listings.
4. Open a verified ZENDOC provider profile.
5. Show published availability.
6. Request an available appointment slot.
7. Open Appointments and show the request status.
8. Show Health Memory / records / timeline as the continuity layer.
9. Open ZENDOC AI and demonstrate a low-risk care-navigation request.
10. If using local EdgeCare voice, speak a short request, review the transcript, then manually press Send.
11. Show the owner EdgeCare/readiness view only if it helps explain privacy and safety boundaries.

Do not demonstrate fake external booking. Public-directory and external-map results remain discovery references unless explicitly connected.

## Evaluation mapping

### Innovation

- One-box healthcare discovery with source-truth separation.
- Longitudinal Health Memory joined to care-navigation workflows.
- Deterministic-first healthcare safety instead of model-first autonomy.
- Local AI/voice option designed for privacy and resilience while preserving manual review.

### Scalability

- Provider/public-data ingestion architecture with provenance.
- PostgreSQL production path and migration/readiness checks.
- Role/tenant/access controls and partner API foundations.
- Geographic architecture designed to expand while measuring real imported coverage rather than claiming schema coverage as data coverage.

### Market potential

Frame this as the opportunity ZENDOC is pursuing. Do not invent market size, customers, partnerships, revenue, or paid pilots. Any traction numbers included in an application must come from actual records.

### Team capability

Use factual founder/team bios only. Distinguish engineering prototypes, competition work, academic projects and healthcare-domain collaborators from employed staff or formal clinical advisors.

### Impact

Potential impact areas that can be described as goals rather than proven outcomes:

- less friction finding appropriate care;
- stronger continuity between search, booking and health records;
- clearer provenance and verification labels;
- privacy-preserving AI assistance;
- improved access in low-bandwidth or local-runtime scenarios.

Do not claim measured clinical outcomes, cost savings, diagnostic accuracy, reduced mortality, regulatory compliance certification, or population-scale impact without evidence.

## Evidence to prepare

Before submission, retain:

- exact Git commit SHA used for the demo;
- green GitHub Actions result for that SHA;
- Render/public deployment URL and readiness evidence for the deployed `main` revision;
- local EdgeCare demo evidence separately if the local AI runtime is not hosted on Render;
- screenshots/video of the search → verified profile → available slot → appointment flow;
- screenshots/video of Health Memory and safety-aware AI;
- actual pilot/user/traction evidence if any;
- incorporation/India-registration evidence required by the organizer;
- team bios;
- architecture diagram and pitch deck if requested by the form.

## Deployment truth

The current Render service is configured from the production `main` branch. The isolated `competition/edgecare-ai-2026` branch contains competition-specific local AI/runtime work and must not be described as deployed on Render unless it is actually merged/deployed and verified.

For a submission using both links, describe them accurately:

- **Render:** stable web product / production core.
- **GitHub competition branch or PR:** EdgeCare competition implementation and engineering evidence.
- **Recorded local demo:** local LLM/ASR behavior when that runtime is executed on the demo laptop.

## Final no-fabrication gate

Do not submit any statement that turns a target into evidence. In particular:

- configured Snapdragon target != Snapdragon execution proof;
- local CPU Whisper != NPU proof;
- public provider listing != verified provider;
- appointment request != provider confirmation;
- schema/geography support != complete India data coverage;
- prototype workflow != hospital deployment;
- competition submission != clinical validation or regulatory approval.
