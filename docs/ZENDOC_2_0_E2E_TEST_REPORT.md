# ZENDOC 2.0 — End-to-End (E2E) Test Automation Report

> Date: 2026-11-08  
> Test Framework: Playwright (`@playwright/test` v1.65.0)  
> Engine: Chromium Headless Shell  
> Execution Target: Next.js 15 App Router (`http://localhost:3000`)

---

## 1. Test Architecture & Directory Structure

Playwright automated tests are located in `./e2e` and isolated into specific domain specifications:

```
e2e/
├── home-and-navigation.spec.ts   # Public routing, Emergency Banner, and Navbar link integrity
├── auth-pages.spec.ts            # Sign-in and patient registration constraints and DOM validation
├── patient-portal.spec.ts        # Dashboard, Vitals, Health Memory, Medical Records, Trust Center
├── ai-advisory.spec.ts           # ZENDOC AI query submission, red-flag emergency diversion, and advice
└── discovery.spec.ts             # Find Care doctor and facility search filters
```

---

## 2. Test Specifications & Verification Matrix

| Spec File | Test Case | Target Capability |
|---|---|---|
| `home-and-navigation.spec.ts` | Renders homepage with brand, emergency banner, and key capabilities | Global layout, 102/108/112 hotlines, healthcare disclaimer |
| `home-and-navigation.spec.ts` | Navbar provides direct navigation to key portals | Desktop navigation bar, routing links to `/dashboard`, `/find-care`, `/memory`, etc. |
| `auth-pages.spec.ts` | Login page displays secure credentials form | Form structure, email input, password field, link to `/register` |
| `auth-pages.spec.ts` | Registration page validates input constraints | Full name, email, phone, and minimum password length constraint (`minlength="10"`) |
| `patient-portal.spec.ts` | Patient dashboard loads clinical overview modules | `/dashboard` clinical view, cards, action items |
| `patient-portal.spec.ts` | Health vitals page renders biomarkers tracker | `/vitals` systolic/diastolic, glucose, heart rate |
| `patient-portal.spec.ts` | Longitudinal health memory page loads timeline view | `/memory` event history and clinical chronology |
| `patient-portal.spec.ts` | Medical records vault renders document list and upload link | `/records` vault listing and link to `/records/upload` |
| `patient-portal.spec.ts` | Trust center renders privacy and consent controls | `/trust-center` consent grants and HIPAA/DPDP privacy |
| `ai-advisory.spec.ts` | Renders AI advisor interface with educational disclaimer | `/ai` advisory input, safety status badge, disclaimer |
| `ai-advisory.spec.ts` | Intercepts acute life-threatening emergency and triggers instant hotline escalation | Critical emergency detection ("crushing chest pain"), Red banner with direct dial links |
| `ai-advisory.spec.ts` | Processes benign dietary inquiry with clinical advisory guidance | Educational advice formulation, structured dietary recommendations |
| `discovery.spec.ts` | Renders verified healthcare provider and facility search filters | `/find-care` directory, doctors/clinics tabs, search bar |

---

## 3. Separation of Test Suites

ZENDOC 2.0 maintains a strict separation between Unit/Integration testing and Browser End-to-End testing:

- **Vitest Unit & Integration Suite (`npm run test`):**
  - Fast, in-memory execution via jsdom.
  - 10 test files, 115 passing tests.
  - Covers cryptographic HMAC math, schema invariants, triage regex patterns, Zod validation schemas, and IDOR boundary logic.
- **Playwright End-to-End Suite (`npm run test:e2e`):**
  - Full headless browser rendering.
  - Validates interactive DOM state, accessibility attributes, navigation, and client-server API roundtrips.
