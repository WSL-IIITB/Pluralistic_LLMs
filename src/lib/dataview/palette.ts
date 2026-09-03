/**
 * Data View's sequential numeric colour ramps.
 *
 * Separate from `src/lib/worldview/palette.ts`'s CATEGORICAL cluster palette
 * (one hue per discovered viewpoint) — this file is a NEW, independent
 * sequential scale for continuous numeric choropleths (dropout rate /
 * intervention index), and never touches or extends the worldview palette.
 * Dependency-free, same as worldview/palette.ts: simple hand-rolled linear
 * RGB interpolation, no external color library.
 */

/** 0–255 integer RGB triple. */
export type RGB = [number, number, number];

/** [min, max] value range a ramp is stretched across. */
export type NumericDomain = [number, number];

/**
 * Dropout-rate ramp: light yellow → deep red. Higher value reads as "worse /
 * more attention needed", matching the reference Do-Board's convention.
 * (5-stop sequential warm ramp, in the spirit of ColorBrewer's YlOrRd.)
 */
const DROPOUT_RATE_RAMP: readonly RGB[] = [
  [255, 255, 204],
  [255, 237, 160],
  [254, 178, 76],
  [240, 59, 32],
  [128, 0, 38],
];

/**
 * Intervention-index ramp: light → dark BLUE, deliberately a different hue
 * family from the dropout-rate ramp so the two choropleth modes are never
 * visually confusable at a glance. Input is already normalized to [0, 1] by
 * the backend, so no domain stretching is needed here.
 */
const INTERVENTION_INDEX_RAMP: readonly RGB[] = [
  [240, 249, 255],
  [189, 215, 231],
  [107, 174, 214],
  [49, 130, 189],
  [8, 81, 156],
];

/** Piecewise-linear interpolation across an ordered ramp, `t` clamped to [0, 1]. */
function interpolateRamp(ramp: readonly RGB[], t: number): RGB {
  const clamped = Math.max(0, Math.min(1, t));
  const first = ramp[0];
  if (ramp.length === 1 && first) return first;

  const scaled = clamped * (ramp.length - 1);
  const i = Math.max(0, Math.min(ramp.length - 2, Math.floor(scaled)));
  const frac = scaled - i;
  const a = ramp[i] ?? first ?? [0, 0, 0];
  const b = ramp[i + 1] ?? a;

  return [
    Math.round(a[0] + (b[0] - a[0]) * frac),
    Math.round(a[1] + (b[1] - a[1]) * frac),
    Math.round(a[2] + (b[2] - a[2]) * frac),
  ];
}

/**
 * Colour for a raw dropout-rate-style value, linearly mapped across `domain`
 * (min → 0, max → 1) and clamped at the endpoints — a value outside `domain`
 * still renders as the nearest endpoint colour rather than extrapolating.
 */
export function numericColor(value: number, domain: NumericDomain): RGB {
  const [lo, hi] = domain;
  const t = hi > lo ? (value - lo) / (hi - lo) : 0;
  return interpolateRamp(DROPOUT_RATE_RAMP, t);
}

/**
 * Colour for an intervention-index value already normalized to [0, 1] by the
 * backend — no domain argument needed, unlike {@link numericColor}.
 */
export function interventionColor(value: number): RGB {
  return interpolateRamp(INTERVENTION_INDEX_RAMP, value);
}
