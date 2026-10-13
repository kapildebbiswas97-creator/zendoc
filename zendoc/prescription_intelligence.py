"""Standardized Prescription Intelligence v2 status projection.

This layer does not re-extract or prescribe. It projects stored prescription
items into explicit safety stages for UI/agent orchestration.
"""
from __future__ import annotations

from typing import Any

from .prescription_service import get_prescription


EXTRACTED = "EXTRACTED"
LOW_CONFIDENCE = "LOW_CONFIDENCE"
AMBIGUOUS = "AMBIGUOUS"
REVIEW_REQUIRED = "REVIEW_REQUIRED"
MATCHED = "MATCHED"
VERIFIED = "VERIFIED"
FULFILMENT_READY = "FULFILMENT_READY"


AUTONOMOUS_PRESCRIBING_MUST_REMAIN_DISABLED = True

KNOWN_DRUG_INTERACTIONS = [
    {
        "pair": ("warfarin", "aspirin"),
        "severity": "CRITICAL",
        "title": "Severe Bleeding Risk",
        "description": "Concurrent anticoagulant (Warfarin) and antiplatelet (Aspirin) therapy substantially increases major hemorrhage risk.",
    },
    {
        "pair": ("warfarin", "ibuprofen"),
        "severity": "CRITICAL",
        "title": "Severe Gastrointestinal Bleeding Risk",
        "description": "NSAIDs damage GI mucosa and impair platelet aggregation while Warfarin prevents coagulation.",
    },
    {
        "pair": ("ramipril", "spironolactone"),
        "severity": "HIGH",
        "title": "Hyperkalemia Risk",
        "description": "Co-administration of ACE inhibitors and potassium-sparing diuretics may induce life-threatening hyperkalemia.",
    },
    {
        "pair": ("telmisartan", "spironolactone"),
        "severity": "HIGH",
        "title": "Hyperkalemia Risk",
        "description": "Co-administration of ARBs and potassium-sparing diuretics may induce life-threatening hyperkalemia.",
    },
    {
        "pair": ("atorvastatin", "clarithromycin"),
        "severity": "HIGH",
        "title": "Rhabdomyolysis Risk",
        "description": "Clarithromycin strongly inhibits CYP3A4, elevating statin concentrations and risking severe myopathy/rhabdomyolysis.",
    },
    {
        "pair": ("simvastatin", "clarithromycin"),
        "severity": "HIGH",
        "title": "Rhabdomyolysis Risk",
        "description": "Clarithromycin elevates Simvastatin levels dramatically. Combination is strongly contraindicated.",
    },
    {
        "pair": ("sildenafil", "nitroglycerin"),
        "severity": "CRITICAL",
        "title": "Profound Hypotension Risk",
        "description": "PDE5 inhibitors potentiate the hypotensive effect of nitrates, risking cardiovascular collapse.",
    },
    {
        "pair": ("fluoxetine", "tramadol"),
        "severity": "HIGH",
        "title": "Serotonin Syndrome Risk",
        "description": "Co-prescribing serotonergic agents elevates central serotonin levels with risk of serotonin syndrome.",
    },
    {
        "pair": ("metformin", "contrast"),
        "severity": "HIGH",
        "title": "Lactic Acidosis Risk",
        "description": "Iodinated contrast can cause acute kidney injury, causing Metformin accumulation and lactic acidosis.",
    },
]

KNOWN_ALLERGY_FAMILIES = {
    "penicillin": ["amoxicillin", "ampicillin", "penicillin", "augmentin", "piperacillin", "clavulanate"],
    "sulfa": ["sulfamethoxazole", "cotrimoxazole", "bactrim", "sulfasalazine"],
    "nsaid": ["aspirin", "ibuprofen", "naproxen", "diclofenac", "ketorolac", "celecoxib", "indomethacin"],
}

KNOWN_CONDITION_CONTRAINDICATIONS = {
    "asthma": {
        "drugs": ["propranolol", "atenolol", "metoprolol", "carvedilol", "aspirin", "ibuprofen"],
        "reason": "Non-selective beta-blockers trigger severe bronchospasm; NSAIDs can trigger aspirin-exacerbated respiratory disease.",
    },
    "chronic_kidney_disease": {
        "drugs": ["ibuprofen", "diclofenac", "naproxen", "ketorolac"],
        "reason": "NSAIDs inhibit renal prostaglandins, precipitating acute kidney injury and fluid retention.",
    },
    "peptic_ulcer": {
        "drugs": ["aspirin", "ibuprofen", "diclofenac", "naproxen"],
        "reason": "NSAIDs disrupt gastric mucosal defenses, carrying high risk of GI ulceration and bleeding.",
    },
    "hypertension": {
        "drugs": ["pseudoephedrine", "phenylephrine"],
        "reason": "Sympathomimetic decongestants cause systemic vasoconstriction and acute blood pressure spikes.",
    },
}

