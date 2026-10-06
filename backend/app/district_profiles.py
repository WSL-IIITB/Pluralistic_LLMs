"""
Per-district facts for the dashboard's map click-through: which persona region
a district belongs to, its secondary dropout rate from the LKI-SSM casefile
(the same file dataview/ reads), and its UIDAI/NITI dominant-factor rows
(niti_factors.py, both methods, never blended). No LLM -- pure lookups, so
clicking a district costs nothing.

Sub-split rows the data files carry that our 30-district map has no polygon for
(Belagavi Chikkodi, Bengaluru U North/South, Tumakuru Madhugiri, Uttara Kannada
Sirsi, Vijayanagara) are attached to their parent district as `subAreas`
instead of being averaged into it or silently dropped.
"""

from __future__ import annotations

from functools import lru_cache

from .dataview.pipeline import get_dataview_model
from .karnataka import normalize_place, region_of_district
from .niti_factors import (
    _SUBDISTRICT_TO_PARENT,
    DISTRICT_LEVEL_METHOD,
    STATE_LEVEL_METHOD,
    niti_factors_statewide,
    region_of_district_lookup,
)

# Vijayanagara was split out of Ballari in 2021 and has no polygon of its own.
_EXTRA_SUBAREAS = {"vijayanagara": "ballari"}


def _title(name: str) -> str:
    return " ".join(part.capitalize() for part in name.split())


@lru_cache(maxsize=1)
def karnataka_district_profiles() -> list[dict]:
    rod = region_of_district()
    profiles: dict[str, dict] = {
        did: {"districtId": did, "regionId": rid, "dropoutRate": None, "subAreas": [], "nitiFactors": []}
        for did, rid in rod.items()
    }

    for rec in get_dataview_model().casefile.districts:
        if "karnataka" not in rec.state_name.lower():
            continue
        key = normalize_place(rec.district_name)
        parent_key = _SUBDISTRICT_TO_PARENT.get(key) or _EXTRA_SUBAREAS.get(key)
        parent_id = region_of_district_lookup(parent_key) if parent_key else None
        if parent_id and parent_id in profiles:
            profiles[parent_id]["subAreas"].append(
                {"name": _title(rec.district_name), "dropoutRate": round(rec.dropout_rate, 1)}
            )
        elif rec.district_id and rec.district_id in profiles:
            profiles[rec.district_id]["dropoutRate"] = round(rec.dropout_rate, 1)

    for f in niti_factors_statewide():
        did = f["district_id"]
        if did in profiles:
            profiles[did]["nitiFactors"].append(
                {
                    "area": f["district_name"],
                    "factor": f["factor"],
                    "value": round(f["value"], 2),
                    "method": "state" if f["method"] == STATE_LEVEL_METHOD else "district",
                }
            )
    return list(profiles.values())


NITI_METHOD_NOTES = {
    "state": STATE_LEVEL_METHOD,
    "district": DISTRICT_LEVEL_METHOD,
}
