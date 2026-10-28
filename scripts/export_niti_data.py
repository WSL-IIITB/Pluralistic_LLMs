"""Writes public/data/niti-factors.json: every row of the two UIDAI/NITI dominant-factor workbooks (all India).

    backend/.venv/bin/python scripts/export_niti_data.py      (needs openpyxl, which the backend has)

Source files: backend/app/data/niti/dominant_factors_state_level.xlsx and ..._district_level.xlsx. Each holds one row
per (state, district) with a factor name and an unlabelled value column; State is filled only on the first row of each
state block. The two files share the same 928 (state, district) keys, so rows are paired. Values are kept as published
(rounded to 4 significant figures). scripts/export_static_data.py calls this.
"""

from __future__ import annotations

import json
import math
import os

import openpyxl

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
NITI = os.path.join(ROOT, "backend", "app", "data", "niti")
OUT = os.path.join(ROOT, "public", "data", "niti-factors.json")
FILES = {"state": "dominant_factors_state_level.xlsx", "district": "dominant_factors_district_level.xlsx"}
METHODS = {
    "state": "One factor is ranked highest for the whole state; each district's value is its own figure for that factor.",
    "district": "A factor is selected for each district on its own; the value is that factor's fitted weight in the analysis, not a raw percentage.",
}


def sig(x: float) -> float:
    return 0.0 if x == 0 else round(x, max(0, 3 - int(math.floor(math.log10(abs(x))))))


def load(name: str) -> tuple[list[tuple[str, str, str, float]], list[dict]]:
    """-> (district rows, factor-only rows). Five state blocks also list factor names with no district and a 0 value;
    they are kept separately so nothing in the workbook is silently dropped."""
    ws = openpyxl.load_workbook(os.path.join(NITI, name), read_only=True, data_only=True).worksheets[0]
    out, extra, state = [], [], None
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row[0]:
            state = str(row[0]).strip()
        if state and row[1] and row[2] and row[3] is not None:
            out.append((state, str(row[1]).strip(), str(row[2]).strip(), float(row[3])))
        elif state and row[2]:
            extra.append({"state": state, "factor": str(row[2]).strip(), "value": None if row[3] is None else sig(float(row[3]))})
    return out, extra


def main() -> None:
    (s, s_extra), (d, d_extra) = load(FILES["state"]), load(FILES["district"])
    dmap = {(a, b): (f, v) for a, b, f, v in d}
    rows = []
    for state, district, f, v in s:
        df, dv = dmap.get((state, district), (None, None))
        rows.append({"state": state, "district": district, "stateFactor": f, "stateValue": sig(v),
                     "districtFactor": df, "districtValue": None if dv is None else sig(dv)})
    data = {
        "source": {"files": [f"backend/app/data/niti/{n}" for n in FILES.values()], "rows": len(rows),
                   "states": len({r["state"] for r in rows}), "unpaired": len(s) - sum(1 for r in rows if r["districtFactor"]),
                   "factorOnlyRows": {"state": len(s_extra), "district": len(d_extra)}},
        "methods": METHODS,
        "rows": rows,
        # factor names listed under a state with no district and a 0 value (likely an export artefact); kept for completeness
        "factorOnlyRows": {"state": s_extra, "district": d_extra},
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"  niti-factors.json: {len(rows)} district rows, {data['source']['states']} states/UTs, "
          f"{len(s_extra)}+{len(d_extra)} factor-only rows, {os.path.getsize(OUT) // 1024} KB")


if __name__ == "__main__":
    main()
