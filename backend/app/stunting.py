"""
The stunting topic: the NITI team's prescriptive model for under-5 stunting in Karnataka, reproduced from their
Tableau workbook ("Prescriptive district view (children who are stunted under the age of 5 years)_01"; data in
data/niti/stunting/, extracted by scripts/extract_stunting_twbx.py, formulas in calculated_fields.md).

The model, as the workbook computes it at its published defaults:

  * One linear model across Karnataka's districts: stunting % = intercept + sum(coefficient_f x value_f), over 11
    NFHS-6 / Poshan factors in four buckets. Each factor also carries its own Pearson r with stunting.
  * Target: cut the district's stunting by 20% ("Reduce Children under 5 years who are stunted" = 0.20).
  * Equal allocation: each bucket takes 1 / (number of buckets) of the cut, shared equally by its factors.
  * Prescribed value of a factor = its value + (bucket weight / factors in bucket) x (target - current) /
    coefficient, clamped to 0..100. "Change" = |prescribed - value| / value. The dashboard lists factors by change,
    largest first.

This module never touches the persona library: it is the data side, handed to personas only as evidence.
"""

from __future__ import annotations

import csv
import json
import os
import statistics
from functools import lru_cache

from .config import DATA_DIR

DIR = os.path.join(DATA_DIR, "niti", "stunting")
OUTCOME = "Children under 5 years who are stunted (height-for-age) (%) (ind_068)"
REDUCE_BY = 0.20  # the workbook's default target: 20% less stunting
SOURCE = {
    "file": "backend/app/data/niti/stunting/Prescriptive_district_view_stunting_under5_01.twbx",
    "from": "NITI team's prescriptive district view for under-5 stunting (Tableau Public, karnataka.data.lake)",
    "dataset": "NFHS-6 district indicators; pre-school attendance from Poshan Tracker FY 2024-25",
    "provisional": True,
}


