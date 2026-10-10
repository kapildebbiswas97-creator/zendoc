# Google Stitch / Canvas / AI Studio frontend intake — 2026-10-11

## Outcome of this PR

This is an **additive, reviewed-code frontend integration** that applies the visual language of the supplied Google Stitch designs to the existing production-capable **Flask + Jinja** site. It does **not** replace the current application with the AI Studio React prototype. In particular, authentication, appointments, live provider search, privacy protections, Health Memory, roles, URLs, backend, AWS/Vercel infrastructure, and existing JavaScript remain unchanged.

The integrated, production-facing changes proposed in this review branch are:

- `static/stitch-refresh.css`: navy/teal/mint refinement, improved landing CTAs and text hierarchy, navigation focus treatment, and restrained finder/provider surface polish.
- `templates/base.html`: loads the new sheet **after** existing styles, and reorders all six patient mobile dock shortcuts to make Find Care prominent while preserving linked endpoints.
- `templates/dashboard.html`: patient-only search panel and real care shortcuts; existing dashboard and live patient state remain unchanged.
- `templates/finder.html`: new discovery introduction, refined existing search form and result card classes. Search sources, map, source health, query, location and advanced filters remain untouched.
- `templates/provider_detail.html`: conventional branded promotional presentation from existing provider data, with contact/availability links. Existing appointment and schedule forms, CSRF handling and patient access remain intact.
- `tests/test_stitch_refresh_assets.py`: Jinja parse and static regression checks for role routing, live data, presentation, mobile navigation and accessibility.

## User-supplied source inventory

| Source | Content | Integration decision |
| --- | --- | --- |
| `Pasted text(20261010-195736).txt` | Stitch HTML for mobile clinical user interface | Use visual language / mobile design reference; do not deploy unverified copy |
| `Pasted text (2).txt` | Stitch HTML clinical search/home experience | Use search design reference; keep live Flask search form |
| `Pasted text (3).txt` | Stitch HTML Find Care / directory experience | Use card, spacing and directory reference; keep real search endpoints |
| `Pasted text (4).txt` | Stitch HTML hospital profile example | Use presentation reference; never publish its sample hospital/credentials as real |
| `zendoc---healthcare-&-clinical-care-platform.zip` | Vite + React + TypeScript application with mock data, components and pages | Keep as **isolated design prototype only** |
| `zendoc-frontend-prototype.zip` | README, tokens, component inventory and integration mapping | Documentation reference only; it contains no React source |

### Design vocabulary

- Core navy: `#001229` / `#0F2744`
- Accent teal: `#006A61`
- Mint: `#89F5E7`
- Canvas: `#FAF8FF`
- Inter typography and spacious, rounded surfaces
- Responsive narrow-screen layouts and visible keyboard focus
- Prefer no stock videos, no intrusive animation, and reduced-motion support

## Important integration risks in the exported prototype

1. `src/services/apiAdapter.ts` declares `USE_MOCK_FALLBACK = true`, so its displayed appointments, triage, records, doctors, hospitals, and queue figures are simulated.
2. The React app is controlled by `useState<NavTab>`, not the existing Flask/Jinja routes. Mounting it at `/` would displace server-rendered pages, role-aware navigation, login flows, and backend forms.
3. Export documentation lists suggested endpoints such as `/api/v1/search/omni`, `/api/v1/abha/records` and `/api/v1/appointments/book` without proving the current production application exposes their described contracts. **Do not treat this mapping as authoritative.**
4. Prototype content includes unverified ABDM / NHA / NABH / NABL / JCI affiliations, sample hospital details, ABHA credentials, ambulance tracking, and demo booking or clinical activities. **Do not turn demo text into verified product claims.**
5. Several exported Stitch documents use `href="#"` links and CDN Tailwind. Replace with existing Flask `url_for(...)` routes and audited production styles, not placeholder links.
6. Avoid adding any real patient data or production secrets to AI Studio, free-tier model prompts, or frontend bundles.

## Completed here and remaining release gates

1. **Implemented:** existing-route patient search, patient shortcuts, real-source directory polish, dynamic provider showcase, and six-link mobile dock.
2. **Implemented:** additive stylesheet, responsive breakpoints, keyboard focus treatment, and reduced-motion rules.
3. **Still required:** full GitHub Production Gate CI success for the final commit; confirm no backend regression.
4. **Still required:** real Flask-rendered desktop/mobile screenshots (at 375px, 768px and 1440px), keyboard/focus navigation, color contrast, dark mode, search/map behavior, and appointment requests in authorized staging sessions.
5. **Still required:** preview deployment health verification. No production rollout or merge until tests and visual approval are complete.
6. **Future separate scope:** provider-managed advertising content and paid subscriptions, if required, need audited persistence and authorization; this PR only presents already published provider profile data and does not add an editor/billing.

## Review / rollout notes

- This PR has no new dependencies, external APIs, database migrations, credential changes, or build system changes.
- It does not establish real ABDM integration or clinical outcomes.
- The front-end remains Flask/Jinja until a separately tested architectural migration is approved.
