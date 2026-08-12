# District boundaries

The map loads **`india-districts.geojson`** from this folder at runtime (see
`src/lib/worldview/geo/districts.ts` → `DISTRICT_GEOJSON_URL`).

## What ships here

`india-districts.geojson` — a simplified, Census-2011 district FeatureCollection
(760 features, ~0.5 MB, coordinates rounded to 3 decimals). It's derived from the
public [udit-001/india-maps-data](https://github.com/udit-001/india-maps-data)
dataset. Every feature carries:

| property   | meaning                              | example        |
| ---------- | ------------------------------------ | -------------- |
| `st_code`  | Census/LGD 2-digit state code        | `"09"` (UP)    |
| `dt_code`  | Census/LGD district code             | `"137"`        |
| `st_nm`    | state name                           | `"Uttar Pradesh"` |
| `district` | district name                        | `"Amroha"`     |

The loader keys each district as **`${st_code}-${dt_code}`** (see `makeDistrictId`).

## Dropping in official boundaries

To use Survey of India / Datameet boundaries instead, replace this file with a
GeoJSON `FeatureCollection` whose features expose the same four properties
(`st_code`, `dt_code`, `st_nm`, `district`). No code changes are needed — the
loader recomputes centroids and bboxes on load. If your source omits `dt_code`
for some features, the loader synthesises a stable id from the district name.

If the file is missing or unreadable, the map degrades to the dark backdrop and
the rest of the dashboard keeps working.

## Regenerating the mock district distribution

The offline demo's district→viewpoint assignments live in
`src/lib/worldview/stream/generatedDistricts.ts`. Regenerate them from whatever
GeoJSON is in this folder with:

```sh
node scripts/generate-mock-districts.mjs
```
