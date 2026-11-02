"""
Build public/data/niti-prescriptive.json: the NITI team's prescriptive model for Karnataka, district by district.

    python3 scripts/export_niti_prescriptive.py

Input : backend/app/data/niti/prescriptive/{factors_all_india,dropout_2023_24,dropout_2024_25}.csv
        (extracted from the team's Tableau workbook by scripts/extract_niti_twbx.py)
        backend/app/data/niti/prescriptive/factor_explanations.json  (what each factor measures + general reasoning)
        public/data/districts.json  (workbook area name -> our district id)

The model (from the workbook's calculated fields): each of 18 factors has one straight line fitted across
Karnataka's districts, predicted dropout = M x value + intercept. For one district, a factor's *sensitivity* is how
much that line's predicted dropout would change if the district improved the factor by 10% of its own value, in the
direction that lowers dropout, as a percentage of the prediction (clamped to 0..100). A factor's *contribution* is
its sensitivity as a share of the sum over the district's 18 factors. The top contributions are the "prescriptive"
changes.

Two rankings are written, never blended:
  * "niti"     -- the formula exactly as the workbook computes it;
  * "feasible" -- the same formula, but a percentage indicator cannot go past 100% (or below 0%). For indicators that
                  are already near 100% (toilets, libraries, CCE, roads), a 10% "improvement" in the published formula
                  pushes the value past 100% and, on a steep line, drives predicted dropout below zero, so the factor
                  hits the 100 cap and tops the ranking although there is almost nothing left to improve. Capping the
                  target at 100% removes that artefact. Everything else is unchanged.
"""

from __future__ import annotations

import csv
import json
import os
import statistics

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "backend", "app", "data", "niti", "prescriptive")
OUT = os.path.join(ROOT, "public", "data", "niti-prescriptive.json")
IMPROVE_BY = 0.1  # the workbook's formula hard-codes a 10% improvement
NOT_PERCENT = {"Teachers per 100 students"}


