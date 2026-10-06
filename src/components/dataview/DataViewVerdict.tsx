/**
 * DataViewVerdict — Data View's all-India "Verdict" page.
 *
 * The first of Data View's two guided pages (see `store.ts`'s
 * `DataViewActiveView` docstring for why the page is a separate, explicit
 * toggle rather than something derived from `selection`). Mirrors the
 * reference LKI/IIIT-Bangalore dashboard's overview page: map color-mode
 * control + legend, a per-state "top 5 factors" table, and a factor-click
 * cross-filter showing which OTHER states share that factor in their own
 * top 5 -- plus, new here, the real LLM-generated "verdict" narrative for
 * whatever's currently selected on the map (no dropdown -- selecting a
 * state or district on the map is itself what drives this page, via
 * `store.selection`, same as the Major-factors table below it always has).
 *
 * The OLD "explore a specific factor across districts" dropdown tool (this
 * file used to fold in the old FactorSensitivityPanel's guts as a
 * collapsed secondary tool) has been REMOVED ENTIRELY -- not unmounted, not
 * collapsed-by-default, gone: its component, its store fields
 * (`fetchFactorSensitivity`/`factorSensitivity`/`factorSensitivityError`),
 * and its API wrapper (`getFactorSensitivity`) were all deleted (see
 * store.ts/api.ts/types.ts). The backend's `/factor/{id}/sensitivity`
 * endpoint itself is left in place (additive, harmless, not part of this
 * page's contract) but nothing in the frontend calls it any more.
 *
 * Self-contained, no props -- reads everything from `useDataViewStore` /
 * `useDistrictGeo`, same convention the panels this replaces used. Owns its
 * own absolute positioning (this file, not a wrapper in `DataViewPanels.tsx`,
 * is the top-level "one whole page" component -- same convention as
 * `HistoryPanel.tsx`, which positions its own root for the same reason: it's
 * the entire content of one tab/page, not one of several panels sharing a
 * host-provided slot).
 *
 * Which factor is "expanded" (showing its cross-filter) is plain local
 * component state (`useState<FactorId | null>`), not global store state --
 * view-local UI, matching how `DataDistrictInfoPanel` already keeps its own
 * local fetch state rather than pushing it into `useDataViewStore`.
 */

import { useEffect, useMemo, useState } from "react";

import { useDistrictGeo } from "@/components/dashboard/map/useDistrictGeo";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import {
  interventionColor,
  numericColor,
  type NumericDomain,
  type RGB,
} from "@/lib/dataview/palette";
import {
  statesSharingFactor,
  topFactorsForState,
  type TopFactorEntry,
} from "@/lib/dataview/selectors";
import { type DataViewColorMode, useDataViewStore } from "@/lib/dataview/store";
import type { BucketId, FactorId } from "@/lib/dataview/types";

const BUCKET_LABELS: Record<BucketId, string> = {
  infrastructure: "Infrastructure",
  digital_ict: "Digital and ICT",
  teacher_profile: "Teacher Profile",
  socio_economic: "Socio-Economic",
};

const COLOR_MODE_OPTIONS: readonly { value: DataViewColorMode; label: string }[] = [
  { value: "dropoutRate", label: "Dropout Rate" },
  { value: "interventionIndex", label: "Intervention Index" },
];

/** Sample points used to rebuild a CSS gradient from palette.ts's exported
 * color functions (5 stops — enough to read as a smooth ramp at this size). */
const GRADIENT_STOPS: readonly number[] = [0, 0.25, 0.5, 0.75, 1];

function rgbToCss([r, g, b]: RGB): string {
  return `rgb(${r}, ${g}, ${b})`;
}

/** How many of a state's top factors to list, and how many other states a
 * clicked factor's cross-filter shows. */
const TOP_FACTOR_COUNT = 5;

// ─────────────────────────────────────────────────────────────────────────
// Verdict narrative — the real LLM-backed section. A pure presentational
// sub-component (not its own store slice beyond what's already global):
// takes the resolved area kind/id/label as props so its parent doesn't
// duplicate the "district vs state, resolved vs not" branching twice.
// ─────────────────────────────────────────────────────────────────────────

interface VerdictSectionProps {
  /** null while nothing selected, or a district selection isn't in the
   * crosswalk (no Data View data for it — same as DataDistrictInfoPanel's
   * own `hasData` guard); in either case there's nothing to fetch. */
  target: { areaKind: "district" | "state"; id: string } | null;
  /** Shown only for the "district selected but not in the crosswalk" case,
   * so the message can name the actual district rather than being generic. */
  unresolvedDistrictLabel: string | null;
}

