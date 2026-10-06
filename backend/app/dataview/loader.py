"""
Loads casefile.xlsx + dataview_district_crosswalk.json into a CaseFile.
Lazy module-level cache, mirroring the pattern build.py uses for the
gazetteer (load once per process, static input files, no per-request
variation).
"""

from __future__ import annotations

import json

import openpyxl

from ..config import DATA_DIR
from .models import CaseFile, DistrictRecord

_CASEFILE_PATH = f"{DATA_DIR}/dataview/raw/casefile.xlsx"
_CASEFILE_SHEET = "RUN00676_ALL_INDIA_CASEFILE_MAT"
_CROSSWALK_PATH = f"{DATA_DIR}/dataview_district_crosswalk.json"

_NON_FACTOR_COLUMNS = {"state", "district", "dropout_rate"}

_casefile_cache: CaseFile | None = None


def _load_crosswalk() -> dict[str, dict[str, str]]:
    with open(_CROSSWALK_PATH, encoding="utf-8") as f:
        return json.load(f)


def _build_casefile() -> CaseFile:
    crosswalk = _load_crosswalk()

    wb = openpyxl.load_workbook(_CASEFILE_PATH, read_only=True, data_only=True)
    ws = wb[_CASEFILE_SHEET]
    rows = ws.iter_rows(values_only=True)
    header = list(next(rows))

    factor_names = [c for c in header if c not in _NON_FACTOR_COLUMNS]
    col_index = {name: i for i, name in enumerate(header)}

    districts: list[DistrictRecord] = []
    for row in rows:
        # read_only worksheets trim trailing empty cells off a row tuple, so
        # a row shorter than the header is just "everything after it is
        # blank" -- pad rather than treat it as malformed.
        if len(row) < len(header):
            row = row + (None,) * (len(header) - len(row))

        state = row[col_index["state"]]
        district = row[col_index["district"]]
        if not state or not district:
            continue
        dropout_rate = row[col_index["dropout_rate"]]
        if dropout_rate is None:
            continue  # a district with no target value can't feed regression or be scored

        raw_key = f"{state}|{district}"
        entry = crosswalk.get(raw_key, {})
        district_id = entry.get("districtId") or None

        factors: dict[str, float | None] = {}
        for name in factor_names:
            value = row[col_index[name]]
            factors[name] = float(value) if isinstance(value, (int, float)) else None

        districts.append(
            DistrictRecord(
                raw_key=raw_key,
                district_id=district_id,
                state_name=str(state),
                district_name=str(district),
                dropout_rate=float(dropout_rate),
                factors=factors,
            )
        )

    wb.close()
    return CaseFile(factor_names=factor_names, districts=districts)


def load_casefile() -> CaseFile:
    global _casefile_cache
    if _casefile_cache is None:
        _casefile_cache = _build_casefile()
    return _casefile_cache
