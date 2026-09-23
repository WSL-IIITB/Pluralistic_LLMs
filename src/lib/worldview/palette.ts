/**
 * Categorical data palette + rendering constants.
 *
 * The RGB tuples below are the sRGB equivalents of the `--cluster-1..6` oklch
 * design tokens in styles.css, so deck.gl map columns match the CSS legend
 * swatches exactly. If you retune the tokens, regenerate these (oklch→sRGB).
 */

import type { ClusterId, ConfidenceTier, RGBAColor, StateCode } from "./types";

/** Ordered categorical palette, keyed to `--cluster-1..6`. */
export const CLUSTER_PALETTE: readonly RGBAColor[] = [
  [249, 183, 63], // cluster-1  amber / gold
  [250, 137, 39], // cluster-2  orange
  [233, 72, 61], // cluster-3  red-orange
  [225, 90, 123], // cluster-4  rose
  [238, 208, 89], // cluster-5  gold
  [243, 126, 97], // cluster-6  coral
];

/** Pick a palette colour by index (wraps for >6 clusters). */
export function paletteColor(index: number): RGBAColor {
  const c =
    CLUSTER_PALETTE[
      ((index % CLUSTER_PALETTE.length) + CLUSTER_PALETTE.length) % CLUSTER_PALETTE.length
    ];
  // Non-null: index is always in-range after the modulo above.
  return c ?? [249, 183, 63];
}

/**
 * Bit-reversal ("van der Corput") sequence over [0, 1) — whatever prefix has
 * been consumed so far is already maximally spread, regardless of how many
 * more entries are eventually needed. Used to space out one region's
 * successive clusters' lightness, since a region's eventual cluster count
 * isn't known until the run completes.
 */
const LIGHTNESS_STEPS: readonly number[] = [0.5, 1, 0, 0.75, 0.25, 0.875, 0.125, 0.625];

/** Standard HSL -> sRGB conversion, 0-255 integer channels. */
function hslToRgb(h: number, s: number, l: number): RGBAColor {
  const c = (1 - Math.abs(2 * l - 1)) * s;
  const hPrime = h / 60;
  const x = c * (1 - Math.abs((hPrime % 2) - 1));
  let r1 = 0;
  let g1 = 0;
  let b1 = 0;
  if (hPrime < 1) [r1, g1, b1] = [c, x, 0];
  else if (hPrime < 2) [r1, g1, b1] = [x, c, 0];
  else if (hPrime < 3) [r1, g1, b1] = [0, c, x];
  else if (hPrime < 4) [r1, g1, b1] = [0, x, c];
  else if (hPrime < 5) [r1, g1, b1] = [x, 0, c];
  else [r1, g1, b1] = [c, 0, x];
  const m = l - c / 2;
  const toByte = (v: number) => Math.round((v + m) * 255);
  return [toByte(r1), toByte(g1), toByte(b1)];
}

function rgbToHsl([r, g, b]: RGBAColor): [number, number, number] {
  const rn = r / 255;
  const gn = g / 255;
  const bn = b / 255;
  const max = Math.max(rn, gn, bn);
  const min = Math.min(rn, gn, bn);
  const l = (max + min) / 2;
  const d = max - min;
  if (d === 0) return [0, 0, l];
  const s = d / (1 - Math.abs(2 * l - 1));
  let h: number;
  if (max === rn) h = ((gn - bn) / d) % 6;
  else if (max === gn) h = (bn - rn) / d + 2;
  else h = (rn - gn) / d + 4;
  return [(h * 60 + 360) % 360, s, l];
}

/**
 * Colour for the `indexWithinRegion`-th cluster of a Karnataka region: the
 * region's own identity hue (see karnataka.ts), stepped by lightness so a
 * region's viewpoints read as one family and never collide with another region's.
 */
export function paletteColorForRegionHue(base: RGBAColor, indexWithinRegion: number): RGBAColor {
  const [h, s] = rgbToHsl(base);
  const stepIndex =
    ((indexWithinRegion % LIGHTNESS_STEPS.length) + LIGHTNESS_STEPS.length) %
    LIGHTNESS_STEPS.length;
  const t = LIGHTNESS_STEPS[stepIndex] ?? 0.5;
  return hslToRgb(h, Math.max(0.35, Math.min(s, 0.85)), 0.38 + 0.34 * t);
}

/** Opacity applied to columns / swatches by confidence tier (0–1). */
export const CONFIDENCE_OPACITY: Record<ConfidenceTier, number> = {
  high: 1,
  medium: 0.7,
  low: 0.42,
};

/** Neutral fill for districts that fell back to their state aggregate. */
export const STATE_FALLBACK_RGB: RGBAColor = [120, 120, 130];

/** Column alpha (0–255) for a given confidence tier. */
export function confidenceAlpha(tier: ConfidenceTier): number {
  return Math.round(255 * (CONFIDENCE_OPACITY[tier] ?? 1));
}

/** `rgb()` / `rgba()` CSS string from a deck.gl colour tuple. */
export function rgbaCss(color: RGBAColor, alpha?: number): string {
  const [r, g, b] = color;
  const a = alpha ?? (color.length === 4 ? (color[3] ?? 255) / 255 : 1);
  return a >= 1 ? `rgb(${r}, ${g}, ${b})` : `rgba(${r}, ${g}, ${b}, ${a.toFixed(3)})`;
}

/** Apply an alpha channel to a colour tuple, returning a new tuple. */
export function withAlpha(color: RGBAColor, alpha0to255: number): RGBAColor {
  return [color[0], color[1], color[2], Math.max(0, Math.min(255, Math.round(alpha0to255)))];
}

// ─────────────────────────────────────────────────────────────────────────────
// Camera / map constants
// ─────────────────────────────────────────────────────────────────────────────

export interface MapViewState {
  longitude: number;
  latitude: number;
  zoom: number;
  pitch: number;
  bearing: number;
}

/** Default "country" camera centred on India. */
export const INDIA_VIEW: MapViewState = {
  longitude: 79.5,
  latitude: 22.5,
  zoom: 3.7,
  pitch: 45,
  bearing: 0,
};

/** Zoom thresholds that drive the bottom-right view chip + drill-down. */
export const ZOOM_TIERS = {
  country: 4.4,
  state: 6.2,
} as const;

export type ViewTier = "Country view" | "State view" | "District view";

export function viewTierForZoom(zoom: number): ViewTier {
  if (zoom < ZOOM_TIERS.country) return "Country view";
  if (zoom < ZOOM_TIERS.state) return "State view";
  return "District view";
}

/**
 * Column height in metres per unit of post volume. deck.gl ColumnLayer
 * `elevationScale` multiplies the datum's `volume`; tuned so a busy district
 * reads as a tall pillar at country zoom without clipping neighbours.
 */
export const COLUMN_ELEVATION_SCALE = 900;
export const COLUMN_RADIUS_METERS = 14000;
