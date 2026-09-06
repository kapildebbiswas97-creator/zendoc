"""ZENDOC NutritionAgent foundation.

General wellness only. This module compares user-supplied product labels and
prices. It does not diagnose, prescribe diets, treat food as medicine, or allow
sponsorship to alter health suitability rankings.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite
from typing import Any


NUTRIENTS = (
    "calories_kcal",
    "protein_g",
    "carbohydrate_g",
    "fat_g",
    "fibre_g",
    "sugar_g",
    "sodium_mg",
)


@dataclass(frozen=True)
class NutritionProduct:
    name: str
    price_inr: float
    quantity: float
    quantity_unit: str
    calories_kcal: float | None = None
    protein_g: float | None = None
    carbohydrate_g: float | None = None
    fat_g: float | None = None
    fibre_g: float | None = None
    sugar_g: float | None = None
    sodium_mg: float | None = None
    ingredients: str = ""
    sponsored: bool = False
    source: str = "user_supplied_label"

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "NutritionProduct":
        name = str(data.get("name") or "").strip()
        if not name:
            raise ValueError("Product name is required.")
        price = _positive_number(data.get("price_inr"), "price_inr", allow_zero=True)
        quantity = _positive_number(data.get("quantity"), "quantity")
        unit = str(data.get("quantity_unit") or "").strip().lower()
        if unit not in {"g", "kg", "ml", "l", "serving", "unit"}:
            raise ValueError("quantity_unit must be g, kg, ml, l, serving, or unit.")

        values = {}
        for nutrient in NUTRIENTS:
            raw = data.get(nutrient)
            values[nutrient] = None if raw in (None, "") else _positive_number(raw, nutrient, allow_zero=True)

        return cls(
            name=name,
            price_inr=price,
            quantity=quantity,
            quantity_unit=unit,
            ingredients=str(data.get("ingredients") or "").strip(),
            sponsored=_bool(data.get("sponsored")),
            source=str(data.get("source") or "user_supplied_label")[:120],
            **values,
        )

    def to_dict(self) -> dict:
        return asdict(self)


def compare_products(
    products: list[dict[str, Any] | NutritionProduct],
    *,
    goal: str = "general_wellness",
    allergens: list[str] | None = None,
) -> dict:
    """Compare labels without making clinical claims or sponsored ranking."""
    parsed = [p if isinstance(p, NutritionProduct) else NutritionProduct.from_mapping(p) for p in products]
    if len(parsed) < 2:
        raise ValueError("At least two products are required for comparison.")
    if len(parsed) > 10:
        raise ValueError("A maximum of 10 products may be compared at once.")

    allergens = [str(item).strip().lower() for item in (allergens or []) if str(item).strip()]
    rows = []
    for product in parsed:
        normalized_quantity = _base_quantity(product.quantity, product.quantity_unit)
        price_per_base = product.price_inr / normalized_quantity if normalized_quantity else None
        nutrient_density = _normalized_nutrients(product)
        allergy_matches = [
            allergen for allergen in allergens if allergen and allergen in product.ingredients.lower()
        ]
        rows.append({
            **product.to_dict(),
            "price_per_base_unit": round(price_per_base, 4) if price_per_base is not None else None,
            "normalized_nutrients": nutrient_density,
            "allergy_matches": allergy_matches,
            "eligible_for_health_ranking": not allergy_matches,
            "sponsorship_affects_health_rank": False,
        })

    health_ranked = sorted(
        rows,
        key=lambda row: (
            not row["eligible_for_health_ranking"],
            _goal_score(row["normalized_nutrients"], goal),
            row["price_per_base_unit"] if row["price_per_base_unit"] is not None else float("inf"),
            row["name"].lower(),
        ),
    )
    cheapest = min(
        rows,
        key=lambda row: (
            row["price_per_base_unit"] if row["price_per_base_unit"] is not None else float("inf"),
            row["name"].lower(),
        ),
    )

    best = health_ranked[0]
    return {
        "status": "OK",
        "goal": str(goal or "general_wellness"),
        "products": rows,
        "best_general_fit": best["name"] if best["eligible_for_health_ranking"] else None,
        "cheapest_by_normalized_quantity": cheapest["name"],
        "sponsored_products": [row["name"] for row in rows if row["sponsored"]],
        "sponsorship_policy": "Sponsored status is disclosed and never changes health suitability ranking.",
        "allergy_warning": any(row["allergy_matches"] for row in rows),
        "medical_diet_required": _medical_goal(goal),
        "next_step": (
            "For a disease-specific or therapeutic diet, use a qualified clinician/dietitian."
            if _medical_goal(goal)
            else "Use this as general label/price guidance, not a diagnosis or treatment plan."
        ),
    }


def hydration_guidance(*, activity_minutes: int | None = None, high_heat: bool = False, medical_condition: bool = False) -> dict:
    """Return conservative general hydration guidance without dose-style claims."""
    if medical_condition:
        return {
            "status": "CLINICAL_REVIEW_RECOMMENDED",
            "message": "Hydration needs can change with kidney, heart, endocrine, or other medical conditions. Use clinician guidance.",
        }
    minutes = max(0, min(int(activity_minutes or 0), 24 * 60))
    if minutes <= 60 and not high_heat:
        message = "For ordinary short-duration activity, plain safe drinking water is generally the simplest hydration option."
    else:
        message = (
            "Longer activity or high heat may increase fluid and electrolyte needs. "
            "Use thirst, conditions, duration, and qualified guidance rather than assuming a sports drink is necessary."
        )
    return {"status": "GENERAL_WELLNESS", "message": message}


def _goal_score(nutrients: dict[str, float | None], goal: str) -> float:
    goal = str(goal or "general_wellness").strip().lower()
    protein = nutrients.get("protein_g") or 0.0
    fibre = nutrients.get("fibre_g") or 0.0
    sugar = nutrients.get("sugar_g") or 0.0
    sodium = nutrients.get("sodium_mg") or 0.0
    calories = nutrients.get("calories_kcal") or 0.0

    # Lower score is better. These are transparent comparison heuristics, not
    # clinical nutrition prescriptions.
    if goal in {"fitness", "protein", "muscle_support"}:
        return sugar * 1.5 + sodium / 500.0 - protein * 2.0 - fibre * 0.5
    if goal in {"lower_sugar", "general_wellness"}:
        return sugar * 2.0 + sodium / 400.0 - fibre - protein * 0.25
    if goal in {"lower_calorie", "weight_management"}:
        return calories / 100.0 + sugar + sodium / 800.0 - fibre
    return sugar + sodium / 500.0 - fibre * 0.5


def _normalized_nutrients(product: NutritionProduct) -> dict[str, float | None]:
    base = _base_quantity(product.quantity, product.quantity_unit)
    factor = 100.0 / base if base and product.quantity_unit in {"g", "kg", "ml", "l"} else 1.0
    return {
        nutrient: (round(getattr(product, nutrient) * factor, 4) if getattr(product, nutrient) is not None else None)
        for nutrient in NUTRIENTS
    }


def _base_quantity(quantity: float, unit: str) -> float:
    if unit in {"g", "ml"}:
        return quantity
    if unit in {"kg", "l"}:
        return quantity * 1000.0
    return quantity


def _medical_goal(goal: str) -> bool:
    text = str(goal or "").lower()
    return any(term in text for term in (
        "diabetes", "kidney", "renal", "heart failure", "cancer", "pregnancy complication",
        "celiac", "therapeutic", "medical diet",
    ))


def _positive_number(value: Any, field: str, *, allow_zero: bool = False) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric.") from exc
    if not isfinite(number) or number < 0 or (number == 0 and not allow_zero):
        raise ValueError(f"{field} must be {'non-negative' if allow_zero else 'positive'}.")
    return number


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)
