# Family Lifecycle & Competitive Gap Plan

Updated: 2026-09-17

This document records product patterns ZENDOC can learn from without claiming any integration, partnership, copied implementation, or clinical equivalence.

## Existing competitive atlas baseline

The existing ZENDOC competitive atlas already covers broad consumer health, Indian super-apps, national digital-health rails, health AI, specialty clinical AI, wearables, remote monitoring and clinician workflow companies. The strategic direction remains: do not recreate every competitor product. ZENDOC should own consented longitudinal context, verified care actions, family/caregiver coordination, affordability discovery and outcomes across providers.

## Additional family/lifecycle benchmarks reviewed

### Maven Clinic

Public source: https://www.mavenclinic.com/

Observed pattern: structured family journeys spanning fertility/family building, maternity/newborn, parenting/pediatrics and menopause/midlife, with employer/health-plan distribution.

ZENDOC learning: make life-stage care a first-class navigation layer rather than a generic family list. Do not copy clinical programs; use deterministic care organization and verified local-provider handoffs.

### Pomelo Care

Public source: https://www.pomelocare.com/

Observed pattern: coordinated virtual care across pregnancy, postpartum/newborn and perimenopause/menopause, designed to work alongside in-person providers.

ZENDOC learning: a pregnancy journey must be explicitly selected and should organize records, appointments, care tasks and follow-through. Pregnancy must never be inferred from gender, age or model output.

### Birdie

Public source: https://www.birdie.care/product-features/family-app

Observed pattern: family members can see care activity remotely; family access is read-only by default and revocable.

ZENDOC learning: remote-parent/cross-border family care should rely on explicit scoped consent. Relationship alone must never confer permission. Existing ZENDOC family access grants remain the authorization source of truth.

### Blueberry Pediatrics

Public source: https://www.blueberrypediatrics.com/

Observed pattern: household pediatric membership, 24/7 pediatric access, developmental screening and optional home measurement tools.

ZENDOC learning: a child-care journey should follow age stages and preserve pediatric records and follow-through. ZENDOC must not imitate diagnosis, prescribing or home-device claims without licensed clinicians, validated devices and real integrations.

### Included Health

Public source: https://includedhealth.com/

Observed pattern: care navigation combines clinical access, benefits understanding, billing advocacy and second-opinion/navigation services.

ZENDOC learning: CareFin and care navigation can meet at a deterministic affordability layer, but benefit eligibility, approval and payment must remain evidence-backed rather than model-decided.

### Honor / Home Instead

Public source: https://www.honorcare.com/

Observed pattern: aging-at-home support includes companionship, transportation, medication reminders and help with activities of daily living.

ZENDOC learning: older-adult support should coordinate tasks and verified services while distinguishing a family reminder from a provider-confirmed service.

## Product gaps to implement safely

1. **Life-stage family navigation**
   - Early childhood (0–2)
   - Preschool (3–5)
   - Child (6–11)
   - Adolescent (12–17)
   - Young adult (18–39)
   - Midlife (40–64)
   - Older adult (65+)
   - Exact newborn/infant milestone timing requires date of birth; integer age alone is insufficient.

2. **Remote family / cross-border coordination**
   - Keep existing explicit family access grants as the authorization source.
   - Never infer consent from being a parent, child, spouse or caregiver.
   - Prefer read-only visibility for observers; write/action scopes must be separately granted.

3. **Pregnancy, postpartum and newborn journey**
   - User-selected only.
   - Never infer pregnancy.
   - Organize care; do not let a model diagnose, prescribe, change medicines or execute emergency actions.

4. **Child growth and pediatric continuity**
   - Age-stage navigation, records, tasks and verified-provider handoffs.
   - No autonomous diagnosis or prescribing.

5. **Adult and older-adult continuity**
   - Keep portable longitudinal context and care tasks across provider changes.
   - For remote parents, separate family-reported state, patient-reported state and provider-confirmed state.

6. **Subscription categories before billing**
   - Family Essentials
   - Remote Parent & Family
   - Pregnancy, Postpartum & Newborn
   - Child Growth & Pediatrics
   - Adult Continuity
   - Older Adult Support
   - These are currently care categories, not purchasable plans.

7. **Payment integration boundary**
   - Candidate methods: UPI, cards, net banking, supported wallets and employer/insurer benefit pathways.
   - Do not accept payment until a real gateway is integrated and verified.
   - Never store CVV, UPI PIN or banking passwords.
   - Model output must never initiate payment, change payment permissions or mark a payment successful.
   - Payment/coverage state transitions require deterministic gateway or authoritative evidence.

## Explicit non-integrations

None of the companies above are integrated with ZENDOC by this work. Their public product patterns are references only. A future integration requires a documented API/partner agreement, authentication, consent mapping, failure handling, provenance and integration-specific tests.
