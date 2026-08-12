/**
 * Typed India-district GeoJSON loader.
 *
 * ── Where to drop your own boundaries ────────────────────────────────────────
 * The app fetches `/geo/india-districts.geojson` (see {@link DISTRICT_GEOJSON_URL}).
 * A working, simplified Census-2011 district file ships in `public/geo/`. To use
 * official Survey of India / Datameet boundaries, replace that file with a
 * FeatureCollection whose feature properties include `st_code`, `dt_code`,
 * `st_nm`, `district` (LGD / Census codes). No code changes needed.
 *
 * The loader is defensive: if the file is missing or malformed it resolves to
 * `null` and the map degrades to its column-only / placeholder rendering.
 */

import { makeDistrictId, type DistrictId, type StateCode } from "../types";

export const DISTRICT_GEOJSON_URL = "/geo/india-districts.geojson";

// Minimal GeoJSON shapes (avoids a hard dep on @types/geojson).
type Position = number[];
interface PolygonGeometry {
  type: "Polygon";
  coordinates: Position[][];
}
interface MultiPolygonGeometry {
  type: "MultiPolygon";
  coordinates: Position[][][];
}
type DistrictGeometry = PolygonGeometry | MultiPolygonGeometry;

interface RawProps {
  district?: string | null;
  dt_code?: string | null;
  st_nm?: string | null;
  st_code?: string | null;
}

interface RawFeature {
  type: "Feature";
  properties: RawProps;
  geometry: DistrictGeometry;
}

interface RawFeatureCollection {
  type: "FeatureCollection";
  features: RawFeature[];
}

/** Properties we inject so deck.gl accessors can key straight into the store. */
export interface DistrictFeatureProps {
  districtId: DistrictId;
  stateCode: StateCode;
  districtName: string;
  stateName: string;
}

export interface DistrictFeature {
  type: "Feature";
  properties: DistrictFeatureProps;
  geometry: DistrictGeometry;
}

export interface DistrictFeatureCollection {
  type: "FeatureCollection";
  features: DistrictFeature[];
}

export type BBox = [number, number, number, number]; // minLng, minLat, maxLng, maxLat

export interface LoadedDistrict {
  districtId: DistrictId;
  name: string;
  stateCode: StateCode;
  stateName: string;
  centroid: [number, number]; // lng, lat
  bbox: BBox;
}

export interface LoadedState {
  stateCode: StateCode;
  stateName: string;
  districtIds: DistrictId[];
  centroid: [number, number];
  bbox: BBox;
}

export interface DistrictGeo {
  featureCollection: DistrictFeatureCollection;
  districts: Record<DistrictId, LoadedDistrict>;
  states: Record<StateCode, LoadedState>;
  /** Stable render order (feature order in the source file). */
  order: DistrictId[];
}

function slug(input: string): string {
  return input
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

function eachRing(geometry: DistrictGeometry, visit: (ring: Position[]) => void): void {
  if (geometry.type === "Polygon") {
    for (const ring of geometry.coordinates) visit(ring);
  } else {
    for (const poly of geometry.coordinates) for (const ring of poly) visit(ring);
  }
}

/** Vertex-averaged centroid + bbox of a district geometry (lng, lat). */
function centroidAndBBox(geometry: DistrictGeometry): { centroid: [number, number]; bbox: BBox } {
  let sx = 0;
  let sy = 0;
  let n = 0;
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  eachRing(geometry, (ring) => {
    for (const pos of ring) {
      const x = pos[0];
      const y = pos[1];
      if (typeof x !== "number" || typeof y !== "number") continue;
      sx += x;
      sy += y;
      n += 1;
      if (x < minX) minX = x;
      if (y < minY) minY = y;
      if (x > maxX) maxX = x;
      if (y > maxY) maxY = y;
    }
  });
  if (n === 0) {
    return { centroid: [0, 0], bbox: [0, 0, 0, 0] };
  }
  return { centroid: [sx / n, sy / n], bbox: [minX, minY, maxX, maxY] };
}

function unionBBox(a: BBox, b: BBox): BBox {
  return [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[2], b[2]), Math.max(a[3], b[3])];
}

/**
 * Fetch + parse the district GeoJSON. Returns `null` (never throws) when the
 * file is absent or unreadable, so callers can fall back gracefully.
 */
export async function loadDistrictGeo(
  url: string = DISTRICT_GEOJSON_URL,
  signal?: AbortSignal,
): Promise<DistrictGeo | null> {
  try {
    const res = await fetch(url, signal ? { signal } : undefined);
    if (!res.ok) return null;
    const raw = (await res.json()) as RawFeatureCollection;
    if (!raw || raw.type !== "FeatureCollection" || !Array.isArray(raw.features)) return null;
    return indexFeatures(raw);
  } catch {
    return null;
  }
}

/** Build the indexed {@link DistrictGeo} from a parsed FeatureCollection. */
export function indexFeatures(raw: RawFeatureCollection): DistrictGeo {
  const features: DistrictFeature[] = [];
  const districts: Record<DistrictId, LoadedDistrict> = {};
  const states: Record<StateCode, LoadedState> = {};
  const order: DistrictId[] = [];

  raw.features.forEach((f, i) => {
    if (!f.geometry || (f.geometry.type !== "Polygon" && f.geometry.type !== "MultiPolygon"))
      return;
    const p = f.properties ?? {};
    const stateCode = (p.st_code ?? "00").toString();
    const stateName = (p.st_nm ?? "Unknown").toString();
    const districtName = (p.district ?? "").toString() || `District ${i}`;
    const districtCode = (p.dt_code ?? "").toString() || slug(districtName) || `x${i}`;
    const districtId = makeDistrictId(stateCode, districtCode);

    const { centroid, bbox } = centroidAndBBox(f.geometry);

    features.push({
      type: "Feature",
      properties: { districtId, stateCode, districtName, stateName },
      geometry: f.geometry,
    });

    // First feature wins for a repeated districtId (MultiPolygon split as
    // separate features share one district); still union their bbox.
    const existing = districts[districtId];
    if (existing) {
      existing.bbox = unionBBox(existing.bbox, bbox);
    } else {
      districts[districtId] = {
        districtId,
        name: districtName,
        stateCode,
        stateName,
        centroid,
        bbox,
      };
      order.push(districtId);
    }

    const st = states[stateCode];
    if (st) {
      if (!st.districtIds.includes(districtId)) st.districtIds.push(districtId);
      st.bbox = unionBBox(st.bbox, bbox);
    } else {
      states[stateCode] = {
        stateCode,
        stateName,
        districtIds: [districtId],
        centroid: [...centroid],
        bbox: [...bbox],
      };
    }
  });

  // Recompute state centroids as the mean of their districts' centroids.
  for (const code of Object.keys(states)) {
    const st = states[code];
    if (!st) continue;
    let sx = 0;
    let sy = 0;
    let n = 0;
    for (const id of st.districtIds) {
      const d = districts[id];
      if (!d) continue;
      sx += d.centroid[0];
      sy += d.centroid[1];
      n += 1;
    }
    if (n > 0) st.centroid = [sx / n, sy / n];
  }

  return { featureCollection: { type: "FeatureCollection", features }, districts, states, order };
}