KNOWN_DUPLICATE_THERAPY_CLASSES = {
    "nsaid": ["ibuprofen", "naproxen", "diclofenac", "aceclofenac", "indomethacin", "combiflam"],
    "ppi": ["omeprazole", "pantoprazole", "rabeprazole", "esomeprazole", "lansoprazole"],
    "ace_inhibitor": ["enalapril", "ramipril", "lisinopril", "captopril", "perindopril"],
    "arb": ["losartan", "telmisartan", "valsartan", "olmesartan", "candesartan"],
    "paracetamol": ["paracetamol", "acetaminophen", "crocin", "calpol", "dolo", "combiflam"],
}


def _clean_med(name: str | None) -> str:
    if not name:
        return ""
    import re
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def check_medication_safety(
    items: list[dict],
    patient_allergies: list[str] | None = None,
    patient_conditions: list[str] | None = None,
) -> dict[str, Any]:
    """
    Evaluates duplicate therapies, drug-drug interactions, allergy alerts, and condition contraindications.
    Strictly non-prescribing clinical decision support.
    """
    cleaned_meds = []
    for it in items:
        raw_name = str(it.get("medicine_name") or it.get("name") or "").strip()
        if raw_name:
            cleaned_meds.append({"raw": raw_name, "clean": _clean_med(raw_name), "item": it})

    alerts = []
    duplicate_therapies = []
    interactions = []
    allergy_alerts = []
    condition_alerts = []

    # 1. Duplicate therapy detection
    for class_name, drugs in KNOWN_DUPLICATE_THERAPY_CLASSES.items():
        matched = []
        for m in cleaned_meds:
            if any(d in m["clean"] for d in drugs):
                matched.append(m["raw"])
        if len(matched) > 1:
            alert = {
                "alert_type": "DUPLICATE_THERAPY",
                "class_name": class_name,
                "medications": matched,
                "severity": "MODERATE",
                "description": f"Multiple medications detected belonging to the same therapeutic class ({class_name}): {', '.join(matched)}. Verify intentional combination.",
            }
            duplicate_therapies.append(alert)
            alerts.append(alert)

    # 2. Drug-Drug Interactions
    for i in range(len(cleaned_meds)):
        for j in range(i + 1, len(cleaned_meds)):
            m1 = cleaned_meds[i]
            m2 = cleaned_meds[j]
            for ddi in KNOWN_DRUG_INTERACTIONS:
                p1, p2 = ddi["pair"]
                if (p1 in m1["clean"] and p2 in m2["clean"]) or (p2 in m1["clean"] and p1 in m2["clean"]):
                    interaction = {
                        "alert_type": "DRUG_INTERACTION",
                        "pair": [m1["raw"], m2["raw"]],
                        "severity": ddi["severity"],
                        "title": ddi["title"],
                        "description": ddi["description"],
                    }
                    interactions.append(interaction)
                    alerts.append(interaction)

    # 3. Allergy Contraindications
    if patient_allergies:
        normalized_allergies = [str(a).strip().lower() for a in patient_allergies if a]
        for m in cleaned_meds:
            for allergy_family, drugs in KNOWN_ALLERGY_FAMILIES.items():
                if any(allergy_family in a for a in normalized_allergies):
                    if any(d in m["clean"] for d in drugs):
                        al_alert = {
                            "alert_type": "ALLERGY_CONTRAINDICATION",
                            "medication": m["raw"],
                            "allergy_family": allergy_family,
                            "severity": "CRITICAL",
                            "description": f"Patient has declared allergy to '{allergy_family}'. Medication '{m['raw']}' belongs to this class.",
                        }
                        allergy_alerts.append(al_alert)
                        alerts.append(al_alert)

    # 4. Condition Contraindications
    if patient_conditions:
        normalized_conds = [str(c).strip().lower() for c in patient_conditions if c]
        for m in cleaned_meds:
            for cond_key, cond_info in KNOWN_CONDITION_CONTRAINDICATIONS.items():
                if any(cond_key in c for c in normalized_conds):
                    if any(d in m["clean"] for d in cond_info["drugs"]):
                        cd_alert = {
                            "alert_type": "CONDITION_CONTRAINDICATION",
                            "medication": m["raw"],
                            "condition": cond_key,
                            "severity": "HIGH",
                            "description": f"Medication '{m['raw']}' carries known risk in patients with {cond_key.replace('_', ' ')}: {cond_info['reason']}",
                        }
                        condition_alerts.append(cd_alert)
                        alerts.append(cd_alert)

    return {
        "safe": len([a for a in alerts if a["severity"] in {"CRITICAL", "HIGH"}]) == 0,
        "critical_alerts_count": len([a for a in alerts if a["severity"] == "CRITICAL"]),
        "high_alerts_count": len([a for a in alerts if a["severity"] == "HIGH"]),
        "moderate_alerts_count": len([a for a in alerts if a["severity"] == "MODERATE"]),
        "duplicate_therapies": duplicate_therapies,
        "interactions": interactions,
        "allergy_alerts": allergy_alerts,
        "condition_alerts": condition_alerts,
        "all_alerts": alerts,
        "disclaimer": (
            "Clinical decision support only. ZENDOC does not autonomously prescribe or modify medications. "
            "All prescription decisions remain the sole legal and clinical responsibility of the licensed human physician."
        ),
    }


