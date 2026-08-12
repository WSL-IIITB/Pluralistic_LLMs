/**
 * Dissolves public/geo/india-districts.geojson into one polygon per state and
 * writes public/geo/india-states.geojson. Run this once whenever the district
 * GeoJSON changes — the app loads the precomputed output at runtime (no turf
 * dependency ships to the client; this script is dev-only).
 *
 * Why precompute: dissolving ~750 district polygons into state boundaries is a
 * geometry-heavy operation (turf.union) that's fragile on malformed input and
 * too slow to redo on every page load. Doing it once here means the browser
 * just fetches a small static file.
 */
import fs from "node:fs";
import * as turf from "@turf/turf";

const SRC = "./public/geo/india-districts.geojson";
const OUT = "./public/geo/india-states.geojson";
const PREC = 3;

const src = JSON.parse(fs.readFileSync(SRC, "utf8"));

const byState = new Map();
for (const f of src.features) {
  const code = String(f.properties.st_code ?? "00");
  if (!byState.has(code)) byState.set(code, { name: f.properties.st_nm ?? code, features: [] });
  byState.get(code).features.push(f);
}

const round = (n) => Math.round(n * 10 ** PREC) / 10 ** PREC;
function roundGeometry(geometry) {
  const roundRing = (ring) => ring.map(([x, y]) => [round(x), round(y)]);
  if (geometry.type === "Polygon") {
    return { type: "Polygon", coordinates: geometry.coordinates.map(roundRing) };
  }
  if (geometry.type === "MultiPolygon") {
    return {
      type: "MultiPolygon",
      coordinates: geometry.coordinates.map((poly) => poly.map(roundRing)),
    };
  }
  return geometry;
}

const features = [];
let failed = 0;
for (const [code, { name, features: districtFeatures }] of byState) {
  try {
    const fc = { type: "FeatureCollection", features: districtFeatures };
    const unioned = turf.union(fc);
    if (!unioned) throw new Error("union returned null");
    features.push({
      type: "Feature",
      properties: { st_code: code, st_nm: name },
      geometry: roundGeometry(unioned.geometry),
    });
  } catch (err) {
    failed++;
    console.warn(`state ${code} (${name}) failed to dissolve: ${err.message} — skipped`);
  }
}

const out = { type: "FeatureCollection", features };
fs.writeFileSync(OUT, JSON.stringify(out));
const sizeKb = (fs.statSync(OUT).size / 1024).toFixed(1);
console.log(
  `wrote ${features.length}/${byState.size} states (${failed} failed) to ${OUT} (${sizeKb} KB)`,
);
