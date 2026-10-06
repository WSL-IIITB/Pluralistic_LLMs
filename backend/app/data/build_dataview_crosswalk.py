"""
Derives dataview_district_crosswalk.json, mapping each district row in the
LKI-SSM casefile (backend/app/data/dataview/raw/casefile.xlsx) onto our own
district_gazetteer.json's district ids -- the two datasets were built from
different, independently-maintained district lists and don't share a code
scheme, so matching happens on normalized (state, district) name pairs.

Run: python -m app.data.build_dataview_crosswalk   (from backend/, venv active)

Three tiers are tried in order for each casefile row:
  1. exact match: normalized district name + state name both hit our gazetteer
  2. district_aliases.csv (LKI's own UDISE-name -> NFHS-name table, shipped
     alongside the casefile) resolves a spelling divergence between the two
     source surveys
  3. a small hand-authored SUPPLEMENTAL_ALIASES table for spelling variants
     neither of the above covers (verified individually against the gazetteer
     while building this script -- see the coverage report this prints)

A residual of ~12% will not match at all: genuine post-2016 Indian district
reorganizations (new Rajasthan/Chhattisgarh/Andhra Pradesh/Telangana/Karnataka/
Assam/Tamil Nadu/Maharashtra/Meghalaya/Tripura/Mizoram/Punjab districts, and
Sikkim's 2021 six-district split) that our own district_gazetteer.json --
itself derived from the frontend's GeoJSON -- has no polygon for. These are
NOT name-matching bugs; the geometry to color simply doesn't exist yet. They
are recorded as "unmatched" here and must render as "no data" on the map, per
this feature's fail-open-to-transparent-gap philosophy -- never guess a
nearby district as a stand-in.

Output shape: {"<state>|<district>": {"districtId": "...", "match":
"exact"|"alias"|"supplemental"|"unmatched"}}, keyed by the casefile's own
raw (state, district) strings so loader.py can look a row up directly
without re-normalizing.
"""

from __future__ import annotations

import json
import re

import openpyxl

from ..config import DATA_DIR

_CASEFILE_PATH = f"{DATA_DIR}/dataview/raw/casefile.xlsx"
_CASEFILE_SHEET = "RUN00676_ALL_INDIA_CASEFILE_MAT"
_DISTRICT_ALIASES_PATH = f"{DATA_DIR}/dataview/raw/district_aliases.csv"
_GAZETTEER_PATH = f"{DATA_DIR}/district_gazetteer.json"
_OUT_PATH = f"{DATA_DIR}/dataview_district_crosswalk.json"

_NORMALIZE_RE = re.compile(r"[^a-z0-9]+")
_AND_WORD_RE = re.compile(r"\band\b")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize(name: str) -> str:
    """Mirror build_gazetteer.py's normalize() so district-name lookups land
    on the same keys the gazetteer was built with."""
    return _NORMALIZE_RE.sub(" ", str(name).lower()).strip()


def normalize_state(name: str) -> str:
    """State-name comparison needs one extra step beyond normalize(): the
    casefile spells conjunctions as "&" (which normalize() strips to nothing,
    e.g. "Jammu & Kashmir" -> "jammu kashmir") while the gazetteer spells them
    out ("Jammu and Kashmir" -> "jammu and kashmir") -- so also drop the
    word "and" on both sides before comparing, re-collapsing the whitespace
    that leaves behind."""
    n = _AND_WORD_RE.sub(" ", normalize(name))
    return _WHITESPACE_RE.sub(" ", n).strip()


