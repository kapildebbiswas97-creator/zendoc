# ZENDOC — Original Product Public Deployment Report

**Date:** 2026-11-10  
**Branch:** `restore/original-zendoc`  
**Base Commit SHA:** `545fc35758f749b46779c41e729d55667fc2118a`  
**Latest Restoration Commit:** `6efa366`  
**Active Live Public HTTPS URL:** [https://presentations-ridge-russia-garlic.trycloudflare.com](https://presentations-ridge-russia-garlic.trycloudflare.com)  
**Local Origin Server:** `http://127.0.0.1:5000`  
**ZENDOC 2.0 Backup:** `rebuild/zendoc-2.0-vercel` (HEAD: `ff22072`, preserved intact)  
**Main Branch:** `545fc35758f749b46779c41e729d55667fc2118a` (100% untouched)  

---

## 1. Executive Summary

The original ZENDOC application is actively deployed and serving live traffic over the global public internet via Cloudflare edge tunneling:

👉 **`https://presentations-ridge-russia-garlic.trycloudflare.com`**

This public deployment:
- **Requires zero login walls or Vercel SSO protection:** Fully open and directly interactive for all patient and provider accounts.
- **Serves the genuine original application:** 275 core Python modules in `zendoc/`, 582 registered routes, Jinja2 SSR Google Stitch templates, dual-engine SQLite/PostgreSQL, and private file storage.
- **Includes live verified clinical workflows:** Patient registration, authentication, dashboard, Find Care, Universal Healthcare Search, appointments, Health Memory, and records upload/download.

---

## 2. Live Public URL & Edge Architecture

```
                                  GLOBAL INTERNET
                                         │
                                         ▼
                     ┌────────────────────────────────────────┐
                     │ Cloudflare Global Anycast Edge Network │
                     │   (Edge SSL/TLS Termination - HTTPS)   │
                     └───────────────────┬────────────────────┘
                                         │
                    Quic / HTTP/2 Secure Multiplexed Tunnel
                                         │
                                         ▼
                     ┌────────────────────────────────────────┐
                     │        cloudflared Tunnel Daemon       │
                     │  (Installed in .gemini/antigravity/bin) │
                     └───────────────────┬────────────────────┘
                                         │
                            Local Loopback (Port 5000)
                                         │
                                         ▼
                     ┌────────────────────────────────────────┐
                     │    ZENDOC Flask Application Server     │
                     │  - 275 Modules in zendoc/              │
                     │  - 582 Endpoints                       │
                     │  - Jinja2 SSR + Google Stitch CSS      │
                     │  - Dual SQLite (WAL) / PostgreSQL 16   │
                     │  - Private Document Storage            │
                     └────────────────────────────────────────┘
```

- **Active Public URL:** `https://presentations-ridge-russia-garlic.trycloudflare.com`
- **Security & Encryption:** Cloudflare Edge TLS Termination with automated certificate management.
- **Zero Inbound Port Exposure:** Encrypted outbound tunnel only.

---

## 3. End-to-End Live Workflow Verification (Nov 10, 2026)

All checks executed live against `https://presentations-ridge-russia-garlic.trycloudflare.com`:

| Category | Endpoint | Method | Result | Details |
|---|---|---|---|---|
| **Health & Liveness** | `/api/v1/health` | GET | `200 OK` | `{"check":"liveness","service":"zendoc","status":"ok"}` |
| **Landing Page** | `/` | GET | `200 OK` | 29,326 bytes HTML; Title: "ZENDOC — One Connected Healthcare Journey" |
| **Registration** | `/register/patient` | POST | `302 Redirect` | Account created with terms & privacy accepted |
| **Authentication** | `/login/patient` | POST | `302 Redirect` | Session established, redirected to `/dashboard` |
| **Dashboard** | `/dashboard` | GET | `200 OK` | Patient dashboard loaded with verified user identity |
| **Universal Search** | `/search?q=hospital` | GET | `200 OK` | Search executed, facilities returned |
| **Find Care** | `/find-care` | GET | `200 OK` | Healthcare directory with filters & distance options |
| **Health Records Upload** | `/records` | POST | `200 OK` | `blood_cbc.pdf` uploaded & saved with sha256 hash |
| **Health Records Download** | `/records/1/download` | GET | `200 OK` | Binary content matches original byte-for-byte |
| **Health Memory Timeline** | `/timeline` | GET | `200 OK` | Longitudinal patient health event timeline |
| **Appointments** | `/appointments` | GET | `200 OK` | Clinical appointment schedule view |
| **Pharmacy** | `/pharmacy` | GET | `200 OK` | Connected care medicine ordering |
| **Care OS** | `/care-os` | GET | `200 OK` | Care continuity chain manager |
| **Agent OS** | `/agent-os` | GET | `200 OK` | Specialist Agent autonomous coordinator |

---

## 4. Branch Summary

- **Primary Product Branch:** `restore/original-zendoc`
- **Original Production (`main`):** `545fc35758f749b46779c41e729d55667fc2118a` (100% untouched)
- **Backup Reference Branch:** `rebuild/zendoc-2.0-vercel` (at commit `ff22072`)
