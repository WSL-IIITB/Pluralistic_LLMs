/**
 * The Data tab's product argument: compare every region-aware answer to the
 * same Karnataka-wide overview. The primary signal is regional coverage, not
 * the small within-region male/female difference.
 */

import { ChevronDown } from "lucide-react";
import { useState } from "react";

import {
  KARNATAKA_REGIONS,
  rgbaCss,
  regionColor,
  type PersonaSimilarityRegion,
  useWorldviewStore,
} from "@/lib/worldview";

function average(values: Array<number | undefined>): number | null {
  const present = values.filter((value): value is number => value !== undefined);
  return present.length ? present.reduce((sum, value) => sum + value, 0) / present.length : null;
}

function percent(value: number | null): string {
  return value === null ? "—" : `${Math.round(value * 100)}%`;
}

function scoreWidth(value: number | undefined): string {
  return `${Math.max(0, Math.min(100, (value ?? 0) * 100))}%`;
}

function RegionalCoverageChart({ rows }: { rows: PersonaSimilarityRegion[] }) {
  return (
    <section className="border-y border-panel-border py-4" aria-labelledby="regional-coverage-title">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p id="regional-coverage-title" className="text-[13px] font-medium text-foreground">
            Regional coverage at a glance
          </p>
          <p className="mt-1 max-w-[760px] text-[11px] leading-relaxed text-muted-foreground">
            Longer bars mean the Karnataka-wide answer covers more of that region&apos;s perspective. The lowest rows are the clearest evidence of what a single generic answer leaves out.
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-3 text-[11px] text-muted-foreground" aria-label="Chart legend">
          <span className="flex items-center gap-1.5">
            <span className="size-2 rounded-full bg-primary" aria-hidden />
            Male
          </span>
          <span className="flex items-center gap-1.5">
            <span className="size-2 rounded-full bg-muted-foreground/50" aria-hidden />
            Female
          </span>
        </div>
      </div>

      <div className="mt-4 space-y-3" role="img" aria-label="Ranked regional male and female similarity scores">
        {rows.map((row) => {
          const match = average([row.maleSimilarity, row.femaleSimilarity]);
          return (
            <div key={row.regionId} className="grid grid-cols-[112px_minmax(0,1fr)_42px] items-center gap-x-3 gap-y-1.5">
              <span className="truncate text-[11px] text-foreground" title={row.regionName}>
                {row.regionName}
              </span>
              <div className="space-y-1" aria-label={`${row.regionName}: male ${percent(row.maleSimilarity ?? null)}, female ${percent(row.femaleSimilarity ?? null)}`}>
                <div className="h-2 overflow-hidden rounded-sm bg-secondary" title={`Male: ${percent(row.maleSimilarity ?? null)}`}>
                  <div className="h-full bg-primary transition-[width]" style={{ width: scoreWidth(row.maleSimilarity) }} />
                </div>
                <div className="h-2 overflow-hidden rounded-sm bg-secondary" title={`Female: ${percent(row.femaleSimilarity ?? null)}`}>
                  <div className="h-full bg-muted-foreground/50 transition-[width]" style={{ width: scoreWidth(row.femaleSimilarity) }} />
                </div>
              </div>
              <span className="text-right text-[11px] tabular-nums text-muted-foreground" title="Average male/female match">
                {percent(match)}
              </span>
            </div>
          );
        })}
      </div>

      <div className="mt-3 grid grid-cols-[112px_minmax(0,1fr)_42px] items-center gap-x-3 text-[10px] text-muted-foreground/70">
        <span />
        <div className="flex justify-between tabular-nums" aria-hidden>
          <span>0%</span>
          <span>50%</span>
          <span>100%</span>
        </div>
        <span className="text-right">avg</span>
      </div>
    </section>
  );
}

