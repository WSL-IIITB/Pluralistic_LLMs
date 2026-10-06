/**
 * Karnataka's six persona regions — the geographic unit the Story View works
 * in. Mirrors backend/app/data/karnataka_regions.json (ids, names, colours,
 * persona variants); the region geometry itself is
 * public/geo/karnataka-regions.geojson, generated from that same file. Keep
 * these in sync by hand.
 *
 * Colours are a 6-slot categorical set: four reused unchanged from the
 * earlier 4-region mapping (Old Mysuru, Karavali, Malnad, Kitturu Karnataka),
 * two new (Bayaluseeme's purple, Kalyana Karnataka's brick red). Not yet
 * re-validated for worst-case CVD ΔE at 6 slots (the 4-slot set was); every
 * use still pairs colour with a name label as the safety net.
 */

import type { PersonaVariantId, RegionId, RGBAColor } from "./types";

export interface PersonaVariantMeta {
  id: PersonaVariantId;
  label: string;
}

export interface KarnatakaRegionMeta {
  id: RegionId;
  name: string;
  shortName: string;
  color: RGBAColor;
  personas: readonly PersonaVariantMeta[];
}

const MALE_FEMALE: readonly PersonaVariantMeta[] = [
  { id: "male", label: "Male resident" },
  { id: "female", label: "Female resident" },
] as const;

export const KARNATAKA_REGIONS: readonly KarnatakaRegionMeta[] = [
  {
    id: "old-mysuru",
    name: "Old Mysuru (Southern) Region",
    shortName: "Old Mysuru",
    color: [213, 81, 129],
    personas: MALE_FEMALE,
  },
  {
    id: "bayaluseeme",
    name: "Bayaluseeme (Central Plains) Region",
    shortName: "Bayaluseeme",
    color: [124, 91, 188],
    personas: MALE_FEMALE,
  },
  {
    id: "karavali",
    name: "Karavali (Coastal) Region",
    shortName: "Karavali",
    color: [57, 135, 229],
    personas: MALE_FEMALE,
  },
  {
    id: "malnad",
    name: "Malnad Region",
    shortName: "Malnad",
    color: [0, 131, 0],
    personas: MALE_FEMALE,
  },
  {
    id: "kitturu-karnataka",
    name: "Kitturu Karnataka (North-west) Region",
    shortName: "Kitturu Karnataka",
    color: [201, 133, 0],
    personas: MALE_FEMALE,
  },
  {
    id: "kalyana-karnataka",
    name: "Kalyana Karnataka (North-east) Region",
    shortName: "Kalyana Karnataka",
    color: [196, 58, 58],
    personas: MALE_FEMALE,
  },
] as const;

/** Posts about Karnataka as a whole rather than one region — no persona, no polygon. */
export const STATEWIDE_REGION_ID: RegionId = "karnataka-statewide";
export const STATEWIDE_COLOR: RGBAColor = [150, 148, 140];

/** Every persona variant id used across all regions, in first-seen order
 *  (today just ["male", "female"]) — for building a variant selector without
 *  hardcoding the pair. */
export const PERSONA_VARIANTS: readonly PersonaVariantMeta[] = (() => {
  const seen = new Map<PersonaVariantId, PersonaVariantMeta>();
  for (const region of KARNATAKA_REGIONS) {
    for (const p of region.personas) if (!seen.has(p.id)) seen.set(p.id, p);
  }
  return Array.from(seen.values());
})();

export const DEFAULT_PERSONA_VARIANT: PersonaVariantId = PERSONA_VARIANTS[0]?.id ?? "male";

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

export function personaVariantLabel(regionId: RegionId | null | undefined, personaId: PersonaVariantId | null | undefined): string {
  if (!personaId) return "";
  return regionMeta(regionId)?.personas.find((p) => p.id === personaId)?.label ?? personaId;
}

/** Camera framing Karnataka. */
export const KARNATAKA_VIEW = {
  longitude: 76.3,
  latitude: 14.85,
  zoom: 6.1,
  pitch: 40,
  bearing: 0,
};

/**
 * The one topic this study explores. The query box shows it but is disabled —
 * the whole dashboard (personas, district research, divergence) is built
 * around this question.
 */
export const FIXED_QUERY = "Secondary school dropouts in India";
