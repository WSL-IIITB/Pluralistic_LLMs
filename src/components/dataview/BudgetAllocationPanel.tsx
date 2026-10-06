/**
 * BudgetAllocationPanel — Data View's ₹ budget allocation panel.
 *
 * Reuses the shared `BucketPrioritySliders` control (bound to
 * `store.bucketPriorities`/`store.setBucketPriority`) rather than
 * reimplementing bucket-priority UI. Debounces calls to
 * `store.fetchBudgetAllocation` ~300ms after the budget figure or any
 * bucket priority changes — the store's fetch function is intentionally
 * undebounced ("Debouncing is the CALLER's job", per store.ts's own doc
 * comment on every interactive fetch action), so that's this panel's job.
 *
 * Active whenever a state OR a district is selected — budget is a
 * state-scoped concept (`POST /state/{state_code}/budget`, confirmed against
 * `backend/app/dataview/router.py`; there's no district-scoped budget
 * endpoint), so a district selection resolves to ITS state via
 * `store.districts[districtId].stateCode` rather than requiring the user to
 * separately select the state too. Otherwise (nothing selected, or a
 * district with no crosswalk match — see `hasData`-style handling in
 * `DataDistrictInfoPanel.tsx`) shows a disabled/hint state. The allocation
 * bar chart uses plain-CSS percentage-width bars, grouped and colored by
 * bucket using the app's existing `--chart-1..4` design tokens.
 *
 * Self-contained, no props — reads `selection` itself rather than taking a
 * state code as a prop, so it works unchanged whether `DataViewIntervention.tsx`
 * mounts it for a state or a district selection. Rendered only inside
 * `DataViewIntervention.tsx`'s own roomy layout now (never floating loose over the
 * map), so the root container below carries no fixed width or corner
 * positioning — it fills whatever space that layout gives it.
 */

import { useEffect, useRef, useState } from "react";

import { Input } from "@/components/ui/input";
import { useDataViewStore } from "@/lib/dataview/store";
import { BUCKET_IDS, type BucketId, type BudgetShare } from "@/lib/dataview/types";
import { BucketPrioritySliders } from "./BucketPrioritySliders";

const BUCKET_LABELS: Record<BucketId, string> = {
  infrastructure: "Infrastructure",
  digital_ict: "Digital and ICT",
  teacher_profile: "Teacher Profile",
  socio_economic: "Socio-Economic",
};

/** The 4 fixed bucket colors, reused for every bucket-colored element in
 * this panel — the app's existing `--chart-*` design tokens (styles.css),
 * not new hex values. */
const BUCKET_COLOR_VAR: Record<BucketId, string> = {
  infrastructure: "var(--chart-1)",
  digital_ict: "var(--chart-2)",
  teacher_profile: "var(--chart-3)",
  socio_economic: "var(--chart-4)",
};

const DEBOUNCE_MS = 300;
const DEFAULT_BUDGET = 10_000_000; // ₹1 crore — a reasonable starting figure, not a backend default.

function formatRupees(amount: number): string {
  return `₹${Math.round(amount).toLocaleString("en-IN")}`;
}

