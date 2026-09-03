/**
 * DataDistrictInfoPanel — Data View's district drill-down panel.
 *
 * Mirrors `DistrictInfoPanel.tsx`'s visual/structural chrome (header with
 * district name + close button, scrolling card-style body) but the content
 * is entirely numeric/quantitative, not LLM-viewpoint text:
 *  - District Profile: a stacked bar of per-factor sensitivity ratios
 *    (sums to ~100%), grouped/colored by bucket.
 *  - Prescriptive controls: a target-reduction % slider + the shared
 *    `BucketPrioritySliders`, driving a debounced recompute of the
 *    district's prescription (original vs. prescribed per factor).
 *  - A numeric Confidence Value badge (raw model r², not a tier string).
 *  - An Original vs. Prescribed table, grouped by bucket, hiding any
 *    bucket currently set to "nil" priority.
 *
 * Self-contained: takes no props, reads everything from `useDataViewStore`.
 * The District Profile response is fetched here and kept in local component
 * state (view-local, not worth putting in the global store — nothing else
 * needs it). Deliberately independent from `src/lib/worldview` — the only
 * cross-import is `useDistrictGeo`, purely for district/state display names,
 * which is safe because `lib/dataview/types.ts`'s `DistrictId` is documented
 * as using the exact same `${stateCode}-${districtCode}` convention as
 * worldview's, so the same GeoJSON index resolves either one's ids.
 *
 * Rendered only inside `DataViewIntervention.tsx`'s roomy layout now (never
 * floating loose over the map, and only ever mounted there when
 * `selection.kind === "district"`), so the root containers below carry no
 * fixed pixel width or corner positioning — they fill whatever space that
 * layout gives them, and `DataViewIntervention`'s own outer container is the sole
 * scroll region rather than each panel nesting an independent one.
 *
 * No recharts here: grepping this codebase's `src/` turned up recharts
 * imported only by the unused shadcn `components/ui/chart.tsx` wrapper — no
 * dashboard component actually renders a chart with it yet, so there's no
 * working example of its styling to copy. Per the plan, plain CSS/flexbox
 * bars are used instead, matching how `DistrictInfoPanel.tsx`'s own
 * "Viewpoint mix" list already renders proportions in this codebase.
 */

import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { X } from "lucide-react";

import { useDistrictGeo } from "@/components/dashboard/map/useDistrictGeo";
import { Slider } from "@/components/ui/slider";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { getDistrictProfile } from "@/lib/dataview/api";
import { useDataViewStore } from "@/lib/dataview/store";
import type { BucketId, DistrictProfile } from "@/lib/dataview/types";

import { BucketPrioritySliders } from "./BucketPrioritySliders";

/**
 * Four fixed, visually distinct bucket colors, LOCAL to this file — a
 * deliberately separate palette from `lib/worldview/palette.ts`'s
 * categorical cluster colors (never touch that one; see this file's header
 * note and `lib/dataview/palette.ts`'s own note about staying independent).
 */
const BUCKET_COLORS: Record<BucketId, string> = {
  infrastructure: "#38bdf8", // sky
  digital_ict: "#a78bfa", // violet
  teacher_profile: "#fb923c", // orange
  socio_economic: "#4ade80", // green
};

const BUCKET_LABELS: Record<BucketId, string> = {
  infrastructure: "Infrastructure",
  digital_ict: "Digital and ICT",
  teacher_profile: "Teacher Profile",
  socio_economic: "Socio-Economic",
};

const BUCKET_ORDER: readonly BucketId[] = [
  "infrastructure",
  "digital_ict",
  "teacher_profile",
  "socio_economic",
];

/** Debounce window for the prescriptive recompute — see the store's own
 * `fetchDistrictPrescription` docstring: "Debouncing is the CALLER's job". */
const PRESCRIPTION_DEBOUNCE_MS = 300;

function formatFactorValue(v: number): string {
  return Number.isFinite(v) ? v.toLocaleString("en-IN", { maximumFractionDigits: 2 }) : "—";
}

