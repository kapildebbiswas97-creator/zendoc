# Google Stitch / Canvas / AI Studio frontend intake — 2026-10-11

## Outcome of this PR

This is an **additive, review-only first pass** that applies the visual language of the supplied Google Stitch designs to the existing production-capable **Flask + Jinja** site. It does **not** replace the current application with the AI Studio React prototype. In particular, authentication, appointments, live provider search, privacy protections, Health Memory, roles, URLs, backend, AWS/Vercel infrastructure, and existing JavaScript remain unchanged.

The only rendered production-facing changes proposed here are:

- `static/stitch-refresh.css`: navy/teal/mint refinement, improved landing CTAs and text hierarchy, navigation focus treatment, and restrained finder/provider surface polish.
- `templates/base.html`: loads the new sheet **after** the existing stylesheets, preserving existing rules and templates.

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

## Next integration stages (separate reviewed PRs)

1. Audit live routes and response contracts from existing Flask blueprints and tests before touching React API adapters.
2. Add provider promotional sections to the current `provider_detail.html` using genuine reviewed profile content. Hospitals, clinics, pharmacies and stores receive **ordinary curated advertising pages**, not AI-generated customer websites.
3. Selectively migrate design elements such as search cards, doctor cards, empty states and mobile navigation into existing templates. Preserve existing CSRF tokens, POST actions, accessibility labels, role-aware navigation, and verification states.
4. Validate desktop/mobile screenshots, contrast, keyboard navigation, focus, booking and search flows, and dark mode.
5. Run the existing backend and deployment gates. Do not merge or deploy until the PR review and tests pass.

## Review / rollout notes

- This PR has no new dependencies, external APIs, database migrations, credential changes, or build system changes.
- It does not establish real ABDM integration or clinical outcomes.
- The front-end remains Flask/Jinja until a separately tested architectural migration is approved.