def reconcile_prescriptions(current_items: list[dict], existing_items: list[dict]) -> dict[str, Any]:
    """
    Performs medication reconciliation comparing a new prescription against historical active regimens.
    """
    curr_cleaned = {_clean_med(it.get("medicine_name") or it.get("name")): it for it in current_items if it.get("medicine_name") or it.get("name")}
    hist_cleaned = {_clean_med(it.get("medicine_name") or it.get("name")): it for it in existing_items if it.get("medicine_name") or it.get("name")}

    continued = []
    new_meds = []
    discontinued_or_prior = []

    for key, it in curr_cleaned.items():
        if key in hist_cleaned:
            continued.append({
                "medicine_name": it.get("medicine_name") or it.get("name"),
                "status": "CONTINUED",
                "current_dosage": it.get("dosage"),
                "prior_dosage": hist_cleaned[key].get("dosage"),
            })
        else:
            new_meds.append({
                "medicine_name": it.get("medicine_name") or it.get("name"),
                "status": "NEW_PRESCRIPTION",
                "dosage": it.get("dosage"),
            })

    for key, it in hist_cleaned.items():
        if key not in curr_cleaned:
            discontinued_or_prior.append({
                "medicine_name": it.get("medicine_name") or it.get("name"),
                "status": "NOT_IN_CURRENT_PRESCRIPTION",
                "prior_dosage": it.get("dosage"),
            })

    return {
        "status": "RECONCILED",
        "continued_medications": continued,
        "new_medications": new_meds,
        "unmentioned_prior_medications": discontinued_or_prior,
        "total_current": len(curr_cleaned),
        "total_prior": len(hist_cleaned),
    }


def prescription_intelligence_state(prescription_id: int, actor: Any = None) -> dict:
    prescription = get_prescription(int(prescription_id), actor=actor)
    raw_items = prescription.get("items", [])
    projected = [_project_item(item) for item in raw_items]

    if not projected:
        overall = REVIEW_REQUIRED
    elif any(item["stage"] in {LOW_CONFIDENCE, AMBIGUOUS, REVIEW_REQUIRED} for item in projected):
        overall = REVIEW_REQUIRED
    elif all(item["stage"] == FULFILMENT_READY for item in projected):
        overall = FULFILMENT_READY
    elif all(item["stage"] in {VERIFIED, FULFILMENT_READY} for item in projected):
        overall = VERIFIED
    else:
        overall = MATCHED

    # Run medication safety check
    safety_analysis = check_medication_safety(raw_items)

    return {
        "prescription_id": prescription["id"],
        "overall_stage": overall,
        "needs_review": overall == REVIEW_REQUIRED,
        "fulfilment_ready": overall == FULFILMENT_READY,
        "items": projected,
        "safety": {
            "autonomous_prescribing": False,
            "automatic_substitution": False,
            "automatic_dose_change": False,
            "automatic_frequency_change": False,
            "automatic_form_change": False,
            "automatic_order_submission": False,
        },
        "safety_analysis": safety_analysis,
    }


def _project_item(item: dict) -> dict:
    confidence = _confidence(item.get("extraction_confidence"))
    review = str(item.get("review_status") or "").strip().lower()
    sku_id = item.get("sku_id")
    medicine_name = str(item.get("medicine_name") or "").strip()

    if not medicine_name:
        stage = AMBIGUOUS
        reason = "Medicine name is empty/ambiguous."
    elif confidence < 0.75:
        stage = LOW_CONFIDENCE
        reason = "Extraction confidence is below the safe review threshold."
    elif review == "item_review_required":
        stage = REVIEW_REQUIRED
        reason = "Stored extraction requires explicit human review."
    elif not sku_id:
        stage = AMBIGUOUS
        reason = "No exact medication SKU is attached; automatic fulfilment is blocked."
    elif review in {"verified", "user_confirmed"}:
        stage = FULFILMENT_READY
        reason = "Exact SKU is attached and review state allows fulfilment staging."
    else:
        stage = MATCHED
        reason = "Exact catalog match exists but final review state is not fulfilment-ready."

    return {
        "item_id": item.get("id"),
        "medicine_name": medicine_name,
        "strength_or_dosage": item.get("dosage"),
        "form": item.get("form"),
        "frequency": item.get("frequency"),
        "extraction_confidence": confidence,
        "review_status": review or None,
        "sku_id": sku_id,
        "stage": stage,
        "reason": reason,
    }


def _confidence(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(number, 1.0))
