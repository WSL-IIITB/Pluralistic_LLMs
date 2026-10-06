"""
UIDAI/NITI Aayog "dominant factor" data for secondary-school dropout -- the
OFFICIAL/statistical counterpart to Story Mode's social+web-sourced,
persona-driven narrative. Loaded from two user-supplied workbooks under
data/niti/, each one row per (state, district): the factor identified as most
predictive of that district's dropout rate, and district's own value for it.

The two files use two DIFFERENT methods and must never be blended into one
number -- they are presented side by side, each honestly labeled by method,
because we were not able to independently verify the exact statistical
meaning of "value" in either file (a raw indicator percentage vs. a fitted
coefficient/contribution weight look equally plausible from the data alone).
Never assert a specific interpretation beyond what's stated here.

  - dominant_factors_state_level.xlsx: the SAME factor for every district in
    a state (consistent with ranking factors by state-level R-squared, the
    same method dataview/verdict.py's "Major factors" table already uses --
    see that module's `topFactorsForState`), paired with each district's own
    value for that one factor.
  - dominant_factors_district_level.xlsx: the factor varies district by
    district -- a finer-grained, per-district selection.

Karnataka district-naming quirk (mirrors a known gap in this project's own
data/dataview_district_crosswalk.json, which already lists these same 5 names
as "unmatched"): five rows use sub-district names that don't match our 30-
district map (large districts apparently split into administrative circles
for this analysis). Folded into their evident parent district here -- see
_SUBDISTRICT_TO_PARENT -- since our map has no polygon for the sub-split
itself. If a district has more than one row after folding (e.g. Belagavi +
Belagavi Chikkodi), all rows are kept, not averaged, so nothing is silently
dropped or blended.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import TypedDict

import openpyxl

from .config import DATA_DIR
from .karnataka import karnataka_state_code, normalize_place, region_of_district

_STATE_LEVEL_PATH = os.path.join(DATA_DIR, "niti", "dominant_factors_state_level.xlsx")
_DISTRICT_LEVEL_PATH = os.path.join(DATA_DIR, "niti", "dominant_factors_district_level.xlsx")

STATE_LEVEL_METHOD = "state-level top factor (same factor ranked highest for the whole state; value is this district's own figure for it)"
DISTRICT_LEVEL_METHOD = "per-district dominant factor (factor selected individually for this district; value is that factor's fitted weight in this analysis, not a raw percentage)"

# Karnataka-only: sub-district names in the workbooks that don't match our
# 30-district map -- folded onto the parent district id they're evidently
# part of. Verified against data/dataview_district_crosswalk.json, which
# already carries these exact 5 names as "unmatched" for the same reason.
_SUBDISTRICT_TO_PARENT = {
    "belagavi chikkodi": "belagavi",
    "bengaluru u north": "bengaluru urban",
    "bengaluru u south": "bengaluru urban",
    "tumakuru madhugiri": "tumakuru",
    "uttara kannada sirsi": "uttara kannada",
}


class NitiFactor(TypedDict):
    district_name: str  # as it appears in the workbook, before any folding
    district_id: str | None  # None if it couldn't be matched even after folding
    factor: str
    value: float
    method: str  # STATE_LEVEL_METHOD or DISTRICT_LEVEL_METHOD


def _load_workbook_rows(path: str, method: str) -> list[NitiFactor]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(min_row=2, values_only=True))  # row 1 is the header
    out: list[NitiFactor] = []
    state = None
    for row in rows:
        if len(row) < 4:
            continue
        raw_state, district, factor, value = row[0], row[1], row[2], row[3]
        if raw_state not in (None, ""):
            state = raw_state
        if state is None or district is None or factor is None or value is None:
            continue
        if normalize_place(str(state)) != "karnataka":
            continue
        name_key = _SUBDISTRICT_TO_PARENT.get(normalize_place(str(district)), normalize_place(str(district)))
        district_id = region_of_district_lookup(name_key)
        out.append(
            NitiFactor(
                district_name=str(district),
                district_id=district_id,
                factor=str(factor).strip(),
                value=float(value),
                method=method,
            )
        )
    wb.close()
    return out


@lru_cache(maxsize=1)
def _district_name_to_id() -> dict[str, str]:
    """Karnataka district name (normalized) -> district id, built from the
    same gazetteer district names karnataka.py's place_aliases point at --
    kept local/small rather than pulling in the full India gazetteer."""
    # region_of_district() is id -> region_id, keyed by district id, which
    # doesn't give us a name; build the name map straight from
    # karnataka_regions.json's district_ids is not possible without names
    # either, so this map is hand-built from the same 30 official district
    # names used throughout this project (backend/app/data/karnataka_regions.json).
    names = {
        "29-555": "belagavi", "29-556": "bagalkote", "29-557": "vijayapura", "29-558": "bidar",
        "29-559": "raichur", "29-560": "koppal", "29-561": "gadag", "29-562": "dharwad",
        "29-563": "uttara kannada", "29-564": "haveri", "29-565": "ballari", "29-566": "chitradurga",
        "29-567": "davanagere", "29-568": "shivamogga", "29-569": "udupi", "29-570": "chikkamagaluru",
        "29-571": "tumakuru", "29-572": "bengaluru urban", "29-573": "mandya", "29-574": "hassan",
        "29-575": "dakshina kannada", "29-576": "kodagu", "29-577": "mysuru", "29-578": "chamarajanagara",
        "29-579": "kalaburagi", "29-580": "yadgir", "29-581": "kolar", "29-582": "chikkaballapur",
        "29-583": "bengaluru rural", "29-584": "ramanagara",
    }
    # A handful of spelling variants the workbooks use vs. our canonical names.
    aliases = {
        "bagalkot": "29-556", "kalburgi": "29-579", "gulbarga": "29-579", "yadagiri": "29-580",
        "chikkamangaluru": "29-570", "chikkaballapura": "29-582", "chamarajanagar": "29-578",
        # No separate polygon for Vijayanagara (split from Ballari in 2021) --
        # folded onto Ballari's id, matching karnataka_regions.json's own treatment.
        "vijayanagara": "29-565",
    }
    by_name = {v: k for k, v in names.items()}
    by_name.update(aliases)
    return by_name


def region_of_district_lookup(normalized_name: str) -> str | None:
    return _district_name_to_id().get(normalized_name)


@lru_cache(maxsize=1)
def _all_factors() -> list[NitiFactor]:
    return _load_workbook_rows(_STATE_LEVEL_PATH, STATE_LEVEL_METHOD) + _load_workbook_rows(
        _DISTRICT_LEVEL_PATH, DISTRICT_LEVEL_METHOD
    )


def niti_factors_for_region(region_id: str) -> list[NitiFactor]:
    """Every matched factor row (both methods) for districts in this persona region."""
    rod = region_of_district()
    return [f for f in _all_factors() if f["district_id"] and rod.get(f["district_id"]) == region_id]


def niti_factors_statewide() -> list[NitiFactor]:
    """Every matched factor row (both methods) across all of Karnataka."""
    return [f for f in _all_factors() if f["district_id"]]


def niti_unmatched_rows() -> list[NitiFactor]:
    """Rows that couldn't be matched to a district id even after folding --
    surfaced so a gap is visible rather than silently dropped."""
    return [f for f in _all_factors() if not f["district_id"]]
