"""Authoritative product-scope registry for India coverage.

This file defines the current State/UT names that ZENDOC intends to support
nationwide. It intentionally does NOT hard-code LGD numeric codes; those are
imported from official LGD state snapshots so government identifiers can
remain source-controlled and updateable.
"""
from __future__ import annotations


INDIA_REGIONS = (
    {"slug": "andhra_pradesh", "name": "Andhra Pradesh", "region_type": "state"},
    {"slug": "arunachal_pradesh", "name": "Arunachal Pradesh", "region_type": "state"},
    {"slug": "assam", "name": "Assam", "region_type": "state"},
    {"slug": "bihar", "name": "Bihar", "region_type": "state"},
    {"slug": "chhattisgarh", "name": "Chhattisgarh", "region_type": "state"},
    {"slug": "goa", "name": "Goa", "region_type": "state"},
    {"slug": "gujarat", "name": "Gujarat", "region_type": "state"},
    {"slug": "haryana", "name": "Haryana", "region_type": "state"},
    {"slug": "himachal_pradesh", "name": "Himachal Pradesh", "region_type": "state"},
    {"slug": "jharkhand", "name": "Jharkhand", "region_type": "state"},
    {"slug": "karnataka", "name": "Karnataka", "region_type": "state"},
    {"slug": "kerala", "name": "Kerala", "region_type": "state"},
    {"slug": "madhya_pradesh", "name": "Madhya Pradesh", "region_type": "state"},
    {"slug": "maharashtra", "name": "Maharashtra", "region_type": "state"},
    {"slug": "manipur", "name": "Manipur", "region_type": "state"},
    {"slug": "meghalaya", "name": "Meghalaya", "region_type": "state"},
    {"slug": "mizoram", "name": "Mizoram", "region_type": "state"},
    {"slug": "nagaland", "name": "Nagaland", "region_type": "state"},
    {"slug": "odisha", "name": "Odisha", "region_type": "state"},
    {"slug": "punjab", "name": "Punjab", "region_type": "state"},
    {"slug": "rajasthan", "name": "Rajasthan", "region_type": "state"},
    {"slug": "sikkim", "name": "Sikkim", "region_type": "state"},
    {"slug": "tamil_nadu", "name": "Tamil Nadu", "region_type": "state"},
    {"slug": "telangana", "name": "Telangana", "region_type": "state"},
    {"slug": "tripura", "name": "Tripura", "region_type": "state"},
    {"slug": "uttar_pradesh", "name": "Uttar Pradesh", "region_type": "state"},
    {"slug": "uttarakhand", "name": "Uttarakhand", "region_type": "state"},
    {"slug": "west_bengal", "name": "West Bengal", "region_type": "state"},
    {"slug": "andaman_and_nicobar_islands", "name": "Andaman and Nicobar Islands", "region_type": "union_territory"},
    {"slug": "chandigarh", "name": "Chandigarh", "region_type": "union_territory"},
    {
        "slug": "dadra_and_nagar_haveli_and_daman_and_diu",
        "name": "Dadra and Nagar Haveli and Daman and Diu",
        "region_type": "union_territory",
    },
    {"slug": "delhi", "name": "Delhi", "region_type": "union_territory"},
    {"slug": "jammu_and_kashmir", "name": "Jammu and Kashmir", "region_type": "union_territory"},
    {"slug": "ladakh", "name": "Ladakh", "region_type": "union_territory"},
    {"slug": "lakshadweep", "name": "Lakshadweep", "region_type": "union_territory"},
    {"slug": "puducherry", "name": "Puducherry", "region_type": "union_territory"},
)

INDIA_REGION_BY_SLUG = {item["slug"]: item for item in INDIA_REGIONS}

VALIDATION_PRIORITY_DISTRICTS = {
    "west_bengal": ["Nadia"],
    "assam": ["Dibrugarh"],
}


def india_region_catalog() -> list[dict]:
    return [dict(item) for item in INDIA_REGIONS]
