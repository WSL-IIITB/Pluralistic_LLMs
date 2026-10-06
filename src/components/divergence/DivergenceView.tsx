/**
 * Story Mode vs. UIDAI/NITI official data.
 *
 * Story Mode's answer comes from social media, web research and each
 * region's persona -- narrative, regional, plural. UIDAI/NITI's dominant-
 * factor data comes from a district-level statistical model -- one number,
 * no persona, no regional voice. This view shows the two side by side for
 * each region and for the whole state, plus one consolidated answer per area
 * that actually draws on both.
 */

import { ChevronDown } from "lucide-react";
import { useState } from "react";

import {
  KARNATAKA_REGIONS,
  regionColor,
  STATEWIDE_REGION_ID,
  useWorldviewStore,
  type NitiFactor,
  type RegionId,
  type StoryVsOfficial,
  rgbaCss,
} from "@/lib/worldview";

function AreaSummary({
  row,
  accentColor,
  defaultOpen = false,
}: {
  row: StoryVsOfficial;
  accentColor?: string;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const hasStory = row.storyPoints.length > 0;
  const hasOfficial = row.officialFactors.length > 0;

  return (
    <div className="rounded-lg border border-panel-border px-3.5 py-3">
      <div className="flex items-center gap-2">
        {accentColor && (
          <span className="size-2.5 shrink-0 rounded-[3px]" style={{ backgroundColor: accentColor }} aria-hidden />
        )}
        <span className="text-[12.5px] font-medium text-foreground">{row.regionName}</span>
        <span className="text-[10.5px] text-muted-foreground">
          {hasStory ? `${row.storyPoints.length} persona repl${row.storyPoints.length === 1 ? "y" : "ies"}` : "no persona reply"}
          {" · "}
          {hasOfficial ? `${row.officialFactors.length} UIDAI/NITI row${row.officialFactors.length === 1 ? "" : "s"}` : "no UIDAI/NITI match"}
        </span>
      </div>

      {row.status === "failed" ? (
        <p className="mt-2 text-[12px] leading-snug text-muted-foreground">
          Couldn't be compared this run{row.error ? `: ${row.error}` : "."}
        </p>
      ) : (
        <>
          {row.consolidatedAnswer && (
            <p className="mt-2 text-[12.5px] leading-relaxed text-foreground/90">{row.consolidatedAnswer}</p>
          )}
          {row.comparison && (
            <p className="mt-2 text-[12px] leading-relaxed text-muted-foreground">{row.comparison}</p>
          )}

          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            className="label-micro mt-2.5 flex items-center gap-1.5 transition-colors hover:text-foreground"
          >
            <ChevronDown className={"size-3 transition-transform " + (open ? "" : "-rotate-90")} aria-hidden />
            Underlying evidence
          </button>

          {open && (
            <div className="mt-2 grid gap-3 lg:grid-cols-2">
              <div>
                <p className="label-micro">Story Mode — {row.storyPoints.length}</p>
                {hasStory ? (
                  <ul className="mt-1.5 space-y-2">
                    {row.storyPoints.map((p, i) => (
                      <li key={i} className="text-[12px] leading-snug text-muted-foreground">
                        {p}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-1.5 text-[12px] text-muted-foreground/60">
                    No persona reply for this area this run.
                  </p>
                )}
              </div>
              <div>
                <p className="label-micro">UIDAI/NITI dominant factors — {row.officialFactors.length}</p>
                {hasOfficial ? (
                  <FactorTable factors={row.officialFactors} />
                ) : (
                  <p className="mt-1.5 text-[12px] text-muted-foreground/60">
                    No UIDAI/NITI row matched this area's districts.
                  </p>
                )}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function FactorTable({ factors }: { factors: NitiFactor[] }) {
  return (
    <div className="mt-1.5 max-h-[220px] overflow-y-auto [&::-webkit-scrollbar]:w-1 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-border">
      <table className="w-full border-collapse text-[11px]">
        <thead>
          <tr className="text-left text-muted-foreground">
            <th className="py-1 pr-2 font-normal">District</th>
            <th className="py-1 pr-2 font-normal">Factor</th>
            <th className="py-1 pr-2 font-normal">Value</th>
          </tr>
        </thead>
        <tbody>
          {factors.map((f, i) => (
            <tr key={i} className="border-t border-panel-border align-top" title={f.method}>
              <td className="py-1 pr-2 whitespace-nowrap text-foreground/85">{f.district}</td>
              <td className="py-1 pr-2 text-foreground/85">{f.factor}</td>
              <td className="py-1 pr-2 tabular-nums text-foreground/85">{f.value}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-1 text-[10px] leading-snug text-muted-foreground/60">
        Two different methods appear (hover a row for which); their values are never comparable to
        each other.
      </p>
    </div>
  );
}

export function DivergenceView() {
  const storyVsOfficial = useWorldviewStore((s) => s.storyVsOfficial);
  const runState = useWorldviewStore((s) => s.runState);
  const query = useWorldviewStore((s) => s.query);
  const isStreaming = runState === "streaming" || runState === "connecting";

  const stateRow = storyVsOfficial[STATEWIDE_REGION_ID];
  const regionRows = KARNATAKA_REGIONS.map((r) => storyVsOfficial[r.id])
    .filter((r): r is StoryVsOfficial => !!r);
  const hasAny = !!stateRow || regionRows.length > 0;

  return (
    <div className="flex min-h-0 flex-1">
      <section className="panel-surface pointer-events-auto flex w-full flex-col overflow-hidden rounded-xl">
        <header className="border-b border-panel-border px-5 py-3.5">
          <h2 className="text-sm font-medium text-foreground">Story Mode vs. UIDAI/NITI data</h2>
          <p className="mt-1 max-w-[900px] text-[12px] leading-relaxed text-muted-foreground">
            Story Mode's answer for {query ? <>“{query}”</> : "this query"} — regional, persona-driven,
            grounded in social and web evidence — compared against UIDAI/NITI's official
            district-level dominant-factor model, which has no region or persona of its own. Each
            area below gets one consolidated answer drawing on both, plus the comparison and the raw
            evidence behind it.
          </p>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4 [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-border">
          {!hasAny ? (
            <p className="py-10 text-center text-[13px] text-muted-foreground/70">
              {isStreaming
                ? "Story Mode and UIDAI/NITI data are compared at the end of a run, once every region's persona reply is written…"
                : "Run a query to compare Story Mode's answer with UIDAI/NITI's official data, region by region and statewide."}
            </p>
          ) : (
            <div className="space-y-3">
              {stateRow && (
                <div>
                  <p className="label-micro mb-1.5">Whole state</p>
                  <AreaSummary row={stateRow} defaultOpen={false} />
                </div>
              )}
              {regionRows.length > 0 && (
                <div>
                  <p className="label-micro mb-1.5 mt-3">By region</p>
                  <div className="space-y-2.5">
                    {regionRows.map((row) => (
                      <AreaSummary
                        key={row.regionId}
                        row={row}
                        accentColor={rgbaCss(regionColor(row.regionId as RegionId))}
                      />
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
