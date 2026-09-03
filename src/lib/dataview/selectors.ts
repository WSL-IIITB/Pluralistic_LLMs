/**
 * Data View — pure selector helpers over `store.ts`'s `factorR2ByState`.
 *
 * Plain functions, not React hooks: callers (Overview's components) already
 * pull `factorR2ByState`/`factors` out of `useDataViewStore` via selector
 * hooks and pass them in here, wrapping the call in their own `useMemo`. Kept
 * in a separate file from `store.ts` rather than inline in a component so
 * both `DataViewVerdict` and any future caller can share the exact same
 * "top N factors" ranking logic without duplicating it.
 */

import type { BucketId, FactorDatum, FactorId } from "./types";
import type { StateCode } from "./types";

/** One factor's identity + fit quality, ranked within a single state. */
export interface TopFactorEntry {
  factorId: FactorId;
  label: string;
  bucket: BucketId;
  r2: number;
}

/**
 * The top-`n` active factors for one state, sorted by fit quality (r2)
 * descending. Mirrors the ranking that used to live inline in
 * `InterventionIndexPanel.tsx` — moved here so `statesSharingFactor` below
 * can reuse the exact same ranking for every OTHER state too, not just the
 * one currently selected.
 */
export function topFactorsForState(
  factorR2ByState: Record<StateCode, Record<FactorId, number>>,
  factors: Record<FactorId, FactorDatum>,
  stateCode: StateCode,
  n = 5,
): TopFactorEntry[] {
  const r2ByFactor = factorR2ByState[stateCode];
  if (!r2ByFactor) return [];
  return Object.entries(r2ByFactor)
    .map(([factorId, r2]) => {
      const factor = factors[factorId];
      return {
        factorId,
        label: factor?.label ?? factorId,
        bucket: factor?.bucket ?? "socio_economic",
        r2,
      };
    })
    .sort((a, b) => b.r2 - a.r2)
    .slice(0, n);
}

/**
 * Reverse lookup: which states have `factorId` among their OWN top-`n`
 * factors (recomputed per state via {@link topFactorsForState}) — the
 * "click a factor -> see which other states have it in their own top 5"
 * cross-filter confirmed live in the reference LKI/IIIT-B dashboard.
 *
 * Deliberately does NOT exclude the state the factor was clicked from — it
 * checks every state in `factorR2ByState` uniformly, including whichever one
 * originated the click, since `factorId` is a bare id with no notion of
 * "where it came from" once passed in here. A caller building an "Also a top
 * factor in: <other states>" list (i.e. `DataViewVerdict`) filters the
 * originating state's code out of the result itself. Keeping the exclusion a
 * caller concern (rather than baking a hidden implicit exclusion in here)
 * keeps this function's contract simple and reusable for any future caller
 * that doesn't have a single "originating" state to exclude.
 */
export function statesSharingFactor(
  factorR2ByState: Record<StateCode, Record<FactorId, number>>,
  factors: Record<FactorId, FactorDatum>,
  factorId: FactorId,
  n = 5,
): StateCode[] {
  const result: StateCode[] = [];
  for (const stateCode of Object.keys(factorR2ByState)) {
    const top = topFactorsForState(factorR2ByState, factors, stateCode, n);
    if (top.some((entry) => entry.factorId === factorId)) result.push(stateCode);
  }
  return result;
}