export function DataDistrictInfoPanel() {
  const selection = useDataViewStore((s) => s.selection);
  const targetReduction = useDataViewStore((s) => s.targetReduction);
  const bucketPriorities = useDataViewStore((s) => s.bucketPriorities);
  const districtPrescription = useDataViewStore((s) => s.districtPrescription);
  const knownDistricts = useDataViewStore((s) => s.districts);
  const setTargetReduction = useDataViewStore((s) => s.setTargetReduction);
  const setBucketPriority = useDataViewStore((s) => s.setBucketPriority);
  const fetchDistrictPrescription = useDataViewStore((s) => s.fetchDistrictPrescription);
  const clearSelection = useDataViewStore((s) => s.clearSelection);

  const { geo, status: geoStatus } = useDistrictGeo();

  const districtId = selection.kind === "district" ? selection.id : null;

  // `store.districts` is populated only from `district_scored` SSE events,
  // i.e. only the districts the backend's crosswalk actually resolved (see
  // the plan's "Explicit open risks" — ~12% of districts don't crosswalk and
  // render as "no data", never a silently wrong match). A click can still
  // land on an unresolved district's polygon (the base map/geojson has more
  // districts than the crosswalk covers), which would otherwise 404 against
  // every Data View endpoint and surface as a scary "Could not load..."
  // error. Treating "not in store.districts" as an honest no-data state
  // (skipping the doomed fetches entirely) instead of an error is more
  // truthful and avoids a pointless round-trip.
  const hasData = districtId != null && districtId in knownDistricts;

  // ── District Profile: view-local state, fetched on selection change ──────
  const [profile, setProfile] = useState<DistrictProfile | null>(null);
  const [profileLoading, setProfileLoading] = useState(false);
  const [profileError, setProfileError] = useState<string | null>(null);

  useEffect(() => {
    if (!districtId || !hasData) {
      setProfile(null);
      setProfileError(null);
      setProfileLoading(false);
      return;
    }
    let alive = true;
    setProfile(null);
    setProfileLoading(true);
    setProfileError(null);
    getDistrictProfile(districtId)
      .then((result) => {
        if (!alive) return;
        setProfile(result);
      })
      .catch((err: unknown) => {
        if (!alive) return;
        setProfileError(err instanceof Error ? err.message : "Could not load district profile.");
      })
      .finally(() => {
        if (alive) setProfileLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [districtId, hasData]);

  // ── Prescriptive recompute: debounced ~300ms so a slider drag doesn't ────
  // fire a request per pixel. `fetchDistrictPrescription` itself is a plain
  // undebounced fetch-and-set by design (see store.ts); debouncing is this
  // component's responsibility.
  const [prescriptionLoading, setPrescriptionLoading] = useState(false);
  const [prescriptionError, setPrescriptionError] = useState<string | null>(null);
  const requestIdRef = useRef(0);

  useEffect(() => {
    if (!districtId || !hasData) {
      setPrescriptionLoading(false);
      setPrescriptionError(null);
      return;
    }
    const requestId = ++requestIdRef.current;
    setPrescriptionLoading(true);
    setPrescriptionError(null);
    const timer = window.setTimeout(() => {
      fetchDistrictPrescription(districtId).then(() => {
        if (requestIdRef.current !== requestId) return; // superseded by a later change
        setPrescriptionLoading(false);
        const current = useDataViewStore.getState().districtPrescription;
        if (!current || current.districtId !== districtId) {
          setPrescriptionError("Could not load prescription.");
        }
      });
    }, PRESCRIPTION_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
    // `bucketPriorities` is a plain object recreated on every change (see
    // store.ts's `setBucketPriority`), so identity comparison is enough to
    // retrigger this effect on any single bucket's priority change.
  }, [districtId, hasData, targetReduction, bucketPriorities, fetchDistrictPrescription]);

  const sortedProfileFactors = useMemo(() => {
    if (!profile) return [];
    // Group by bucket (stable visual grouping in the stacked bar/legend),
    // descending sensitivity within each bucket.
    return [...profile.factors].sort((a, b) => {
      if (a.bucket !== b.bucket) {
        return BUCKET_ORDER.indexOf(a.bucket) - BUCKET_ORDER.indexOf(b.bucket);
      }
      return b.sensitivityPct - a.sensitivityPct;
    });
  }, [profile]);

  // Only trust the store's prescription if it actually matches the
  // currently-selected district — a fast reselect could otherwise briefly
  // show a stale district's numbers while the new fetch is in flight.
  const prescription =
    districtPrescription && districtPrescription.districtId === districtId
      ? districtPrescription
      : null;

  const groupedPrescriptionFactors = useMemo(() => {
    if (!prescription) return [];
    return BUCKET_ORDER.filter((bucket) => bucketPriorities[bucket] !== "nil")
      .map((bucket) => ({
        bucket,
        factors: prescription.factors.filter((f) => f.bucket === bucket),
      }))
      .filter((group) => group.factors.length > 0);
  }, [prescription, bucketPriorities]);

  if (selection.kind !== "district") {
    return (
      <section className="panel-surface pointer-events-auto w-full rounded-xl px-4 py-3">
        <p className="text-[12px] leading-relaxed text-muted-foreground/70">
          Select a district on the map to see its data profile and prescriptive model.
        </p>
      </section>
    );
  }

  const id = selection.id;
  const geoDistrict = geo?.districts[id];
  // `geo` is the same map/gazetteer that rendered the clickable polygon in
  // the first place, so it knows every district's real name regardless of
  // whether LKI's dataset (`hasData`) covers it — an unresolved district
  // should never fall back to a bare id. While geo itself is still loading
  // (should be rare — the map only becomes clickable once it's ready, but
  // this guards the brief window regardless), show a loading placeholder
  // rather than flashing the raw id or "undefined".
  const geoLoading = geoStatus !== "ready";
  const districtName = geoDistrict?.name ?? profile?.districtId ?? (geoLoading ? null : id);
  const stateName = geoDistrict?.stateName ?? profile?.stateCode ?? "";

  if (!hasData) {
    return (
      <section className="panel-surface pointer-events-auto flex w-full flex-col rounded-xl">
        <header className="flex items-start justify-between gap-2 border-b border-panel-border px-4 py-3">
          <div className="min-w-0">
            <p className="label-micro">District</p>
            <h2 className="text-sm leading-snug font-medium text-foreground">
              {districtName ?? <span className="text-muted-foreground/50">Loading…</span>}
            </h2>
            {stateName && <p className="text-[11px] text-muted-foreground/70">{stateName}</p>}
          </div>
          <button
            type="button"
            aria-label="Close"
            onClick={clearSelection}
            className="flex size-6 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:text-foreground"
          >
            <X className="size-4" />
          </button>
        </header>
        <p className="px-4 py-4 text-[12px] leading-relaxed text-muted-foreground/70">
          No Data View data for this district — it isn't in the LKI-SSM dropout dataset's district
          crosswalk (a small share of districts don't match, e.g. post-2016 reorganizations the
          source data predates). Try another district.
        </p>
      </section>
    );
  }

  return (
    <section className="panel-surface pointer-events-auto flex w-full min-w-0 flex-col rounded-xl">
      <header className="flex items-start justify-between gap-2 border-b border-panel-border px-4 py-3">
        <div className="min-w-0">
          <p className="label-micro">District</p>
          <h2 className="text-sm leading-snug font-medium text-foreground">{districtName}</h2>
          {stateName && <p className="text-[11px] text-muted-foreground/70">{stateName}</p>}
        </div>
        <button
          type="button"
          aria-label="Close"
          onClick={clearSelection}
          className="flex size-6 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:text-foreground"
        >
          <X className="size-4" />
        </button>
      </header>

      <div className="space-y-4 px-4 py-4">
        {/* ── District Profile ────────────────────────────────────────── */}
        <div>
          <p className="label-micro">District Profile · Factor Sensitivity</p>
          {profileLoading && <p className="mt-2 text-[12px] text-muted-foreground/70">Loading…</p>}
          {profileError && (
            <p className="mt-2 text-[12px] text-destructive">Could not load district profile.</p>
          )}
          {!profileLoading && !profileError && profile && (
            <>
              <div className="mt-2.5 flex h-4 w-full overflow-hidden rounded-full bg-background/40">
                {sortedProfileFactors.map((f, i) => (
                  <div
                    key={`${f.factorName}-${i}`}
                    style={{
                      width: `${Math.max(0, f.sensitivityPct)}%`,
                      backgroundColor: BUCKET_COLORS[f.bucket],
                    }}
                    title={`${f.factorName} · ${f.sensitivityPct.toFixed(1)}%`}
                    className="h-full first:rounded-l-full last:rounded-r-full"
                  />
                ))}
              </div>
              <ul className="mt-2.5 flex flex-wrap gap-x-3 gap-y-1">
                {BUCKET_ORDER.map((bucket) => (
                  <li key={bucket} className="flex items-center gap-1.5">
                    <span
                      className="size-2 shrink-0 rounded-[2px]"
                      style={{ backgroundColor: BUCKET_COLORS[bucket] }}
                      aria-hidden
                    />
                    <span className="text-[10px] text-muted-foreground">
                      {BUCKET_LABELS[bucket]}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}
          {!profileLoading && !profileError && !profile && (
            <p className="mt-2 text-[12px] text-muted-foreground/70">No profile data.</p>
          )}
        </div>

        {/* ── Prescriptive controls ───────────────────────────────────── */}
        <div>
          <p className="label-micro">Prescriptive Model</p>
          <div className="mt-2.5 flex items-center justify-between gap-2">
            <span className="text-[12px] text-muted-foreground">Target reduction</span>
            <span className="text-[12px] tabular-nums text-foreground">
              {Math.round(targetReduction * 100)}%
            </span>
          </div>
          <Slider
            className="mt-2"
            value={[Math.round(targetReduction * 100)]}
            min={0}
            max={100}
            step={1}
            onValueChange={(v) => {
              const pct = v[0];
              if (pct !== undefined) setTargetReduction(pct / 100);
            }}
            aria-label="Target reduction percentage"
          />

          <div className="mt-3.5">
            <BucketPrioritySliders priorities={bucketPriorities} onChange={setBucketPriority} />
          </div>

          <div className="mt-3 flex items-center gap-2">
            <span className="label-micro">Confidence</span>
            <span className="rounded-full border border-panel-border px-2 py-0.5 text-[10px] tabular-nums text-foreground">
              {prescription ? prescription.confidenceValue.toFixed(2) : "—"}
            </span>
            {prescriptionLoading && (
              <span className="text-[11px] text-muted-foreground/70">Recomputing…</span>
            )}
            {!prescriptionLoading && prescriptionError && (
              <span className="text-[11px] text-destructive">Could not load prescription.</span>
            )}
          </div>
        </div>

        {/* ── Original vs. Prescribed ─────────────────────────────────── */}
        <div>
          <p className="label-micro">Original vs. Prescribed</p>
          {!prescription && !prescriptionLoading && !prescriptionError && (
            <p className="mt-2 text-[12px] text-muted-foreground/70">
              Adjust the sliders above to compute a prescription.
            </p>
          )}
          {groupedPrescriptionFactors.length > 0 && (
            // `table-fixed` + explicit column widths (rather than
            // content-driven `auto` layout) so a long, unbroken factor
            // name (no spaces to break on, e.g.
            // "electricity_availability - Yes (%)") can't push the
            // Original/Prescribed number columns off the panel — the
            // Factor column instead wraps within its own fixed share of
            // the width (`whitespace-normal break-words` below). The
            // `overflow-x-auto` wrapper stays only as a safety net for
            // extreme cases; it shouldn't be needed in the normal case
            // now that wrapping keeps every column on-panel.
            <div className="mt-2.5 overflow-x-auto">
              <Table className="table-fixed">
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead className="h-7 w-[58%] px-2 text-[10px] tracking-wide uppercase">
                      Factor
                    </TableHead>
                    <TableHead className="h-7 w-[21%] px-2 text-right text-[10px] tracking-wide uppercase">
                      Original
                    </TableHead>
                    <TableHead className="h-7 w-[21%] px-2 text-right text-[10px] tracking-wide uppercase">
                      Prescribed
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {groupedPrescriptionFactors.map(({ bucket, factors }) => (
                    <Fragment key={bucket}>
                      <TableRow className="hover:bg-transparent">
                        <TableCell
                          colSpan={3}
                          className="px-2 py-1.5 text-[10px] font-semibold tracking-wide text-muted-foreground uppercase"
                        >
                          <span
                            className="mr-1.5 inline-block size-2 rounded-[2px] align-middle"
                            style={{ backgroundColor: BUCKET_COLORS[bucket] }}
                            aria-hidden
                          />
                          {BUCKET_LABELS[bucket]}
                        </TableCell>
                      </TableRow>
                      {factors.map((f) => (
                        <TableRow key={`${bucket}-${f.factorName}`}>
                          <TableCell className="px-2 py-1.5 align-top text-[12px] break-words whitespace-normal text-foreground">
                            {f.factorName}
                          </TableCell>
                          <TableCell className="px-2 py-1.5 text-right text-[12px] tabular-nums text-muted-foreground">
                            {formatFactorValue(f.original)}
                          </TableCell>
                          <TableCell className="px-2 py-1.5 text-right text-[12px] tabular-nums text-foreground">
                            {formatFactorValue(f.prescribed)}
                          </TableCell>
                        </TableRow>
                      ))}
                    </Fragment>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
          {prescription && groupedPrescriptionFactors.length === 0 && (
            <p className="mt-2 text-[12px] text-muted-foreground/70">
              All buckets are set to Nil priority — nothing to show.
            </p>
          )}
        </div>
      </div>
    </section>
  );
}