def _rows() -> list[dict]:
    with open(os.path.join(DIR, "factors_karnataka.csv"), encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _f(x: str | None) -> float | None:
    try:
        return float(x) if x not in (None, "", "None") else None
    except ValueError:
        return None


@lru_cache(maxsize=1)
def model() -> dict:
    with open(os.path.join(DIR, "district_ids.json"), encoding="utf-8") as fh:
        ids: dict[str, str] = json.load(fh)["districts"]
    with open(os.path.join(DIR, "factor_explanations.json"), encoding="utf-8") as fh:
        explain = {k: v for k, v in json.load(fh).items() if not k.startswith("_")}

    rows = _rows()
    by_district: dict[str, list[dict]] = {}
    for r in rows:
        by_district.setdefault(r["District"], []).append(r)

    factors: dict[str, dict] = {}
    intercept = confidence = None
    for r in rows:
        name, m = r["Field Name"].strip(), _f(r["M Value"])
        if name == OUTCOME:
            confidence = confidence if confidence is not None else _f(r["Confidence Level"])
            continue
        if not name or m is None:
            continue
        intercept = _f(r["Intercept Value"])
        factors.setdefault(name, {
            "name": name, "column": r["Column Name"], "bucket": r["Bucket"], "coefficient": m,
            "pearson": _f(r["Pearson Correlation"]), "directionMatch": r["Direction Match"],
            "better": "higher" if m < 0 else "lower", **explain.get(name, {"short": name, "measures": ""}),
            "values": [],
        })["values"].append(float(r["Field Value"]))

    def rank(name: str, v: float) -> int:
        """1 = best in Karnataka in the direction the model links to less stunting."""
        f = factors[name]
        return 1 + sum(1 for x in f["values"] if (x > v if f["better"] == "higher" else x < v))

    districts: dict[str, dict] = {}
    for area, rs in by_district.items():
        did = ids[area]
        outcome = next((_f(r["Field Value"]) for r in rs if r["Field Name"].strip() == OUTCOME), None)
        frows = [r for r in rs if r["Field Name"].strip() in factors]
        if outcome is None or not frows:
            districts[did] = {"area": area, "districtId": did, "stunting": None, "target": None, "factors": []}
            continue
        target = outcome * (1 - REDUCE_BY)
        buckets = {r["Bucket"] for r in frows}
        per_bucket = {b: sum(1 for r in frows if r["Bucket"] == b) for b in buckets}
        out = []
        for r in frows:
            name, v = r["Field Name"].strip(), float(r["Field Value"])
            f = factors[name]
            share = (1 / len(buckets)) / per_bucket[f["bucket"]]
            raw = v + share * (target - outcome) / f["coefficient"]
            prescribed = min(100.0, max(0.0, raw))
            out.append({
                "name": name, "bucket": f["bucket"], "value": round(v, 2), "prescribed": round(prescribed, 2),
                "change": None if abs(v) < 1e-6 else round(abs(prescribed - v) / v * 100, 1),
                "share": round(share * 100, 2), "atLimit": not 0 <= raw <= 100, "rank": rank(name, v),
            })
        out.sort(key=lambda x: -(x["change"] or 0))
        districts[did] = {"area": area, "districtId": did, "stunting": round(outcome, 1),
                          "target": round(target, 2), "factors": out}

    rates = sorted((d["stunting"], did) for did, d in districts.items() if d["stunting"] is not None)
    for pos, (_, did) in enumerate(sorted(rates, key=lambda x: -x[0]), start=1):
        districts[did]["rankHighest"] = pos
    values = [r for r, _ in rates]
    return {
        "version": 1,
        "topic": "stunting",
        "outcome": {"name": OUTCOME, "short": "Stunting, under 5", "unit": "%", "better": "lower"},
        "source": {**SOURCE, "karnatakaDistricts": len(districts), "withData": len(values),
                   "missing": sorted(d["area"] for d in districts.values() if d["stunting"] is None)},
        "method": {
            "model": "One linear model fitted across Karnataka's districts: stunting % = intercept + the sum of each "
                     "factor's coefficient x its value. Each factor also has its own correlation (Pearson r) with stunting.",
            "target": f"Cut the district's stunting by {int(REDUCE_BY * 100)}% (the workbook's default).",
            "allocation": "Equal allocation: each of the buckets takes an equal share of the cut, split equally among "
                          "its factors.",
            "prescribed": "A factor's prescribed value is how far it would have to move, along the model, to deliver its "
                          "share of the cut (kept within 0-100%). Change is that move as a % of today's value; factors "
                          "are listed by change, largest first, as in the dashboard.",
            "caveat": "The model is a correlation across districts, not proof that changing a factor would change "
                      "stunting. The authors mark it PROVISIONAL.",
            "reduceBy": REDUCE_BY, "intercept": intercept, "confidence": confidence,
        },
        "factors": [
            {**{k: v for k, v in f.items() if k != "values"},
             "karnataka": {"min": round(min(f["values"]), 2), "median": round(statistics.median(f["values"]), 2),
                           "max": round(max(f["values"]), 2)}}
            for f in sorted(factors.values(), key=lambda f: (f["bucket"], f["name"]))
        ],
        "statewide": {
            "mean": round(statistics.mean(values), 1) if values else None,
            "median": round(statistics.median(values), 1) if values else None,
            "highest": {"districtId": rates[-1][1], "value": rates[-1][0]} if rates else None,
            "lowest": {"districtId": rates[0][1], "value": rates[0][0]} if rates else None,
        },
        "districts": districts,
    }


def district_evidence(district_id: str) -> dict | None:
    """Evidence for a persona's answer: the district's stunting and the model's factors, plainly labelled."""
    m = model()
    d = m["districts"].get(district_id)
    if not d or d["stunting"] is None:
        return None
    info = {f["name"]: f for f in m["factors"]}
    return {
        "about": "Under-5 stunting in this district (NFHS-6) and the NITI team's PROVISIONAL prescriptive model.",
        "district": d["area"],
        "stunting_pct": d["stunting"],
        "karnataka_mean_pct": m["statewide"]["mean"],
        "rank": f"{d.get('rankHighest')} highest of {m['source']['withData']} districts",
        "factors": [
            {"factor": f["name"], "bucket": f["bucket"], "value_pct": f["value"],
             "karnataka_rank": f"{f['rank']} of {m['source']['withData']} (1 = best)",
             "correlation_with_stunting": info[f["name"]]["pearson"],
             "model_prescribed_value_for_20pct_cut": f["prescribed"]}
            for f in d["factors"]
        ],
        "caveat": m["method"]["caveat"],
    }


# ── For the pipeline's "Story vs official data" step on a stunting question ──────────────────────────────────

_STUNTING_QUERY = __import__("re").compile(r"stunt|malnutri|malnourish|undernutri|undernourish|child nutrition", __import__("re").I)


def is_stunting_query(query: str) -> bool:
    return bool(_STUNTING_QUERY.search(query or ""))


def _official_rows(district_ids: list[str]) -> list[dict]:
    """NitiFactor-shaped rows: each district's stunting rate, then its three factors the model prescribes most
    change for (default 20% target) -- the official-data side for a stunting run."""
    m = model()
    info = {f["name"]: f for f in m["factors"]}
    rows: list[dict] = []
    for did in district_ids:
        d = m["districts"].get(did)
        if not d or d["stunting"] is None:
            continue
        rows.append({"district_name": d["area"], "district_id": did, "factor": "Children under 5 who are stunted (%)",
                     "value": d["stunting"], "method": "outcome (NFHS-6)"})
        for f in d["factors"][:3]:
            rows.append({"district_name": d["area"], "district_id": did,
                         "factor": f"{info[f['name']]['short']} (now {f['value']}%, model needs {f['prescribed']}%)",
                         "value": f["value"], "method": "stunting model: top prescribed change"})
    return rows


def stunting_factors_for_region(region_id: str) -> list[dict]:
    from .karnataka import region_of_district

    rod = region_of_district()
    return _official_rows([did for did, rid in rod.items() if rid == region_id])


def stunting_factors_statewide() -> list[dict]:
    return _official_rows(sorted(model()["districts"]))
