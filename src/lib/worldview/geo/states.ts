/**
 * Typed loader for the precomputed India state-boundary GeoJSON
 * (public/geo/india-states.geojson).
 *
 * This file is generated OFFLINE by scripts/build-state-boundaries.mjs, which
 * dissolves the ~750 district polygons in india-districts.geojson into one
 * polygon per state via turf.union. Doing this once at build time (rather than
 * in the browser) means: no turf dependency ships to the client, no per-load
 * geometry-union cost, and no runtime fragility from malformed input.
 *
 * The state layer is purely additive: it draws a distinct, always-visible
 * state-border stroke and a solid per-state backing fill (so gaps between
 * independently-rounded district edges don't show through as seams). If the
 * file is missing, the loader resolves to `null` and the map falls back to the
 * per-district choropleth alone — nothing else depends on this file existing.
 */

import { assetUrl } from "../api";
import type { StateCode } from "../types";

export const STATE_GEOJSON_URL = assetUrl("geo/india-states.geojson");

type Position = number[];
interface PolygonGeometry {
  type: "Polygon";
  coordinates: Position[][];
}
interface MultiPolygonGeometry {
  type: "MultiPolygon";
  coordinates: Position[][][];
}
type StateGeometry = PolygonGeometry | MultiPolygonGeometry;

interface RawProps {
  st_code?: string | null;
  st_nm?: string | null;
}
interface RawFeature {
  type: "Feature";
  properties: RawProps;
  geometry: StateGeometry;
}
interface RawFeatureCollection {
  type: "FeatureCollection";
  features: RawFeature[];
}

export interface StateFeatureProps {
  stateCode: StateCode;
  stateName: string;
}

export interface StateFeature {
  type: "Feature";
  properties: StateFeatureProps;
  geometry: StateGeometry;
}

export interface StateFeatureCollection {
  type: "FeatureCollection";
  features: StateFeature[];
}

/**
 * Fetch + parse the state-boundary GeoJSON. Returns `null` (never throws) when
 * the file is absent or unreadable.
 */
export async function loadStateGeo(
  url: string = STATE_GEOJSON_URL,
  signal?: AbortSignal,
): Promise<StateFeatureCollection | null> {
  try {
    const res = await fetch(url, signal ? { signal } : undefined);
    if (!res.ok) return null;
    const raw = (await res.json()) as RawFeatureCollection;
    if (!raw || raw.type !== "FeatureCollection" || !Array.isArray(raw.features)) return null;

    const features: StateFeature[] = [];
    for (const f of raw.features) {
      if (!f.geometry || (f.geometry.type !== "Polygon" && f.geometry.type !== "MultiPolygon"))
        continue;
      const stateCode = (f.properties.st_code ?? "00").toString();
      const stateName = (f.properties.st_nm ?? "Unknown").toString();
      features.push({
        type: "Feature",
        properties: { stateCode, stateName },
        geometry: f.geometry,
      });
    }
    return { type: "FeatureCollection", features };
  } catch {
    return null;
  }
}
