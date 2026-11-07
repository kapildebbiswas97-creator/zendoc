# ZENDOC 2.0 — External Integration Checklist

> Status key: ✅ Ready | ⚙️ Partial | 🔑 Needs credentials | ❌ Not started

---

## 1. Supabase (Primary Platform)

| Item | Status | Action Required |
|------|--------|----------------|
| Supabase project created | 🔑 | Create project at supabase.com |
| `NEXT_PUBLIC_SUPABASE_URL` set in Vercel | 🔑 | Copy from Project Settings → API |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` set | 🔑 | Copy from Project Settings → API |
| `SUPABASE_SERVICE_ROLE_KEY` set (server-only) | 🔑 | Copy from Project Settings → API |
| `DATABASE_URL` set (pooler connection string) | 🔑 | Copy from Project Settings → Database |
| Migration SQL applied | 🔑 | Run `20261107000000_zendoc_2_0_core_schema.sql` followed by `20261108000000_zendoc_2_0_schema_corrections.sql` in SQL Editor |
| RLS policies verified | 🔑 | Run `SELECT * FROM pg_policies;` in SQL Editor |
| `medical-records` Storage bucket created | 🔑 | Storage → New Bucket → `medical-records` → Private |
| Storage bucket RLS policy applied | 🔑 | Restrict to `auth.uid() = owner` |
| Email confirmation enabled | 🔑 | Auth → Settings → Email Confirmations |
| Auth redirect URL set | 🔑 | Auth → Settings → Redirect URLs → add `https://your-domain.vercel.app/api/auth/callback` |
| `profiles` table trigger created | ✅ | Authored in `20261108000000_zendoc_2_0_schema_corrections.sql` (`handle_new_user()`) |

---

## 2. Vercel (Hosting)

| Item | Status | Action Required |
|------|--------|----------------|
| Vercel project imported from GitHub | 🔑 | vercel.com → New Project → import `zendoc` repo |
| Branch `rebuild/zendoc-2.0-vercel` set as production | 🔑 | Project Settings → Git → Production Branch |
| All env vars from `.env.example` added to Vercel | 🔑 | Project Settings → Environment Variables |
| Preview deployments enabled | ✅ | Default Vercel behavior |
| `NEXT_PUBLIC_APP_URL` set to production domain | 🔑 | Add after first deploy |

---

## 3. AI Advisory Provider (Optional)

| Item | Status | Action Required |
|------|--------|----------------|
| `ZENDOC_AI_PROVIDER` env var set | ⚙️ | Defaults to `mock` — works without API key |
| Anthropic Claude API key | 🔑 | console.anthropic.com → set `ZENDOC_AI_API_KEY` |
| OpenAI API key (alternative) | 🔑 | platform.openai.com → set `ZENDOC_AI_API_KEY` |
| Google Gemini API key (alternative) | 🔑 | ai.google.dev → set `ZENDOC_AI_API_KEY` |
| `ZENDOC_AI_MODEL` configured | ⚙️ | Defaults to `claude-3-5-sonnet-20241022` |
| `ZENDOC_AI_TIMEOUT` configured | ✅ | Defaults to `20` seconds |

---

## 4. Python Worker (Standalone Microservice)

| Item | Status | Action Required |
|------|--------|----------------|
| `PYTHON_WORKER_ENABLED` | ⚙️ | Defaults to `false` — set to `true` to activate |
| Python worker microservice (`worker/`) | ✅ | Standalone Dockerized Flask service with HMAC-SHA256, Whisper ASR & OCR |
| Dockerfile & Compose orchestration | ✅ | `worker/Dockerfile` and `docker-compose.worker.yml` with non-root security |
| Pytest worker test suite | ✅ | 7/7 tests passing (`tests/test_worker_api.py`, `tests/test_smoke.py`) |
| `PYTHON_WORKER_URL` set | 🔑 | Deploy `worker/` to AWS ECS / Fly.io / Render and set URL |
| `PYTHON_WORKER_SECRET` shared secret set | 🔑 | Set matching 32-byte secret on Next.js and Worker |
| Worker `/api/health` endpoint responding | ✅ | Implemented in `worker/app.py` & verified via `/api/workers/health` |

---

## 5. Distributed Abuse Prevention & Rate Limiting

