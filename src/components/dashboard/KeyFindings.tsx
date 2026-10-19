/**
 * "Key findings" — the study's headline results in plain language, at the top of the home view.
 * Wording comes from keyFindings.ts; every number is computed from the data.
 */

import { ChevronDown } from "lucide-react";
import { useMemo, useState } from "react";

import { useDistrictProfiles, useExplorerStore, useWorldviewStore } from "@/lib/worldview";
import {
  summarisePersonaSimilarity,
  type ResearchAggregate,
  type ResearchMap,
} from "@/lib/worldview/aggregate";
import { buildKeyFindings, type KeyFinding } from "@/lib/worldview/keyFindings";

export function KeyFindings({
  agg,
  research,
  regionRates,
}: {
  agg: ResearchAggregate;
  research: ResearchMap;
  regionRates: Record<string, { avg: number | null; n: number }>;
}) {
  const [open, setOpen] = useState(true);
  const personaSimilarity = useWorldviewStore((s) => s.personaSimilarity);
  const { byId } = useDistrictProfiles();
  const focusRegion = useExplorerStore((s) => s.focusRegion);
  const focusDistrict = useExplorerStore((s) => s.focusDistrict);
  const setTab = useExplorerStore((s) => s.setTab);

  const findings = useMemo(
    () =>
      buildKeyFindings({
        agg,
        research,
        regionRates,
        persona: summarisePersonaSimilarity(personaSimilarity),
        byId,
      }),
    [agg, research, regionRates, personaSimilarity, byId],
  );

  const run = (a: NonNullable<KeyFinding["action"]>) => {
    if (a.kind === "region") focusRegion(a.regionId);
    else if (a.kind === "district") focusDistrict(a.districtId, a.regionId);
    else setTab(a.tab);
  };

  return (
    <section
      aria-labelledby="key-findings-title"
      className="rounded-2xl border border-primary/25 bg-gradient-to-br from-primary/10 to-transparent"
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
      >
        <span>
          <span className="label-micro block">Summary</span>
          <span
            id="key-findings-title"
            className="mt-0.5 block text-[15px] font-semibold text-foreground"
          >
            Key findings
          </span>
        </span>
        <ChevronDown
          className={`size-4 shrink-0 text-muted-foreground transition-transform ${open ? "" : "-rotate-90"}`}
          aria-hidden
        />
      </button>

      {open && (
        <ol className="space-y-3.5 border-t border-primary/15 px-4 py-4">
          {findings.map((f, i) => (
            <li key={f.id} className="flex gap-3">
              <span
                className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-primary/20 text-[11px] font-semibold text-primary"
                aria-hidden
              >
                {i + 1}
              </span>
              <p className="min-w-0 text-[12.5px] leading-relaxed text-foreground/85">
                <b className="font-semibold text-foreground">{f.lead}</b> {f.text}
                {f.action && (
                  <button
                    type="button"
                    onClick={() => run(f.action!)}
                    className="ml-1.5 text-[11.5px] font-medium text-primary underline-offset-2 hover:underline"
                  >
                    {f.action.label} →
                  </button>
                )}
              </p>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
