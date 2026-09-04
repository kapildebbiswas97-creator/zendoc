"""Truthful pharmacy fulfilment planning for Connected Care.

The planner only turns provider-supplied observations into an order-ready
plan. Missing providers, prices, distances, fees, or quantities remain
unknown and are never replaced with a synthetic partner, estimate, or MRP.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import math
from typing import Any

from .db import get_db, now_iso
from .inventory_service import _data_mode, search_pharmacy_offers


@dataclass
class FulfilmentOption:
    option_id: str
    pharmacy_names: list[str]
    pharmacy_ids: list[int]
    strategy_type: str
    strategy_name: str
    coverage_ratio: str
    covered_items_count: int
    total_items_count: int
    distance_summary: str
    item_total_inr: float | None
    delivery_fee_inr: float | None
    total_inr: float | None
    freshness_summary: str
    overall_status: str
    deliveries_count: int
    deliveries_text: str
    why_explanation: list[str]
    unknowns: list[str]
    plan_hash: str
    items: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compute_plan_hash(items: list[dict[str, Any]], pharmacy_ids: list[int], total_inr: float) -> str:
    """Hash the quoted snapshot so confirmation can detect a changed quote."""
    payload = {
        "pharmacy_ids": sorted(int(pid) for pid in pharmacy_ids),
        "total_inr": round(float(total_inr), 2),
        "items": sorted(
            [
                {
                    "sku_id": it.get("sku_id"),
                    "pharmacy_id": it.get("pharmacy_id"),
                    "qty": it.get("quantity"),
                    "price": round(float(it.get("unit_price_inr") or 0.0), 2),
                }
                for it in items
            ],
            key=lambda value: (value.get("sku_id") or 0, value.get("pharmacy_id") or 0),
        ),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:32]


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _prescription_items(prescription_id: int, patient_id: int | None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    from .prescription_service import get_prescription

    prescription = get_prescription(int(prescription_id))
    owner_id = int(prescription["patient_id"])
    if patient_id is not None and int(patient_id) != owner_id:
        raise PermissionError("Prescription does not belong to the requested patient.")
    return prescription, list(prescription.get("items", []))


def _make_item(requested: dict[str, Any], pharmacy: dict[str, Any], observation: dict[str, Any], status: str) -> dict[str, Any]:
    quantity = int(requested.get("quantity_prescribed") or 1)
    unit_price = _finite_number(observation.get("price_inr"))
    subtotal = round(unit_price * quantity, 2) if unit_price is not None else None
    return {
        "prescription_item_id": requested.get("id"),
        "sku_id": int(requested["sku_id"]),
        "medicine_name": requested.get("medicine_name"),
        "quantity": quantity,
        "pharmacy_id": pharmacy.get("user_id"),
        "pharmacy_name": pharmacy.get("pharmacy_name"),
        "unit_price_inr": unit_price,
        "total_price_inr": subtotal,
        "stock_status": status,
        "stock_freshness": observation.get("freshness_label") or "Stock not confirmed",
        "quantity_available": int(observation.get("quantity_available") or 0),
        "data_mode": observation.get("data_mode") or pharmacy.get("data_mode"),
    }


def _build_option(
    option_id: str,
    providers: list[dict[str, Any]],
    items: list[dict[str, Any]],
    total_items: int,
    overall_status: str,
    strategy_type: str,
    why: list[str],
) -> FulfilmentOption:
    provider_ids = [int(provider["user_id"]) for provider in providers if provider.get("user_id") is not None]
    names = [str(provider.get("pharmacy_name") or "Unnamed pharmacy") for provider in providers]
    item_total = None if any(item.get("total_price_inr") is None for item in items) else round(
        sum(float(item["total_price_inr"]) for item in items), 2
    )
    fees = [_finite_number(provider.get("delivery_fee_base_inr")) for provider in providers]
    delivery_fee = round(sum(fee for fee in fees if fee is not None), 2) if fees and all(fee is not None for fee in fees) else None
    total = round(item_total + delivery_fee, 2) if item_total is not None and delivery_fee is not None else None
    distances = [_finite_number(provider.get("distance_km")) for provider in providers]
    distance_summary = (
        " + ".join(f"{distance:g} km" for distance in distances if distance is not None)
        if distances and all(distance is not None for distance in distances)
        else "Distance unavailable"
    )
    unknowns: list[str] = []
    if item_total is None:
        unknowns.append("Price unavailable for one or more prescribed items.")
    if delivery_fee is None:
        unknowns.append("Delivery fee unavailable until the provider configures a quote.")
    if any(distance is None for distance in distances):
        unknowns.append("Distance unavailable because provider or patient coordinates are missing.")
    if overall_status != "CONFIRMED":
        unknowns.append("Previously reported stock must be reconfirmed before any order can be placed.")
    else:
        unknowns.append("Provider acknowledgement is required before fulfilment begins.")
    return FulfilmentOption(
        option_id=option_id,
        pharmacy_names=names,
        pharmacy_ids=provider_ids,
        strategy_type=strategy_type,
        strategy_name=("Confirmed stock option" if overall_status == "CONFIRMED" else "Previously listed — reconfirm stock"),
        coverage_ratio=f"{len(items)} of {total_items}",
        covered_items_count=len(items),
        total_items_count=total_items,
        distance_summary=distance_summary,
        item_total_inr=item_total,
        delivery_fee_inr=delivery_fee,
        total_inr=total,
        freshness_summary="; ".join(sorted({item["stock_freshness"] for item in items if item.get("stock_freshness")})) or "Stock not confirmed",
        overall_status=overall_status,
        deliveries_count=len(set(provider_ids)),
        deliveries_text=(f"{len(set(provider_ids))} delivery" if len(set(provider_ids)) == 1 else f"{len(set(provider_ids))} deliveries"),
        why_explanation=why,
        unknowns=unknowns,
        plan_hash=compute_plan_hash(items, provider_ids, total or 0.0),
        items=items,
    )


def _stage_options(
    options: dict[str, dict[str, Any]],
    patient_id: int,
    actor_id: int | None,
    prescription_id: int | None,
    data_mode: str,
) -> list[dict[str, Any]]:
    """Persist only complete, priced, confirmed snapshots."""
    db = get_db()
    staged: list[dict[str, Any]] = []
    now = now_iso()
    for key, option in options.items():
        if option.get("overall_status") != "CONFIRMED" or option.get("total_inr") is None:
            continue
        if any(item.get("stock_status") != "CONFIRMED" or item.get("unit_price_inr") is None for item in option.get("items", [])):
            continue
        plan_uid = f"plan_{int(patient_id)}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}_{key}"
        cursor = db.execute(
            """
            INSERT INTO fulfilment_plans
            (plan_uid, patient_id, actor_id, prescription_id, strategy_type, strategy_name, coverage_ratio,
             item_total_inr, delivery_fee_inr, total_inr, distance_summary, deliveries_count,
             freshness_summary, overall_status, why_explanation, plan_hash, status, data_mode, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'staged', ?, ?)
            """,
            (
                plan_uid,
                int(patient_id),
                actor_id,
                prescription_id,
                option["strategy_type"],
                option["strategy_name"],
                option["coverage_ratio"],
                option["item_total_inr"],
                option["delivery_fee_inr"],
                option["total_inr"],
                option["distance_summary"],
                option["deliveries_count"],
                option["freshness_summary"],
                option["overall_status"],
                "\n".join(option["why_explanation"]),
                option["plan_hash"],
                data_mode,
                now,
            ),
        )
        plan_db_id = int(cursor.lastrowid)
        option["db_plan_id"] = plan_db_id
        option["plan_uid"] = plan_uid
        option["data_mode"] = data_mode
        staged.append(option)
        for item in option["items"]:
            db.execute(
                """
                INSERT INTO fulfilment_plan_items
                (plan_id, prescription_item_id, sku_id, pharmacy_id, quantity, unit_price_inr, total_price_inr, stock_status, stock_freshness)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    plan_db_id,
                    item.get("prescription_item_id"),
                    item["sku_id"],
                    item["pharmacy_id"],
                    item["quantity"],
                    item["unit_price_inr"],
                    item["total_price_inr"],
                    item["stock_status"],
                    item["stock_freshness"],
                ),
            )
    if staged:
        db.commit()
    return staged


