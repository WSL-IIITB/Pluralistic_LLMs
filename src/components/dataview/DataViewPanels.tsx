/**
 * DataViewPanels — Data View's top-level router, rendered by routes/index.tsx
 * when the "Data" tab is active.
 *
 * A calm, guided TWO-PAGE flow (mirroring the reference LKI/IIIT-Bangalore
 * dashboard): an all-India "Verdict" page (`DataViewVerdict.tsx` — map
 * color-mode + legend, per-state Major-factors table + cross-filter, and the
 * real LLM-generated verdict narrative for whatever's selected on the map)
 * and an "Intervention & Budget" drill-down page (`DataViewIntervention.tsx`
 * — prescriptive sliders, Original-vs-Prescribed table, budget allocation),
 * switched by an explicit forward/back control — never shown together, and
 * never auto-switched as a side effect of a map click (see `store.ts`'s
 * `DataViewActiveView` docstring for why that's `activeDataView`, a field
 * deliberately separate from `selection`).
 *
 * This file itself stays small: the always-visible bootstrap status card +
 * Verdict/Intervention & Budget toggle (top-left, the same slot the old
 * bootstrap status card already occupied), plus conditionally mounting
 * whichever page is active. Each page owns its own positioning/layout from
 * here down — see `DataViewVerdict.tsx`'s header comment for why.
 */

import { useDataViewBootstrap } from "@/lib/dataview/useDataViewBootstrap";
import { type DataViewActiveView, useDataViewStore } from "@/lib/dataview/store";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";

import { DataViewIntervention } from "./DataViewIntervention";
import { DataViewVerdict } from "./DataViewVerdict";

const VIEW_OPTIONS: readonly { value: DataViewActiveView; label: string }[] = [
  { value: "verdict", label: "Verdict" },
  { value: "intervention", label: "Intervention & Budget" },
];

export function DataViewPanels() {
  useDataViewBootstrap();

  const loadState = useDataViewStore((s) => s.loadState);
  const error = useDataViewStore((s) => s.error);
  const activeDataView = useDataViewStore((s) => s.activeDataView);
  const setActiveDataView = useDataViewStore((s) => s.setActiveDataView);

  return (
    <>
      {/* ── Top-left: bootstrap status (while loading/erroring) + the page toggle ── */}
      <div className="pointer-events-none absolute top-28 left-5 flex flex-col items-start gap-2">
        {loadState !== "ready" && (
          <div className="panel-surface pointer-events-auto w-[260px] rounded-xl px-4 py-3">
            <p className="label-micro">Data View</p>
            <p className="mt-2 text-[12px] text-muted-foreground">
              Status: <span className="text-foreground">{loadState}</span>
            </p>
            {loadState === "error" && (
              <p className="mt-1 text-[11px] text-destructive">
                {error ?? "The Data View stream failed."}
              </p>
            )}
          </div>
        )}

        <div className="panel-surface pointer-events-auto rounded-xl p-1.5">
          <ToggleGroup
            type="single"
            value={activeDataView}
            onValueChange={(v) => {
              if (v) setActiveDataView(v as DataViewActiveView);
            }}
            aria-label="Data View page"
            className="gap-1"
          >
            {VIEW_OPTIONS.map((opt) => (
              <ToggleGroupItem
                key={opt.value}
                value={opt.value}
                className="h-7 px-3 text-[11px] font-semibold tracking-wide uppercase"
              >
                {opt.label}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        </div>
      </div>

      {activeDataView === "verdict" ? <DataViewVerdict /> : <DataViewIntervention />}
    </>
  );
}