function ScoreTile({ row }: { row: PersonaSimilarityRegion }) {
  const [open, setOpen] = useState(false);
  const match = average([row.maleSimilarity, row.femaleSimilarity]);
  const genderGap =
    row.maleSimilarity !== undefined && row.femaleSimilarity !== undefined
      ? Math.abs(row.maleSimilarity - row.femaleSimilarity)
      : null;

  return (
    <div className="rounded-lg border border-panel-border px-3.5 py-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span
            className="size-2.5 shrink-0 rounded-[3px]"
            style={{ backgroundColor: rgbaCss(regionColor(row.regionId)) }}
            aria-hidden
          />
          <span className="text-[12px] font-medium text-foreground">{row.regionName}</span>
        </div>
        <span className="text-[11px] text-muted-foreground">Generic-answer match</span>
      </div>
      {row.status === "failed" ? (
        <p className="mt-2 text-[12px] leading-snug text-muted-foreground">
          Couldn&apos;t be measured this run{row.error ? `: ${row.error}` : "."}
        </p>
      ) : (
        <>
          <div className="mt-3 flex items-end gap-3">
            <p className="text-[26px] leading-none font-semibold text-foreground">{percent(match)}</p>
            <p className="pb-0.5 text-[11px] text-muted-foreground">
              {match === null ? "No reply available" : `${Math.round((1 - match) * 100)} pp not represented`}
            </p>
          </div>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-secondary">
            <div
              className="h-full rounded-full"
              style={{ width: `${Math.max(0, Math.min(100, (match ?? 0) * 100))}%`, backgroundColor: rgbaCss(regionColor(row.regionId)) }}
            />
          </div>
          <p className="mt-2 text-[11px] leading-snug text-foreground/80">
            {genderGap === null
              ? "Only one regional reply was available."
              : `Male/female difference: ${Math.round(genderGap * 100)} percentage points — secondary to the regional comparison.`}
          </p>

          {(row.baselineReply || row.maleReply || row.femaleReply) && (
            <>
              <button
                type="button"
                onClick={() => setOpen((value) => !value)}
                aria-expanded={open}
                className="label-micro mt-2.5 flex items-center gap-1.5 transition-colors hover:text-foreground"
              >
                <ChevronDown className={`size-3 transition-transform ${open ? "" : "-rotate-90"}`} aria-hidden />
                Compare replies
              </button>
              {open && (
                <div className="mt-2 space-y-2">
                  {row.baselineReply && <Reply label="Karnataka-wide generic answer" text={row.baselineReply} />}
                  {row.maleReply && <Reply label="Regional male persona" text={row.maleReply} />}
                  {row.femaleReply && <Reply label="Regional female persona" text={row.femaleReply} />}
                </div>
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}

function Reply({ label, text }: { label: string; text: string }) {
  return (
    <div>
      <p className="label-micro">{label}</p>
      <p className="mt-1 text-[12px] leading-relaxed text-muted-foreground">{text}</p>
    </div>
  );
}

export function KarnatakaPersonaSimilarity() {
  const personaSimilarity = useWorldviewStore((state) => state.personaSimilarity);
  const runState = useWorldviewStore((state) => state.runState);
  const query = useWorldviewStore((state) => state.query);
  const isStreaming = runState === "streaming" || runState === "connecting";
  const rows = KARNATAKA_REGIONS.map((region) => personaSimilarity[region.id]).filter(
    (row): row is PersonaSimilarityRegion => !!row && row.status === "ok",
  );
  const orderedRows = [...rows].sort(
    (a, b) => (average([a.maleSimilarity, a.femaleSimilarity]) ?? 1) - (average([b.maleSimilarity, b.femaleSimilarity]) ?? 1),
  );
  const matches = rows.map((row) => average([row.maleSimilarity, row.femaleSimilarity])).filter((value): value is number => value !== null);
  const genderGaps = rows
    .map((row) => (row.maleSimilarity !== undefined && row.femaleSimilarity !== undefined ? Math.abs(row.maleSimilarity - row.femaleSimilarity) : null))
    .filter((value): value is number => value !== null);
  const averageMatch = average(matches);
  const regionalSpread = matches.length ? Math.max(...matches) - Math.min(...matches) : null;
  const averageGenderGap = average(genderGaps);

  return (
    <div className="flex min-h-0 flex-1">
      <section className="panel-surface pointer-events-auto flex w-full flex-col overflow-hidden rounded-xl">
        <header className="border-b border-panel-border px-5 py-3.5">
          <p className="label-micro">Plural AI evidence</p>
          <h2 className="mt-1 text-sm font-medium text-foreground">A single Karnataka answer does not represent every region equally</h2>
          <p className="mt-1 max-w-[900px] text-[12px] leading-relaxed text-muted-foreground">
            We compare each region-aware answer to the same Karnataka-wide answer for {query ? <>“{query}”</> : "this query"}. Lower match means the generic answer leaves more of that region&apos;s perspective out.
          </p>
          {averageMatch !== null && regionalSpread !== null && averageGenderGap !== null && (
            <p className="mt-2 text-[12.5px] font-medium text-foreground">
              The generic answer matches regional answers by {percent(averageMatch)} on average, with a {Math.round(regionalSpread * 100)}-point gap between regions. Gender differs by only {Math.round(averageGenderGap * 100)} points on average — this run supports a region-first, not gender-first, approach.
            </p>
          )}
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4 [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-border">
          {rows.length === 0 ? (
            <p className="py-10 text-center text-[13px] text-muted-foreground/70">
              {isStreaming
                ? "Comparing each regional answer with the Karnataka-wide overview…"
                : "Run a query in Story Mode to see which regional perspectives a generic Karnataka answer misses."}
            </p>
          ) : (
            <>
              <RegionalCoverageChart rows={orderedRows} />
              <div className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-3">
                {orderedRows.map((row) => <ScoreTile key={row.regionId} row={row} />)}
              </div>
            </>
          )}
        </div>
      </section>
    </div>
  );
}