| Item | Status | Action Required |
|------|--------|----------------|
| Upstash Redis REST integration | ✅ | Built in `src/lib/security/rate-limiter.ts` |
| Emergency triage rate-limit bypass | ✅ | Life-safety invariant: Emergency red-flags bypass rate limiting completely |
| Automatic in-memory sliding window fallback | ✅ | Fail-open / graceful fallback verified under network partition |
| Route rate limiting: AI Chat (10/min) | ✅ | Configured in `src/app/api/ai/chat/route.ts` |
| Route rate limiting: Uploads (20/min) | ✅ | Configured in `src/app/api/records/upload/route.ts` |
| Route rate limiting: Worker ASR/OCR (15/min)| ✅ | Configured in `src/app/api/workers/asr/route.ts` & `ocr/route.ts` |
| `UPSTASH_REDIS_REST_URL` set | 🔑 | Create free database at console.upstash.com |
| `UPSTASH_REDIS_REST_TOKEN` set | 🔑 | Copy REST token to Vercel environment variables |

---

## 6. Structured Healthcare Monitoring & Privacy

| Item | Status | Action Required |
|------|--------|----------------|
| Structured JSON logger | ✅ | Implemented in `src/lib/monitoring/logger.ts` |
| Automated PHI de-identification (HIPAA/DPDP) | ✅ | Regex filters redact emails, phone numbers, Aadhaar, SSN, cards, tokens |
| Operation latency stopwatch | ✅ | High-resolution elapsed timing helper for SLA tracking |
| Deployment diagnostic health endpoint | ✅ | `GET /api/health` reporting runtime, memory, and subsystem states |

---

## 7. Payments — Razorpay (Integration Required)

| Item | Status | Action Required |
|------|--------|----------------|
| Razorpay account created | ❌ | razorpay.com → Business account |
| `RAZORPAY_KEY_ID` set | 🔑 | Dashboard → API Keys |
| `RAZORPAY_KEY_SECRET` set | 🔑 | Dashboard → API Keys |
| `RAZORPAY_WEBHOOK_SECRET` set | 🔑 | Dashboard → Webhooks → Reveal Secret |
| Webhook endpoint registered | ❌ | Add `https://your-domain/api/payments/webhook` in Razorpay dashboard |
| Webhook handler route created | ❌ | `src/app/api/payments/webhook/route.ts` — planned |
| Pharmacy order payment flow | ❌ | Requires Razorpay SDK integration |

---

## 6. Maps / Location — Google Maps Platform (Integration Required)

| Item | Status | Action Required |
|------|--------|----------------|
| Google Cloud project created | 🔑 | console.cloud.google.com |
| Maps JavaScript API enabled | 🔑 | APIs & Services → Enable |
| Places API enabled | 🔑 | For facility search autocomplete |
| `NEXT_PUBLIC_GOOGLE_MAPS_KEY` set | 🔑 | Credentials → API Key (restrict to domain) |
| Facility PostGIS nearest-neighbor query | ⚙️ | Schema has `geography` columns — query written |
| Find Care map view | ❌ | Requires Maps embed in `find-care` page |

---

## 7. Email Notifications (Integration Required)

| Item | Status | Action Required |
|------|--------|----------------|
| Email provider chosen (Resend recommended) | ❌ | resend.com |
| `RESEND_API_KEY` or `SENDGRID_API_KEY` set | 🔑 | Provider dashboard |
| Appointment confirmation email | ❌ | Trigger from `bookAppointment` action |
| Account welcome email | ❌ | Trigger from `signUpAction` |
| Prescription-ready notification | ❌ | Planned |

---

## 8. Video Consultation — WebRTC (Integration Required)

| Item | Status | Action Required |
|------|--------|----------------|
| TURN server provider chosen (e.g. Twilio, Metered) | ❌ | For NAT traversal in production |
| `TURN_SERVER_URL` set | 🔑 | Provider dashboard |
| `TURN_SERVER_CREDENTIAL` set | 🔑 | Provider dashboard |
| Video room creation API | ❌ | Planned — `src/app/api/video/room/route.ts` |
| In-app WebRTC signalling | ❌ | Planned |

---

## 9. Push Notifications (Future)

| Item | Status | Action Required |
|------|--------|----------------|
| FCM / APNS credentials | ❌ | Future feature |
| Web push VAPID keys | ❌ | Future feature |

---

## Credential Acquisition Summary

To go from zero to functional with **live database + auth** (minimum viable):

```
1. supabase.com   → Create project → copy URL + anon key + service role key
2. Supabase SQL Editor → Paste migration SQL → Run
3. Supabase Storage → Create bucket "medical-records" (private)
4. Supabase Auth → Settings → Add Vercel redirect URL
5. vercel.com → Import repo → Set env vars → Deploy
```

That alone enables: registration, login, session persistence, protected routes,
patient dashboard, health metrics, medical records, appointments, consent management.

Everything else in this checklist enables additional integrations progressively.
