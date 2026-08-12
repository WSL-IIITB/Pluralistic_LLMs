"""
Derives district_gazetteer.json from the FRONTEND's own
public/geo/india-districts.geojson, so the resolver's place-name lookup always
maps onto real, renderable district ids — the two systems can never drift.

Run: python -m app.data.build_gazetteer   (from backend/, with the venv active)

Output shape: {"name_normalized": [{"districtId": "...", "stateCode": "...",
"stateName": "...", "districtName": "..."}]} — a list because district/city
names are not always unique across states (e.g. more than one "Aurangabad").
"""

from __future__ import annotations

import json
import re

from ..config import DATA_DIR, FRONTEND_DISTRICTS_GEOJSON


def normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def build() -> dict[str, list[dict[str, str]]]:
    with open(FRONTEND_DISTRICTS_GEOJSON, encoding="utf-8") as f:
        geo = json.load(f)

    gazetteer: dict[str, list[dict[str, str]]] = {}
    seen_district_ids: set[str] = set()

    for feature in geo["features"]:
        props = feature.get("properties", {})
        district_name = str(props.get("district") or "").strip()
        state_name = str(props.get("st_nm") or "").strip()
        state_code = str(props.get("st_code") or "00").strip()
        district_code = str(props.get("dt_code") or "").strip() or normalize(district_name).replace(
            " ", "-"
        )
        district_id = f"{state_code}-{district_code}"

        if not district_name or district_id in seen_district_ids:
            continue
        seen_district_ids.add(district_id)

        entry = {
            "districtId": district_id,
            "stateCode": state_code,
            "stateName": state_name,
            "districtName": district_name,
        }

        # Index by district name and by state name (so an NER hit on "Kerala"
        # can resolve to a plausible district within that state at lower
        # confidence, distinct from an exact district-name hit).
        gazetteer.setdefault(normalize(district_name), []).append(entry)
        gazetteer.setdefault(normalize(state_name), []).append(entry)

    return gazetteer


def main() -> None:
    gazetteer = build()
    out_path = f"{DATA_DIR}/district_gazetteer.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(gazetteer, f, ensure_ascii=False)
    print(f"wrote {len(gazetteer)} name keys ({out_path})")


if __name__ == "__main__":
    main()
