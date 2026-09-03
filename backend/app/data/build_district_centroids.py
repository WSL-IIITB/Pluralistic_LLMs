"""
Derives district_centroids.json (districtId -> [lng, lat]) from the same
FRONTEND geojson build_gazetteer.py reads, using the identical district_id
convention (imports `normalize` from build_gazetteer so the two files can
never drift apart on id generation).

Vertex-averaged centroid -- ports the frontend's own centroidAndBBox()
(src/lib/worldview/geo/districts.ts) so region-inference's geographic-sanity
signal derives from the exact same source of truth the map renders, rather
than a second, possibly-diverging approximation. Deliberately NOT porting the
bbox half or building adjacency/shared-border data -- region-inference only
needs a coarse "how far apart are these districts" signal, which a centroid
already gives it.

Run: python -m app.data.build_district_centroids   (from backend/, venv active)
"""

from __future__ import annotations

import json
from typing import Iterator

from ..config import DATA_DIR, FRONTEND_DISTRICTS_GEOJSON
from .build_gazetteer import normalize


def _each_ring(geometry: dict) -> Iterator[list]:
    coords = geometry.get("coordinates") or []
    gtype = geometry.get("type")
    if gtype == "Polygon":
        for ring in coords:
            yield ring
    elif gtype == "MultiPolygon":
        for polygon in coords:
            for ring in polygon:
                yield ring


def _centroid(geometry: dict) -> tuple[float, float] | None:
    sx = 0.0
    sy = 0.0
    n = 0
    for ring in _each_ring(geometry):
        for pos in ring:
            if len(pos) < 2:
                continue
            x, y = pos[0], pos[1]
            if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
                continue
            sx += x
            sy += y
            n += 1
    if n == 0:
        return None
    return (sx / n, sy / n)


def build() -> dict[str, list[float]]:
    with open(FRONTEND_DISTRICTS_GEOJSON, encoding="utf-8") as f:
        geo = json.load(f)

    centroids: dict[str, list[float]] = {}

    for feature in geo["features"]:
        props = feature.get("properties", {})
        district_name = str(props.get("district") or "").strip()
        state_code = str(props.get("st_code") or "00").strip()
        district_code = str(props.get("dt_code") or "").strip() or normalize(district_name).replace(
            " ", "-"
        )
        district_id = f"{state_code}-{district_code}"

        geometry = feature.get("geometry")
        if not district_name or district_id in centroids or not geometry:
            continue

        centroid = _centroid(geometry)
        if centroid is None:
            continue
        centroids[district_id] = [centroid[0], centroid[1]]

    return centroids


def main() -> None:
    centroids = build()
    out_path = f"{DATA_DIR}/district_centroids.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(centroids, f)
    print(f"wrote {len(centroids)} district centroids ({out_path})")


if __name__ == "__main__":
    main()
