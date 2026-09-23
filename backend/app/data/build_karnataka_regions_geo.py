"""
Generates public/geo/karnataka-regions.geojson: the four persona regions as
dissolved polygons, derived from the same district GeoJSON the map renders and
the membership in data/karnataka_regions.json (so the map and the backend's
district -> region mapping can never disagree).

Needs shapely, a dev-only dependency (the output file is committed, so the
running app never imports it):  pip install shapely

Run: python -m app.data.build_karnataka_regions_geo   (from backend/, venv active)
"""

from __future__ import annotations

import json
import os

from shapely.geometry import mapping, shape
from shapely.ops import unary_union

from ..config import FRONTEND_DISTRICTS_GEOJSON, REPO_ROOT
from ..karnataka import karnataka_state_code, persona_regions

OUTPUT = os.path.join(REPO_ROOT, "public", "geo", "karnataka-regions.geojson")
# ~0.5 km -- invisible at region zoom, keeps the file small.
_SIMPLIFY_DEG = 0.005


def main() -> None:
    with open(FRONTEND_DISTRICTS_GEOJSON, encoding="utf-8") as f:
        districts = json.load(f)["features"]

    state_code = karnataka_state_code()
    geom_by_district: dict[str, object] = {}
    for feat in districts:
        props = feat.get("properties") or {}
        if str(props.get("st_code")) != state_code or not props.get("dt_code"):
            continue
        geom_by_district[f"{state_code}-{props['dt_code']}"] = shape(feat["geometry"]).buffer(0)

    features = []
    for region in persona_regions():
        missing = [d for d in region["district_ids"] if d not in geom_by_district]
        if missing:
            raise SystemExit(f"{region['id']}: districts missing from the map GeoJSON: {missing}")
        merged = unary_union([geom_by_district[d] for d in region["district_ids"]])
        merged = merged.simplify(_SIMPLIFY_DEG, preserve_topology=True)
        label = merged.representative_point()
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "regionId": region["id"],
                    "name": region["name"],
                    "shortName": region["short_name"],
                    "color": region["color"],
                    "labelPoint": [round(label.x, 4), round(label.y, 4)],
                    "districtIds": region["district_ids"],
                    "bbox": [round(v, 4) for v in merged.bounds],
                },
                "geometry": mapping(merged),
            }
        )

    assigned = {d for r in persona_regions() for d in r["district_ids"]}
    unassigned = sorted(set(geom_by_district) - assigned)
    if unassigned:
        raise SystemExit(f"Karnataka districts not assigned to any region: {unassigned}")

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f, separators=(",", ":"))
    print(f"wrote {OUTPUT} ({len(features)} regions, {len(assigned)} districts)")


if __name__ == "__main__":
    main()