function VerdictSection({ target, unresolvedDistrictLabel }: VerdictSectionProps) {
  const verdict = useDataViewStore((s) => s.verdict);
  const verdictLoading = useDataViewStore((s) => s.verdictLoading);
  const verdictError = useDataViewStore((s) => s.verdictError);
  const fetchVerdict = useDataViewStore((s) => s.fetchVerdict);

  useEffect(() => {
    if (target) void fetchVerdict(target.areaKind, target.id);
    // `fetchVerdict` self-guards against an out-of-order resolve (see
    // store.ts) — this effect firing once per (areaKind, id) change is all
    // that's needed, no debounce (a map click is a discrete user action,
    // not a rapid-fire slider). `target` is memoized by the caller
    // (DataViewVerdict) to a stable reference per real (areaKind, id) pair,
    // so depending on the object itself here is safe and exhaustive-deps-clean.
  }, [target, fetchVerdict]);

  const isCurrent =
    verdict != null &&
    target != null &&
    verdict.areaKind === target.areaKind &&
    verdict.areaId === target.id;

  return (
    <section className="panel-surface shrink-0 rounded-xl p-4">
      <h2 className="text-xs font-medium tracking-wide text-foreground">Verdict</h2>
      <p className="mt-1 text-[10px] leading-relaxed text-muted-foreground/60">
        A generated narrative grounded in this area's own computed factors and prescriptive model —
        not a live database record, and it can take up to a minute for a real model call.
      </p>

      {/* `unresolvedDistrictLabel` is only ever set when `target` is ALSO
          null (a district selection outside the crosswalk has nothing to
          fetch — see DataViewVerdict's own `verdictTarget` computation) —
          so this branch MUST be checked before the bare `!target` case
          below, or the more specific "not in the dataset" message could
          never be reached (it would always lose to the generic "select
          something" placeholder). */}
      {unresolvedDistrictLabel ? (
        <p className="mt-2.5 text-[12px] leading-relaxed text-muted-foreground/70">
          No Data View data for {unresolvedDistrictLabel} — it isn&apos;t in the LKI-SSM dropout
          dataset&apos;s district crosswalk. Try another district, or select its state.
        </p>
      ) : !target ? (
        <p className="mt-2.5 text-[12px] leading-relaxed text-muted-foreground/70">
          Select a state or district on the map to generate its verdict.
        </p>
      ) : verdictLoading ? (
        <div className="mt-2.5 flex items-center gap-2">
          <span
            className="size-3.5 shrink-0 animate-spin rounded-full border-2 border-muted-foreground/25 border-t-foreground"
            aria-hidden
          />
          <p className="text-[12px] text-muted-foreground/70">
            Generating verdict… a real model call, this can take up to a minute.
          </p>
        </div>
      ) : isCurrent && verdict ? (
        <>
          <p className="mt-2 text-[11px] text-muted-foreground/70">
            {verdict.areaKind === "district"
              ? `${verdict.areaName} · ${verdict.stateName}`
              : verdict.areaName}
          </p>
          <div className="mt-2.5 space-y-2.5">
            {verdict.verdict
              .split(/\n{2,}/)
              .map((p) => p.trim())
              .filter(Boolean)
              .map((paragraph, i) => (
                <p key={i} className="text-[12px] leading-relaxed text-foreground/90">
                  {paragraph}
                </p>
              ))}
          </div>
        </>
      ) : verdictError ? (
        <p className="mt-2.5 text-[12px] text-destructive">{verdictError}</p>
      ) : (
        <p className="mt-2.5 text-[12px] text-muted-foreground/70">Loading…</p>
      )}
    </section>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// DataViewVerdict
// ─────────────────────────────────────────────────────────────────────────

export function DataViewVerdict() {
  const { geo } = useDistrictGeo();
  const colorMode = useDataViewStore((s) => s.colorMode);
  const setColorMode = useDataViewStore((s) => s.setColorMode);
  const selection = useDataViewStore((s) => s.selection);
  const stateScores = useDataViewStore((s) => s.stateScores);
  const factors = useDataViewStore((s) => s.factors);
  const factorR2ByState = useDataViewStore((s) => s.factorR2ByState);
  const knownDistricts = useDataViewStore((s) => s.districts);

  const [expandedFactorId, setExpandedFactorId] = useState<FactorId | null>(null);

  // Dropout rate isn't pre-normalized (unlike intervention index, which the
  // backend already scales to [0, 1] — see palette.ts's docstring), so the
  // legend stretches across the observed min/max of loaded state averages.
  const dropoutDomain = useMemo<NumericDomain>(() => {
    const values = Object.values(stateScores).map((s) => s.avgOutcome);
    if (values.length === 0) return [0, 1];
    return [Math.min(...values), Math.max(...values)];
  }, [stateScores]);

  const gradientCss = useMemo(() => {
    const colors: RGB[] =
      colorMode === "dropoutRate"
        ? GRADIENT_STOPS.map((t) =>
            numericColor(
              dropoutDomain[0] + t * (dropoutDomain[1] - dropoutDomain[0]),
              dropoutDomain,
            ),
          )
        : GRADIENT_STOPS.map((t) => interventionColor(t));
    return `linear-gradient(to right, ${colors.map(rgbToCss).join(", ")})`;
  }, [colorMode, dropoutDomain]);

  // A district selection (made in Intervention & Budget, e.g. by clicking a
  // district on the map there) still resolves to a state here — this page
  // is state-granular for its Major-factors table (see the file header),
  // but showing nothing for it would make the toggle look like it reset the
  // map's selection, when `selection` itself is untouched by the view
  // toggle (see DataViewPanels.tsx). Falling back to the district's parent
  // state keeps this page's "selection isn't reset by the toggle" contract
  // visible, not just true in the store.
  const selectedDistrict = selection.kind === "district" ? geo?.districts[selection.id] : undefined;
  const selectedStateCode =
    selection.kind === "state" ? selection.id : (selectedDistrict?.stateCode ?? null);
  const selectedState = selectedStateCode ? stateScores[selectedStateCode] : undefined;
  const selectedStateName = selectedStateCode
    ? (geo?.states[selectedStateCode]?.stateName ?? selectedStateCode)
    : null;

  // A newly-selected state's cross-filter shouldn't carry over a previously
  // expanded factor that may not even be in the new state's top 5.
  useEffect(() => {
    setExpandedFactorId(null);
  }, [selectedStateCode]);

  const topFactors = useMemo<TopFactorEntry[]>(() => {
    if (!selectedStateCode) return [];
    return topFactorsForState(factorR2ByState, factors, selectedStateCode, TOP_FACTOR_COUNT);
  }, [selectedStateCode, factorR2ByState, factors]);

  // "Also a top factor in:" — every OTHER state (the originating state is
  // filtered out here; see selectors.ts's docstring on why that's this
  // caller's job, not statesSharingFactor's).
  const sharingStates = useMemo(() => {
    if (!expandedFactorId) return [];
    return statesSharingFactor(factorR2ByState, factors, expandedFactorId, TOP_FACTOR_COUNT).filter(
      (code) => code !== selectedStateCode,
    );
  }, [expandedFactorId, factorR2ByState, factors, selectedStateCode]);

  const expandedFactorLabel = expandedFactorId
    ? (factors[expandedFactorId]?.label ?? expandedFactorId)
    : null;

  // Verdict is per EXACT selection (a district's own verdict genuinely
  // differs from its parent state's — see verdict.py's context builders),
  // unlike the Major-factors table above (which deliberately falls back to
  // the parent state for a district selection): fetch the district endpoint
  // directly whenever a district — not just its state — is selected.
  const districtHasData = selection.kind === "district" && selection.id in knownDistricts;
  // Memoized so its IDENTITY only changes when the resolved (areaKind, id)
  // pair actually changes — VerdictSection's effect depends on this object
  // directly, and a plain inline literal here would be a fresh reference on
  // every render (this component re-renders on every store tick, e.g. every
  // streamed factor/district/state during bootstrap), which would otherwise
  // re-fire the verdict fetch constantly instead of once per real selection
  // change.
  const verdictTarget = useMemo<VerdictSectionProps["target"]>(
    () =>
      selection.kind === "district" && districtHasData
        ? { areaKind: "district", id: selection.id }
        : selection.kind === "state"
          ? { areaKind: "state", id: selection.id }
          : null,
    [selection.kind, selection.id, districtHasData],
  );
  const unresolvedDistrictLabel =
    selection.kind === "district" && !districtHasData
      ? (selectedDistrict?.name ?? selection.id)
      : null;

  return (
    <div className="pointer-events-auto absolute top-28 right-5 bottom-6 flex w-[400px] max-w-[calc(100vw-3rem)] flex-col gap-3 overflow-y-auto [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-border [&::-webkit-scrollbar-track]:bg-transparent">
      {/* ── Map coloring + legend ─────────────────────────────────────────── */}
      <section className="panel-surface shrink-0 rounded-xl p-4">
        <h2 className="text-xs font-medium tracking-wide text-foreground">Intervention Index</h2>

        <div className="mt-3">
          <p className="label-micro">Map coloring</p>
          <ToggleGroup
            type="single"
            value={colorMode}
            onValueChange={(v) => {
              if (v) setColorMode(v as DataViewColorMode);
            }}
            aria-label="Choropleth color mode"
            className="mt-1.5 justify-start gap-1"
          >
            {COLOR_MODE_OPTIONS.map((opt) => (
              <ToggleGroupItem
                key={opt.value}
                value={opt.value}
                className="h-7 px-2.5 text-[11px] font-semibold tracking-wide uppercase"
              >
                {opt.label}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        </div>

        <div className="mt-3 rounded-lg border border-panel-border bg-background/40 p-3">
          <p className="label-micro">
            {colorMode === "dropoutRate" ? "Dropout rate scale" : "Intervention index scale"}
          </p>
          <div
            className="mt-2 h-2.5 w-full rounded-full"
            style={{ backgroundImage: gradientCss }}
          />
          <div className="mt-1 flex justify-between text-[10px] text-muted-foreground/70">
            {colorMode === "dropoutRate" ? (
              <>
                <span>{dropoutDomain[0].toFixed(1)}</span>
                <span>{dropoutDomain[1].toFixed(1)}</span>
              </>
            ) : (
              <>
                <span>0 (low)</span>
                <span>1 (high)</span>
              </>
            )}
          </div>
        </div>
      </section>

      {/* ── Selected state: summary + top 5 factors + cross-filter ─────────── */}
      <section className="panel-surface shrink-0 rounded-xl p-4">
        {selectedStateCode ? (
          <>
            <p className="label-micro">{selectedStateName}</p>
            {selectedDistrict && (
              <p className="mt-0.5 text-[11px] text-muted-foreground/70">
                District selected: <span className="text-foreground">{selectedDistrict.name}</span>{" "}
                — see Intervention &amp; Budget for its own breakdown.
              </p>
            )}
            {selectedState ? (
              <ul className="mt-1.5 space-y-1 text-[11px] text-muted-foreground">
                <li>
                  Avg. dropout rate:{" "}
                  <span className="text-foreground">{selectedState.avgOutcome.toFixed(2)}</span>
                </li>
                <li>
                  Confidence value:{" "}
                  <span className="text-foreground">
                    {selectedState.confidenceValue.toFixed(2)}
                  </span>
                </li>
                <li>
                  Intervention index:{" "}
                  <span className="text-foreground">
                    {selectedState.interventionIndex.toFixed(2)}
                  </span>
                </li>
              </ul>
            ) : (
              <p className="mt-1.5 text-[11px] text-muted-foreground/70">
                No model summary loaded yet for this state.
              </p>
            )}

            <p className="label-micro mt-3.5">Major factors</p>
            {topFactors.length > 0 ? (
              <div className="mt-1.5 overflow-hidden rounded-lg border border-panel-border">
                <Table>
                  <TableHeader>
                    <TableRow className="hover:bg-transparent">
                      <TableHead className="h-7 px-2 text-[10px] tracking-wide uppercase">
                        Factor
                      </TableHead>
                      <TableHead className="h-7 px-2 text-[10px] tracking-wide uppercase">
                        Bucket
                      </TableHead>
                      <TableHead className="h-7 px-2 text-right text-[10px] tracking-wide uppercase">
                        r2
                      </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {topFactors.map((f) => {
                      const isExpanded = f.factorId === expandedFactorId;
                      return (
                        <TableRow
                          key={f.factorId}
                          onClick={() => setExpandedFactorId(isExpanded ? null : f.factorId)}
                          aria-selected={isExpanded}
                          className={`cursor-pointer ${isExpanded ? "bg-muted/60" : ""}`}
                        >
                          <TableCell
                            className="max-w-0 truncate px-2 py-1.5 text-[12px] text-foreground"
                            title={f.label}
                          >
                            {f.label}
                          </TableCell>
                          <TableCell className="px-2 py-1.5 text-[11px] text-muted-foreground">
                            {BUCKET_LABELS[f.bucket]}
                          </TableCell>
                          <TableCell className="px-2 py-1.5 text-right text-[12px] tabular-nums text-foreground">
                            {f.r2.toFixed(2)}
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </div>
            ) : (
              <p className="mt-1.5 text-[11px] text-muted-foreground/70">
                No active factors loaded yet for this state.
              </p>
            )}
            <p className="mt-2 text-[10px] leading-relaxed text-muted-foreground/60">
              Click a row to see which other states also have that factor in their own top 5.
            </p>

            {expandedFactorId && (
              <div className="mt-3 border-t border-panel-border pt-3">
                <p className="label-micro">Also a top factor in:</p>
                {sharingStates.length > 0 ? (
                  <ul className="mt-1.5 space-y-1 text-[12px] text-foreground">
                    {sharingStates.map((code) => (
                      <li key={code}>{geo?.states[code]?.stateName ?? code}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-1.5 text-[11px] text-muted-foreground/70">
                    No other states have &ldquo;{expandedFactorLabel}&rdquo; in their own top 5.
                  </p>
                )}
              </div>
            )}
          </>
        ) : (
          <p className="text-[12px] leading-relaxed text-muted-foreground/70">
            Select a state on the map to see its top factors.
          </p>
        )}
      </section>

      {/* ── Verdict narrative (real LLM call) ───────────────────────────────── */}
      <VerdictSection target={verdictTarget} unresolvedDistrictLabel={unresolvedDistrictLabel} />
    </div>
  );
}
