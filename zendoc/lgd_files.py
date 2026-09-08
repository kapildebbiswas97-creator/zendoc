"""LGD CSV/file normalization for state-scale ZENDOC geography imports."""
from __future__ import annotations

import csv
import io
import re
from typing import Any


def normalize_lgd_state_code(value: Any) -> str:
    """Return the canonical numeric LGD state code used inside ZENDOC.

    LGD exports may serialize numeric state codes with or without leading
    zeroes (for example Uttar Pradesh as 9 or 09). Only purely numeric state
    codes are canonicalized; unexpected non-numeric values are preserved so
    validation can reject them rather than silently coercing unrelated IDs.
    """
    text = str(value or "").strip()
    if not text:
        return ""
    if not re.fullmatch(r"\d{1,3}", text):
        return text
    return str(int(text))


def parse_delimited_text(text: str, *, delimiter: str | None = None, max_rows: int = 250000) -> list[dict[str, str]]:
    raw = str(text or "")
    if not raw.strip():
        raise ValueError("Input text is empty.")
    if delimiter is None:
        first_line = raw.splitlines()[0] if raw.splitlines() else ""
        delimiter = ";" if first_line.count(";") > first_line.count(",") else ","
    reader = csv.DictReader(io.StringIO(raw), delimiter=delimiter)
    if not reader.fieldnames:
        raise ValueError("Header row is required.")
    rows = []
    for index, row in enumerate(reader, start=1):
        if index > max_rows:
            raise ValueError(f"Input is limited to {max_rows} rows.")
        rows.append({_clean_header(k): v for k, v in row.items() if k is not None})
    return rows


def normalize_lgd_bundle(
    *,
    state_code: str,
    districts: list[dict[str, Any]] | None = None,
    subdistricts: list[dict[str, Any]] | None = None,
    villages: list[dict[str, Any]] | None = None,
    villages_by_blocks: list[dict[str, Any]] | None = None,
    blocks: list[dict[str, Any]] | None = None,
    panchayats: list[dict[str, Any]] | None = None,
    urban_local_bodies: list[dict[str, Any]] | None = None,
    ulb_coverage: list[dict[str, Any]] | None = None,
) -> dict[str, list[dict]]:
    state_code = normalize_lgd_state_code(state_code)
    if not state_code:
        raise ValueError("state_code is required.")

    result = {
        "districts": _districts(state_code, districts or []),
        "subdistricts": _subdistricts(state_code, subdistricts or []),
        "villages": _villages(state_code, villages or []),
        "blocks": _blocks(state_code, blocks or []),
        "panchayats": _panchayats(state_code, panchayats or []),
        "local_bodies": _urban_local_bodies(state_code, urban_local_bodies or []),
        "village_panchayat_links": [],
    }

    block_map: dict[str, dict] = {}
    panchayat_map: dict[str, dict] = {}

    for raw in villages_by_blocks or []:
        row = _normalized_row(raw)
        if normalize_lgd_state_code(_value(row, "state code", "statecode")) != state_code:
            continue
        village_code = _value(row, "village code", "villagecode")
        if not village_code:
            continue

        block_code = _value(row, "block code", "blockcode")
        block_name = _value(row, "block name in english", "block name", "blockname")
        district_code = _value(row, "district code", "districtcode")
        subdistrict_code = _value(row, "subdistrict code", "sub district code", "subdistrictcode")
        localbody_code = _value(row, "localbody code", "local body code", "localbodycode")
        localbody_name = _value(row, "localbody name in english", "local body name in english", "localbody name", "local body name")

        if block_code and block_name:
            block_map.setdefault(block_code, {
                "state_code": state_code,
                "code": block_code,
                "name": block_name,
                "district_code": district_code,
                "subdistrict_code": subdistrict_code,
            })

        if localbody_code and localbody_name:
            panchayat_map.setdefault(localbody_code, {
                "state_code": state_code,
                "code": localbody_code,
                "name": localbody_name,
                "district_code": district_code,
                "block_code": block_code,
            })
            result["village_panchayat_links"].append({
                "state_code": state_code,
                "village_code": village_code,
                "panchayat_code": localbody_code,
                "source_ref": f"lgd:village:{village_code}:localbody:{localbody_code}",
            })

        for village in result["villages"]:
            if village["code"] == village_code:
                if block_code:
                    village["block_code"] = block_code
                if localbody_code:
                    village["panchayat_code"] = localbody_code
                break

    for item in block_map.values():
        if not any(existing["code"] == item["code"] for existing in result["blocks"]):
            result["blocks"].append(item)
    for item in panchayat_map.values():
        if not any(existing["code"] == item["code"] for existing in result["panchayats"]):
            result["panchayats"].append(item)

    ulb_map = {item["code"]: item for item in result["local_bodies"]}
    for raw in ulb_coverage or []:
        row = _normalized_row(raw)
        row_state = normalize_lgd_state_code(_value(row, "state code", "statecode"))
        state_name = _value(row, "state name", "state name in english")
        if row_state and row_state != state_code:
            continue
        if not row_state and not state_name:
            continue

        code = _value(row, "localbody", "local body code", "localbody code")
        if not code:
            continue
        name = _value(row, "localbody name", "local body name", "localbody name in english")
        district_code = _value(row, "district code", "districtcode")
        subdistrict_code = _value(row, "subdistrict code", "sub district code")
        item = ulb_map.get(code) or {
            "state_code": state_code,
            "code": code,
            "name": name or f"Local Body {code}",
            "district_code": district_code,
            "subdistrict_code": subdistrict_code,
            "node_type": "municipality",
        }
        if district_code:
            item["district_code"] = district_code
        if subdistrict_code:
            item["subdistrict_code"] = subdistrict_code
        ulb_map[code] = item

    result["local_bodies"] = list(ulb_map.values())
    return result


