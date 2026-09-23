/**
 * Karnataka's four persona regions — the geographic unit Story View works in.
 * Mirrors backend/app/data/karnataka_regions.json (ids, names, colours); the
 * region geometry itself is public/geo/karnataka-regions.geojson, generated
 * from that same file. Keep the two in sync by hand.
 *
 * Colours are a validated 4-slot categorical set (dark surface, all-pairs):
 * worst CVD ΔE 6.9, so every use pairs colour with a name label.
 */

import type { RegionId, RGBAColor } from "./types";

export interface KarnatakaRegionMeta {
  id: RegionId;
  name: string;
  shortName: string;
  color: RGBAColor;
}

export const KARNATAKA_REGIONS: readonly KarnatakaRegionMeta[] = [
  {
    id: "mysuru-bengaluru",
    name: "Mysuru-Bengaluru Region",
    shortName: "Mysuru-Bengaluru",
    color: [213, 81, 129],
  },
  {
    id: "north-karnataka",
    name: "Northern Karnataka Region",
    shortName: "North Karnataka",
    color: [201, 133, 0],
  },
  { id: "karavali", name: "Karavali Coastal Region", shortName: "Karavali", color: [57, 135, 229] },
  { id: "malnad", name: "Malnad Region", shortName: "Malnad", color: [0, 131, 0] },
] as const;

/** Posts about Karnataka as a whole rather than one region — no persona, no polygon. */
export const STATEWIDE_REGION_ID: RegionId = "karnataka-statewide";
export const STATEWIDE_COLOR: RGBAColor = [150, 148, 140];

const BY_ID = new Map(KARNATAKA_REGIONS.map((r) => [r.id, r]));

export function regionMeta(id: RegionId | null | undefined): KarnatakaRegionMeta | undefined {
  return id ? BY_ID.get(id) : undefined;
}

export function regionColor(id: RegionId | null | undefined): RGBAColor {
  return regionMeta(id)?.color ?? STATEWIDE_COLOR;
}

export function regionShortName(id: RegionId | null | undefined): string {
  if (id === STATEWIDE_REGION_ID) return "Statewide";
  return regionMeta(id)?.shortName ?? id ?? "Unknown";
}

/** Camera framing Karnataka. */
export const KARNATAKA_VIEW = {
  longitude: 76.3,
  latitude: 14.85,
  zoom: 6.1,
  pitch: 40,
  bearing: 0,
};