def rows(name: str) -> list[dict]:
    with open(os.path.join(SRC, name), encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def sensitivity(m: float, v: float, b: float, cap: bool, percent: bool) -> tuple[float | None, float, bool]:
    """(sensitivity %, target value, whether the published target leaves the 0..100 range)."""
    base = m * v + b
    sign = (m > 0) - (m < 0)
    target = v + v * IMPROVE_BY * -sign
    out_of_range = percent and not 0 <= target <= 100
    if cap:
        target = max(0.0, min(100.0, target)) if percent else max(0.0, target)
    if abs(base) < 1e-6:
        return None, target, out_of_range
    s = abs((m * target + b) - base) / base * 100  # base is not abs()'d in the workbook: a negative base gives 0
    return max(0.0, min(100.0, s)), target, out_of_range


def main() -> int:
    explain = {k: v for k, v in json.load(open(os.path.join(SRC, "factor_explanations.json"), encoding="utf-8")).items() if not k.startswith("_")}
    area_to_id: dict[str, str] = {}
    for d in json.load(open(os.path.join(ROOT, "public", "data", "districts.json"), encoding="utf-8"))["districts"]:
        for f in d["nitiFactors"]:
            area_to_id[f["area"]] = d["districtId"]
    names = {did: r["name"] for did, r in json.load(open(os.path.join(ROOT, "public", "data", "districts-research.json"), encoding="utf-8")).items()}

    ka = [r for r in rows("factors_all_india.csv") if r["State"].strip().upper() == "KARNATAKA"]
    d23 = {r["District"]: float(r["Field Value"]) for r in rows("dropout_2023_24.csv") if r["State"].strip().upper() == "KARNATAKA"}
    d24 = {r["district"]: float(r["dropout_rate"]) for r in rows("dropout_2024_25.csv") if r["state"].strip().upper() == "KARNATAKA"}

    factors: dict[str, dict] = {}
    for r in ka:
        name = r["Field Name"]
        factors.setdefault(name, {
            "name": name, "column": r["Column Name"], "bucket": r["Bucket"],
            "slope": float(r["M Value"]), "intercept": float(r["Intercept Value"]), "pearson": float(r["Pearson Correlation"]),
            "directionMatch": r["Direction Match"], "values": [],
        })["values"].append(float(r["Field Value"]))
    missing = sorted(set(factors) - set(explain))
    if missing:
        raise SystemExit(f"factor_explanations.json has no entry for: {missing}")

    # ranks across Karnataka's rows, 1 = best in the direction the model links to lower dropout
    def rank(name: str, v: float) -> int:
        better_high = factors[name]["slope"] < 0
        return 1 + sum(1 for x in factors[name]["values"] if (x > v if better_high else x < v))

    areas: dict[str, dict] = {}
    for r in ka:
        a = areas.setdefault(r["District"], {"area": r["District"], "districtId": area_to_id.get(r["District"]),
                                              "dropout2023_24": d23.get(r["District"]), "dropout2024_25": d24.get(r["District"]),
                                              "factors": []})
        name, v, m, b = r["Field Name"], float(r["Field Value"]), float(r["M Value"]), float(r["Intercept Value"])
        pct = name not in NOT_PERCENT
        s_niti, t_niti, oor = sensitivity(m, v, b, cap=False, percent=pct)
        s_cap, t_cap, _ = sensitivity(m, v, b, cap=True, percent=pct)
        a["factors"].append({
            "name": name, "value": round(v, 2), "predicted": round(m * v + b, 2), "rank": rank(name, v),
            "niti": {"target": round(t_niti, 2), "sensitivity": None if s_niti is None else round(s_niti, 2)},
            "feasible": {"target": round(t_cap, 2), "sensitivity": None if s_cap is None else round(s_cap, 2)},
            "pastLimit": oor,
        })
    unmatched = sorted(a for a, x in areas.items() if not x["districtId"])
    if unmatched:
        raise SystemExit(f"workbook areas with no district id: {unmatched}")

    for a in areas.values():
        for key in ("niti", "feasible"):
            total = sum(f[key]["sensitivity"] or 0 for f in a["factors"])
            for f in a["factors"]:
                f[key]["contribution"] = round((f[key]["sensitivity"] or 0) / total * 100, 1) if total else 0
            a[f"top{key.capitalize()}"] = [f["name"] for f in sorted(a["factors"], key=lambda f: -f[key]["contribution"])[:3]]
        a["factors"].sort(key=lambda f: -f["feasible"]["contribution"])

    districts: dict[str, dict] = {}
    for a in sorted(areas.values(), key=lambda a: a["area"]):
        d = districts.setdefault(a["districtId"], {"name": names.get(a["districtId"], a["area"]), "areas": []})
        d["areas"].append(a)
    for did, d in districts.items():
        # the district's own row first (Belagavi before Belagavi Chikkodi), sub-areas after
        d["areas"].sort(key=lambda a: (not d["name"].lower().startswith(a["area"].lower()[:5]), a["area"]))

    def tally(key: str) -> dict[str, int]:
        out: dict[str, int] = {}
        for a in areas.values():
            for n in a[key]:
                out[n] = out.get(n, 0) + 1
        return dict(sorted(out.items(), key=lambda kv: -kv[1]))

    out = {
        "version": 1,
        "source": {
            "file": "backend/app/data/niti/prescriptive/India_Navigation_Dashboard_v14_District_view_677.twbx",
            "from": "NITI team's India Navigation Dashboard (v14, district view)",
            "dataset": "UDISE 2023-24 and NFHS-5 (as stated in the workbook)",
            "karnatakaRows": len(areas),
            "factorsPerDistrict": len(factors),
        },
        "method": {
            "model": "For each factor, one straight line fitted across Karnataka's districts: predicted dropout = slope x factor value + intercept.",
            "sensitivity": "How much that line's predicted dropout changes if the district improves the factor by 10% of its own value (in the direction that lowers dropout), as a % of the prediction, clamped to 0-100.",
            "contribution": "A factor's sensitivity as a share of the sum over the district's 18 factors. The top three are the prescriptive changes.",
            "niti": "Ranking exactly as the workbook computes it.",
            "feasible": "Same formula, but a percentage cannot go past 100%. Factors already near 100% (toilets, libraries, CCE, roads) otherwise top the published ranking although almost nothing is left to improve.",
            "step": "The step is 10% of the district's own value, so a factor where the district already scores high gets a bigger step, and so a bigger effect, than one where it lags. Read each factor's contribution next to its rank among Karnataka's districts.",
            "caveat": "Each line is a correlation across districts, not proof that changing the factor would change dropout. The two rankings are shown side by side, never blended.",
        },
        "factors": [
            {**{k: v for k, v in f.items() if k != "values"}, **explain[f["name"]],
             "karnataka": {"min": round(min(f["values"]), 2), "median": round(statistics.median(f["values"]), 2), "max": round(max(f["values"]), 2)}}
            for f in sorted(factors.values(), key=lambda f: (f["bucket"], f["name"]))
        ],
        "statewide": {
            "topFeasible": tally("topFeasible"),
            "topNiti": tally("topNiti"),
            "pastLimitRows": sum(1 for a in areas.values() for f in a["factors"] if f["pastLimit"]),
        },
        "districts": districts,
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    print(f"wrote {os.path.relpath(OUT, ROOT)} ({os.path.getsize(OUT) // 1024} KB): {len(areas)} areas, {len(districts)} districts, {len(factors)} factors")
    print("  feasible top-3 tally:", list(out["statewide"]["topFeasible"].items())[:6])
    print("  NITI top-3 tally:   ", list(out["statewide"]["topNiti"].items())[:4])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