def _districts(state_code: str, rows: list[dict]) -> list[dict]:
    result = []
    for raw in rows:
        row = _normalized_row(raw)
        if normalize_lgd_state_code(_value(row, "state code", "statecode")) != state_code:
            continue
        code = _value(row, "district code", "districtcode")
        name = _value(row, "district name in english", "district name", "districtname")
        if code and name:
            result.append({"state_code": state_code, "code": code, "name": name})
    return result


def _subdistricts(state_code: str, rows: list[dict]) -> list[dict]:
    result = []
    for raw in rows:
        row = _normalized_row(raw)
        if normalize_lgd_state_code(_value(row, "state code", "statecode")) != state_code:
            continue
        code = _value(row, "sub district code", "subdistrict code", "subdistrictcode")
        name = _value(row, "sub district name", "subdistrict name", "sub district name in english", "subdistrict name in english")
        district_code = _value(row, "district code", "districtcode")
        if code and name and district_code:
            result.append({
                "state_code": state_code,
                "code": code,
                "name": name,
                "district_code": district_code,
            })
    return result


def _villages(state_code: str, rows: list[dict]) -> list[dict]:
    result = []
    for raw in rows:
        row = _normalized_row(raw)
        if normalize_lgd_state_code(_value(row, "state code", "statecode")) != state_code:
            continue
        code = _value(row, "village code", "villagecode")
        name = _value(
            row,
            "village name in englsih",
            "village name in english",
            "village name",
            "villagename",
        )
        district_code = _value(row, "district code", "districtcode")
        subdistrict_code = _value(row, "sub district code", "subdistrict code", "subdistrictcode")
        if code and name and (subdistrict_code or district_code):
            result.append({
                "state_code": state_code,
                "code": code,
                "name": name,
                "district_code": district_code,
                "subdistrict_code": subdistrict_code,
            })
    return result


def _blocks(state_code: str, rows: list[dict]) -> list[dict]:
    result = []
    for raw in rows:
        row = _normalized_row(raw)
        if normalize_lgd_state_code(_value(row, "state code", "statecode")) != state_code:
            continue
        code = _value(row, "block code", "development block code", "blockcode")
        name = _value(row, "block name in english", "block name", "development block name")
        district_code = _value(row, "district code", "districtcode")
        subdistrict_code = _value(row, "sub district code", "subdistrict code")
        if code and name and (district_code or subdistrict_code):
            result.append({
                "state_code": state_code,
                "code": code,
                "name": name,
                "district_code": district_code,
                "subdistrict_code": subdistrict_code,
            })
    return result


def _panchayats(state_code: str, rows: list[dict]) -> list[dict]:
    result = []
    for raw in rows:
        row = _normalized_row(raw)
        if normalize_lgd_state_code(_value(row, "state code", "statecode")) != state_code:
            continue
        code = _value(row, "local body code", "localbody code", "panchayat code")
        name = _value(row, "local body name in english", "localbody name in english", "panchayat name")
        district_code = _value(row, "district code", "districtcode")
        block_code = _value(row, "block code", "blockcode")
        if code and name and (block_code or district_code):
            result.append({
                "state_code": state_code,
                "code": code,
                "name": name,
                "district_code": district_code,
                "block_code": block_code,
            })
    return result


def _urban_local_bodies(state_code: str, rows: list[dict]) -> list[dict]:
    result = []
    for raw in rows:
        row = _normalized_row(raw)
        if normalize_lgd_state_code(_value(row, "state code", "statecode")) != state_code:
            continue
        code = _value(row, "local body code", "localbody code")
        name = _value(row, "local body name in english", "localbody name in english", "local body name")
        if code and name:
            result.append({
                "state_code": state_code,
                "code": code,
                "name": name,
                "district_code": _value(row, "district code", "districtcode"),
                "subdistrict_code": _value(row, "subdistrict code", "sub district code"),
                "node_type": "municipality",
            })
    return result


def _clean_header(value: Any) -> str:
    return " ".join(str(value or "").replace("\n", " ").replace("\r", " ").strip().split())


def _normalized_key(value: Any) -> str:
    text = _clean_header(value).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _normalized_row(raw: dict[str, Any]) -> dict[str, Any]:
    return {_normalized_key(key): value for key, value in dict(raw or {}).items()}


def _value(row: dict[str, Any], *aliases: str) -> str:
    for alias in aliases:
        value = row.get(_normalized_key(alias))
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""