export function BudgetAllocationPanel() {
  const selection = useDataViewStore((s) => s.selection);
  const knownDistricts = useDataViewStore((s) => s.districts);
  const bucketPriorities = useDataViewStore((s) => s.bucketPriorities);
  const setBucketPriority = useDataViewStore((s) => s.setBucketPriority);
  const budgetResult = useDataViewStore((s) => s.budgetResult);
  const fetchBudgetAllocation = useDataViewStore((s) => s.fetchBudgetAllocation);

  const [totalBudget, setTotalBudget] = useState<number>(DEFAULT_BUDGET);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Budget is state-scoped — a district selection targets ITS state (see
  // this file's header comment), falling back to null only when there's no
  // selection at all, or a selected district isn't in the crosswalk (no
  // known `stateCode` for it).
  const stateCode =
    selection.kind === "state"
      ? selection.id
      : selection.kind === "district"
        ? (knownDistricts[selection.id]?.stateCode ?? null)
        : null;
  const isStateSelected = stateCode != null;

  useEffect(() => {
    if (!stateCode || !(totalBudget > 0)) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      void fetchBudgetAllocation(stateCode, totalBudget);
    }, DEBOUNCE_MS);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
    // fetchBudgetAllocation reads bucketPriorities itself (get() inside the
    // store), but a priority change still needs to trigger a recompute, so
    // bucketPriorities is a dependency here even though it isn't an argument.
  }, [stateCode, totalBudget, bucketPriorities, fetchBudgetAllocation]);

  const shares: BudgetShare[] =
    budgetResult && stateCode && budgetResult.stateCode === stateCode ? budgetResult.shares : [];
  const denom =
    budgetResult && budgetResult.totalBudget > 0 ? budgetResult.totalBudget : totalBudget;

  return (
    // `w-full` — no fixed pixel width or corner positioning here anymore;
    // `DataViewIntervention.tsx`'s own layout sizes and positions this panel (see
    // this file's header comment). No inner `max-h`/scroll region either —
    // `DataViewIntervention`'s single outer scroll container is now the only
    // scrolling region, rather than nesting an independent one per panel.
    <section
      className={`panel-surface pointer-events-auto flex w-full min-w-0 flex-col rounded-xl ${
        isStateSelected ? "" : "opacity-60"
      }`}
    >
      <div className="p-4 pb-0">
        <h2 className="text-xs font-medium tracking-wide text-foreground">Budget Allocation</h2>

        {!isStateSelected && (
          <p className="mt-2 text-[12px] text-muted-foreground/70">
            Select a state, or a district with data, on the map first.
          </p>
        )}

        <div className={isStateSelected ? "" : "pointer-events-none"}>
          <div className="mt-3">
            <p className="label-micro">Total budget (₹)</p>
            <Input
              type="number"
              min={0}
              step={100000}
              value={totalBudget}
              onChange={(e) => setTotalBudget(Number(e.target.value) || 0)}
              disabled={!isStateSelected}
              className="mt-1.5 h-9 text-[12px]"
              placeholder="e.g. 10000000"
            />
          </div>

          <div className="mt-4">
            <p className="label-micro">Bucket priority</p>
            <div className="mt-1.5">
              <BucketPrioritySliders priorities={bucketPriorities} onChange={setBucketPriority} />
            </div>
          </div>
        </div>
      </div>

      <div className={`p-4 pt-4 ${isStateSelected ? "" : "pointer-events-none"}`}>
        <div className="rounded-lg border border-panel-border bg-background/40 p-3">
          <p className="label-micro">Allocation by factor</p>
          {!isStateSelected ? (
            <p className="mt-2 text-[12px] text-muted-foreground/70">No state selected.</p>
          ) : shares.length === 0 ? (
            <p className="mt-2 text-[12px] text-muted-foreground/70">
              {totalBudget > 0 ? "Loading…" : "Enter a budget to see the allocation."}
            </p>
          ) : (
            <div className="mt-2 space-y-3">
              {BUCKET_IDS.map((bucket) => {
                const bucketShares = shares
                  .filter((s) => s.bucket === bucket)
                  .sort((a, b) => b.amount - a.amount);
                if (bucketShares.length === 0) return null;
                const subtotal = bucketShares.reduce((sum, s) => sum + s.amount, 0);
                return (
                  <div key={bucket}>
                    <div className="flex items-center gap-1.5">
                      <span
                        className="size-2 shrink-0 rounded-full"
                        style={{ backgroundColor: BUCKET_COLOR_VAR[bucket] }}
                        aria-hidden
                      />
                      <span className="text-[11px] font-medium text-foreground/90">
                        {BUCKET_LABELS[bucket]}
                      </span>
                      <span className="text-[10px] text-muted-foreground/60">
                        · {formatRupees(subtotal)}
                      </span>
                    </div>
                    <ul className="mt-1.5 space-y-1.5 pl-3.5">
                      {bucketShares.map((s) => (
                        <li key={s.factorName} className="flex items-center gap-2">
                          <span
                            className="w-24 shrink-0 truncate text-[11px] text-muted-foreground"
                            title={s.factorName}
                          >
                            {s.factorName}
                          </span>
                          <div className="h-2 flex-1 overflow-hidden rounded-full bg-white/5">
                            <div
                              className="h-full rounded-full"
                              style={{
                                width: `${denom > 0 ? Math.max(0, Math.min(100, (s.amount / denom) * 100)) : 0}%`,
                                backgroundColor: BUCKET_COLOR_VAR[bucket],
                              }}
                            />
                          </div>
                          <span className="w-20 shrink-0 text-right text-[10px] tabular-nums text-foreground">
                            {formatRupees(s.amount)}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                );
              })}
            </div>
          )}
          <p className="mt-3 text-[10px] leading-relaxed text-muted-foreground/50">
            A relative split of the entered budget by required change magnitude and bucket priority
            — not a genuinely costed estimate (no unit-cost data exists in the source).
          </p>
        </div>
      </div>
    </section>
  );
}