# Verified individually against district_gazetteer.json while building this
# script (see the module docstring) -- each key is a casefile district name
# normalized via normalize(), each value is a gazetteer key that resolves to
# the same real district under a different spelling convention.
SUPPLEMENTAL_ALIASES: dict[str, str] = {
    "kheri": "lakhimpur kheri",
    "banas kantha": "banaskantha",
    "sabar kantha": "sabarkantha",
    "panch mahals": "panchmahal",
    "dohad": "dahod",
    "kachchh": "kutch",
    "mahesana": "mehsana",
    "coochbehar": "cooch behar",
    "nabarangpur": "nabarangapur",
    "sonepur": "subarnapur",
    "lahul spiti": "lahaul and spiti",
    "pashchim champaran": "west champaran",
    "purba champaran": "east champaran",
    "kaimur bhabua": "kaimur",
    "purbi singhbhum": "east singhbhum",
    "pondicherry": "puducherry",
    "baramula": "baramulla",
    "badgam": "budgam",
    "punch": "poonch",
    "nellore": "s p s nellore",
    "kadapa": "y s r kadapa",
}


def _load_gazetteer() -> dict[str, list[dict[str, str]]]:
    with open(_GAZETTEER_PATH, encoding="utf-8") as f:
        return json.load(f)


def _load_district_aliases() -> dict[str, str]:
    """udise_district_name -> alias_name, both normalized, from LKI's own
    crosswalk CSV (plain csv.reader -- this file has no embedded commas)."""
    import csv

    alias_map: dict[str, str] = {}
    with open(_DISTRICT_ALIASES_PATH, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            alias_map[normalize(row["udise_district_name"])] = normalize(row["alias_name"])
    return alias_map


def _load_casefile_rows() -> list[tuple[str, str]]:
    wb = openpyxl.load_workbook(_CASEFILE_PATH, read_only=True, data_only=True)
    ws = wb[_CASEFILE_SHEET]
    rows = ws.iter_rows(values_only=True)
    header = next(rows)
    state_idx = header.index("state")
    district_idx = header.index("district")
    out = [(row[state_idx], row[district_idx]) for row in rows if row[state_idx] and row[district_idx]]
    wb.close()
    return out


def build() -> dict[str, dict[str, str]]:
    gazetteer = _load_gazetteer()
    district_aliases = _load_district_aliases()
    crosswalk: dict[str, dict[str, str]] = {}
    counts = {"exact": 0, "alias": 0, "supplemental": 0, "unmatched": 0}

    def state_matches(candidates: list[dict[str, str]] | None, norm_state: str) -> dict[str, str] | None:
        if not candidates:
            return None
        for cand in candidates:
            if normalize_state(cand["stateName"]) == norm_state:
                return cand
        return None

    for state, district in _load_casefile_rows():
        norm_district = normalize(district)
        norm_state = normalize_state(state)
        key = f"{state}|{district}"

        hit = state_matches(gazetteer.get(norm_district), norm_state)
        match_kind = "exact"

        if hit is None:
            alias = district_aliases.get(norm_district)
            if alias:
                hit = state_matches(gazetteer.get(alias), norm_state)
                match_kind = "alias"

        if hit is None:
            supplemental = SUPPLEMENTAL_ALIASES.get(norm_district)
            if supplemental:
                hit = state_matches(gazetteer.get(supplemental), norm_state)
                match_kind = "supplemental"

        if hit is not None:
            crosswalk[key] = {"districtId": hit["districtId"], "match": match_kind}
            counts[match_kind] += 1
        else:
            crosswalk[key] = {"districtId": "", "match": "unmatched"}
            counts["unmatched"] += 1

    total = sum(counts.values())
    matched = total - counts["unmatched"]
    print(
        f"exact={counts['exact']} alias={counts['alias']} supplemental={counts['supplemental']} "
        f"unmatched={counts['unmatched']} / {total} total"
    )
    print(f"coverage: {matched}/{total} ({matched / total:.1%})")

    return crosswalk


def main() -> None:
    crosswalk = build()
    with open(_OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(crosswalk, f, ensure_ascii=False, indent=2)
    print(f"wrote {len(crosswalk)} entries ({_OUT_PATH})")


if __name__ == "__main__":
    main()
