/**
 * DataViewIntervention — Data View's "Intervention & Budget" drill-down page.
 *
 * The second of Data View's two guided pages (see `store.ts`'s
 * `DataViewActiveView` docstring). Reuses `DataDistrictInfoPanel` (the
 * bucket sliders + Original-vs-Prescribed table) and `BudgetAllocationPanel`
 * (the ₹ budget split) wholesale — all their fetch/debounce/geo-lookup logic
 * is untouched by this rename, only their own root containers were widened
 * to drop the narrow floating-panel chrome they used to need (see each
 * file's own header comment) now that they're only ever mounted here, inside
 * this page's own roomy layout, never floating loose over the map.
 *
 * Self-contained, no props — reads `selection`/`setActiveDataView` itself.
 * Owns its own absolute positioning (same convention as `DataViewVerdict`
 * and `HistoryPanel.tsx` — see `DataViewVerdict.tsx`'s header comment for
 * why a top-level "whole page" component positions itself rather than
 * waiting on a wrapper from `DataViewPanels.tsx`).
 *
 * The "← Back to Verdict" control only flips `activeDataView` — it never
 * touches `selection`, so the map's current selection is preserved across
 * the toggle in either direction (per the plan: view and selection are
 * deliberately independent).
 */

import { ArrowLeft } from "lucide-react";

import { useDistrictGeo } from "@/components/dashboard/map/useDistrictGeo";
import { useDataViewStore } from "@/lib/dataview/store";

import { BudgetAllocationPanel } from "./BudgetAllocationPanel";
import { DataDistrictInfoPanel } from "./DataDistrictInfoPanel";

export function DataViewIntervention() {
  const { geo } = useDistrictGeo();
  const selection = useDataViewStore((s) => s.selection);
  const setActiveDataView = useDataViewStore((s) => s.setActiveDataView);

  const selectionLabel = (() => {
    if (selection.kind === "state") {
      return geo?.states[selection.id]?.stateName ?? selection.id;
    }
    if (selection.kind === "district") {
      const d = geo?.districts[selection.id];
      return d ? `${d.name}${d.stateName ? ` · ${d.stateName}` : ""}` : selection.id;
    }
    return null;
  })();

  return (
    // Box edges, not a `top-28`-matching centered fixed width — this page is
    // wide enough to span under the ALWAYS-visible, horizontally-centered
    // `QueryBar` (routes/index.tsx, unconditional on every tab) and the
    // ALWAYS-visible bottom-6-anchored `ProgressBar`/"LIVE COLLECTION" bar in
    // its own bottom stack. Neither can be moved or resized from here (out
    // of scope; not touching routes/index.tsx), so this box's own edges
    // clear both instead: `top-[300px]` sits below QueryBar's own rendered
    // bottom (~263px at 1440x900, its own box, no error/no-results card
    // showing), and `bottom-28` sits above ProgressBar's top (~818px at the
    // same viewport) — with buffer either side rather than an exact
    // pixel match, since this page's own gaps between sections are
    // transparent and would otherwise let whatever's underneath peek
    // through messily. `left-[300px]` clears the status-card+toggle column
    // that always occupies top-28 left-5 (up to ~260px wide while the
    // bootstrap status card is showing).
    // pointer-events-none here, not -auto: this box's edges are sized to
    // clear QueryBar/ProgressBar (see above), which leaves real empty margin
    // beside the actual panel content on most viewports. Each child section
    // below already sets its own `pointer-events-auto` (panel-surface
    // convention, same as every other dataview panel) -- pointer-events:none
    // on the wrapper lets clicks in that empty margin fall through to the
    // map underneath instead of being silently swallowed, while the panels
    // themselves stay fully interactive.
    <div className="pointer-events-none absolute top-[300px] right-5 bottom-28 left-[300px] flex flex-col gap-3 overflow-y-auto [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-border [&::-webkit-scrollbar-track]:bg-transparent">
      <div className="panel-surface pointer-events-auto flex shrink-0 items-center justify-between gap-3 rounded-xl px-4 py-2.5">
        <button
          type="button"
          onClick={() => setActiveDataView("verdict")}
          className="flex items-center gap-1.5 text-[12px] font-medium text-muted-foreground transition-colors hover:text-foreground"
        >
          <ArrowLeft className="size-3.5" aria-hidden />
          Back to Verdict
        </button>
        {selectionLabel && (
          <p className="truncate text-[11px] text-muted-foreground/70">{selectionLabel}</p>
        )}
      </div>

      {selection.kind === null && (
        <section className="panel-surface shrink-0 rounded-xl px-4 py-3">
          <p className="text-[12px] leading-relaxed text-muted-foreground/70">
            Select a state or district on the map first.
          </p>
        </section>
      )}

      {selection.kind === "state" && (
        <>
          <p className="shrink-0 text-[11px] text-muted-foreground/70">
            Click a district on the map for its own prescriptive breakdown.
          </p>
          <div className="max-w-2xl shrink-0">
            <BudgetAllocationPanel />
          </div>
        </>
      )}

      {selection.kind === "district" && (
        <div className="flex flex-col items-start gap-3 md:flex-row">
          <div className="min-w-0 md:flex-[3]">
            <DataDistrictInfoPanel />
          </div>
          <div className="min-w-0 md:flex-[2]">
            <BudgetAllocationPanel />
          </div>
        </div>
      )}
    </div>
  );
}