def optimize_prescription_fulfilment(
    prescribed_items: list[dict[str, Any]] | int | None = None,
    user_lat: float | None = None,
    user_lon: float | None = None,
    city: str | None = None,
    radius_km: float = 12.0,
    patient_id: int | None = None,
    actor_id: int | None = None,
    prescription_id: int | None = None,
    stage_in_db: bool = True,
    actor: Any = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Find real options and stage only a fully quoted, confirmed snapshot."""
    if isinstance(prescribed_items, int):
        prescription_id = int(prescribed_items)
        prescribed_items = None
    if prescription_id is None and kwargs.get("prescription_id"):
        prescription_id = int(kwargs["prescription_id"])
    if user_lat is None:
        user_lat = kwargs.get("patient_lat")
    if user_lon is None:
        user_lon = kwargs.get("patient_lon")

    prescription = None
    if prescription_id and not prescribed_items:
        prescription, prescribed_items = _prescription_items(int(prescription_id), patient_id)
        patient_id = int(prescription["patient_id"])
    prescribed_items = [dict(item) for item in (prescribed_items or [])]
    if not prescribed_items:
        return {
            "status": "NO_ITEMS",
            "status_code": "NO_ITEMS",
            "message": "No prescribed medicine items are available for fulfilment.",
            "options": {},
            "total_items": 0,
            "plan_id": None,
            "plan_hash": None,
            "total_cost_inr": None,
        }

    unresolved = [
        item for item in prescribed_items
        if not item.get("sku_id") or str(item.get("review_status") or "").lower() == "item_review_required"
    ]
    if unresolved:
        return {
            "status": "ITEM_REVIEW_REQUIRED",
            "status_code": "ITEM_REVIEW_REQUIRED",
            "message": "Every prescribed medicine must have an exact, user-verified catalogue match before fulfilment.",
            "unresolved_items": [item.get("medicine_name") for item in unresolved],
            "options": {},
            "total_items": len(prescribed_items),
            "plan_id": None,
            "plan_hash": None,
            "total_cost_inr": None,
        }

    target_patient = int(patient_id) if patient_id is not None else None
    if actor is not None:
        if target_patient is None:
            raise PermissionError("A patient must be specified when an actor requests fulfilment.")
        from .context_engine import verify_context_authorization

        verify_context_authorization(actor, target_patient, "pharmacy_fulfilment")
        if actor_id is None:
            try:
                actor_id = int(actor["id"])
            except (KeyError, TypeError, ValueError):
                actor_id = None

    mode = _data_mode(kwargs.get("data_mode"))
    pharmacies = search_pharmacy_offers(
        medicine_ids=[int(item["sku_id"]) for item in prescribed_items],
        city=city,
        user_lat=user_lat,
        user_lon=user_lon,
        radius_km=radius_km,
        data_mode=mode,
    )
    total_items = len(prescribed_items)
    complete: list[FulfilmentOption] = []
    stale: list[FulfilmentOption] = []

    for pharmacy in pharmacies:
        inventory = pharmacy.get("inventory") or {}
        items: list[dict[str, Any]] = []
        statuses: list[str] = []
        for requested in prescribed_items:
            observation = inventory.get(int(requested["sku_id"]))
            if observation is None:
                break
            status = str(observation.get("effective_status") or "UNKNOWN").upper()
            needed = int(requested.get("quantity_prescribed") or 1)
            if status == "CONFIRMED" and int(observation.get("quantity_available") or 0) < needed:
                status = "UNAVAILABLE"
            statuses.append(status)
            items.append(_make_item(requested, pharmacy, observation, status))
        if len(items) != total_items:
            continue
        if all(status == "CONFIRMED" for status in statuses):
            complete.append(_build_option(
                f"pharmacy-{pharmacy['user_id']}",
                [pharmacy],
                items,
                total_items,
                "CONFIRMED",
                "single_complete",
                [f"All {total_items} exact prescribed items have fresh confirmed observations at this provider."],
            ))
        elif all(status in {"CONFIRMED", "STALE"} for status in statuses) and any(status == "STALE" for status in statuses):
            stale.append(_build_option(
                f"pharmacy-stale-{pharmacy['user_id']}",
                [pharmacy],
                items,
                total_items,
                "STALE",
                "stale_listed",
                ["Every item was previously observed, but at least one inventory observation is stale and must be reconfirmed."],
            ))

    # A split option may use only independently confirmed observations.
    for index, first in enumerate(pharmacies):
        for second in pharmacies[index + 1:]:
            split_items: list[dict[str, Any]] = []
            used: list[dict[str, Any]] = []
            for requested in prescribed_items:
                candidates: list[tuple[dict[str, Any], dict[str, Any]]] = []
                needed = int(requested.get("quantity_prescribed") or 1)
                for pharmacy in (first, second):
                    observation = (pharmacy.get("inventory") or {}).get(int(requested["sku_id"]))
                    if (
                        observation
                        and observation.get("effective_status") == "CONFIRMED"
                        and int(observation.get("quantity_available") or 0) >= needed
                    ):
                        candidates.append((pharmacy, observation))
                if not candidates:
                    split_items = []
                    break
                pharmacy, observation = min(
                    candidates,
                    key=lambda pair: _finite_number(pair[1].get("price_inr")) if _finite_number(pair[1].get("price_inr")) is not None else float("inf"),
                )
                split_items.append(_make_item(requested, pharmacy, observation, "CONFIRMED"))
                if pharmacy not in used:
                    used.append(pharmacy)
            if len(split_items) == total_items and len(used) > 1:
                complete.append(_build_option(
                    f"split-{first['user_id']}-{second['user_id']}",
                    used,
                    split_items,
                    total_items,
                    "CONFIRMED",
                    "split_fulfilment",
                    [f"{len(used)} participating pharmacies cover all {total_items} exact items with confirmed stock."],
                ))

    complete.sort(key=lambda option: (
        option.total_inr is None,
        option.total_inr if option.total_inr is not None else float("inf"),
        option.distance_summary == "Distance unavailable",
        option.distance_summary,
        option.option_id,
    ))
    stale.sort(key=lambda option: option.option_id)
    result_options = {f"option_{idx}": option.to_dict() for idx, option in enumerate(complete + stale, start=1)}
    for option in result_options.values():
        option["data_mode"] = mode

    staged: list[dict[str, Any]] = []
    if stage_in_db and target_patient is not None:
        staged = _stage_options(result_options, target_patient, actor_id, prescription_id, mode)

    best = staged[0] if staged else (next(iter(result_options.values())) if result_options else {})
    confirmed_present = any(option.get("overall_status") == "CONFIRMED" for option in result_options.values())
    if staged:
        status = "staged"
        status_code = "STAGED"
        message = "Confirmed options are staged for explicit user review."
    elif result_options and confirmed_present:
        status = "NO_CONFIRMED_OPTION"
        status_code = "NO_CONFIRMED_OPTION"
        message = "Confirmed stock was found, but a complete quote is unavailable; no order-ready plan was created."
    elif result_options:
        status = "NO_CONFIRMED_OPTION"
        status_code = "NO_CONFIRMED_OPTION"
        message = "Only stale or unconfirmed observations were found; no order-ready plan was created."
    else:
        status = "NO_CONFIRMED_INVENTORY"
        status_code = "NO_CONFIRMED_INVENTORY"
        message = "No confirmed participating pharmacy inventory is currently available for this prescription."

    return {
        "status": status,
        "status_code": status_code,
        "message": message,
        "next_actions": ["change_location", "increase_radius", "refresh_inventory", "contact_pharmacy"],
        "plan_id": best.get("db_plan_id"),
        "plan_hash": best.get("plan_hash"),
        "total_cost_inr": best.get("total_inr"),
        "total_items": total_items,
        "data_mode": mode,
        "options": result_options,
    }
