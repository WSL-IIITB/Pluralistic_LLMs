/**
 * The dashboard's home view: everything the study has found, aggregated across all
 * 30 Karnataka districts — what drives secondary-school dropout, how that differs by
 * region, which findings are best evidenced, and how the UIDAI/NITI factors fare
 * against local evidence. Built from the district research files; no query is run.
 */

import { useEffect, useMemo, useState } from "react";

import {
  CATEGORY_EMOJI,
  CATEGORY_LABEL,
  KARNATAKA_REGIONS,
  fetchAllDistrictResearch,
  rgbaCss,
  useDistrictProfiles,
  useExplorerStore,
  type DistrictResearch,
  type ReasonCategory,
} from "@/lib/worldview";

type ResearchMap = Record<string, DistrictResearch>;

const EVIDENCE_WEIGHT = { strong: 3, moderate: 2, thin: 1 } as const;
const VERDICTS = ["supports", "contradicts", "unclear", "no-evidence"] as const;
const VERDICT_LABEL: Record<(typeof VERDICTS)[number], string> = {
  supports: "Supports",
  contradicts: "Contradicts",
  unclear: "Unclear",
  "no-evidence": "No local evidence",
};
const VERDICT_BAR: Record<(typeof VERDICTS)[number], string> = {
  supports: "bg-emerald-400/80",
  contradicts: "bg-red-400/80",
  unclear: "bg-amber-400/80",
  "no-evidence": "bg-muted-foreground/35",
};

function useAllResearch(): ResearchMap | null {
  const [data, setData] = useState<ResearchMap | null>(null);
  useEffect(() => {
    let alive = true;
    void fetchAllDistrictResearch().then((r) => alive && setData(r));
    return () => {
      alive = false;
    };
  }, []);
  return data;
}

function Section({
  title,
  hint,
  children,
}: {
  title: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <section>
      <p className="label-micro">{title}</p>
      {hint && <p className="mt-1 text-[11px] leading-snug text-muted-foreground/70">{hint}</p>}
      <div className="mt-3">{children}</div>
    </section>
  );
}

function Stat({ value, label }: { value: string | number; label: string }) {
  return (
    <div className="rounded-xl border border-panel-border bg-secondary/40 px-3 py-2.5">
      <p className="text-[20px] leading-none font-semibold tabular-nums text-foreground">{value}</p>
      <p className="mt-1 text-[10px] tracking-wide text-muted-foreground uppercase">{label}</p>
    </div>
  );
}

export function OverviewPanel() {
  const research = useAllResearch();
  const { byId } = useDistrictProfiles();
  const focusRegion = useExplorerStore((s) => s.focusRegion);
  const focusDistrict = useExplorerStore((s) => s.focusDistrict);

  const agg = useMemo(() => {
    if (!research) return null;
    const districts = Object.values(research);
    const n = districts.length;

    // Reason categories: in how many districts does each appear, weighted by evidence?
    const catDistricts: Record<string, Set<string>> = {};
    const catScore: Record<string, number> = {};
    const regionCats: Record<string, Record<string, number>> = {};
    const strong: {
      district: string;
      id: string;
      regionId: string;
      factor: string;
      category: ReasonCategory;
      detail: string;
    }[] = [];
    for (const d of districts) {
      for (const r of d.reasons) {
        (catDistricts[r.category] ??= new Set()).add(d.districtId);
        catScore[r.category] = (catScore[r.category] ?? 0) + EVIDENCE_WEIGHT[r.evidence];
        const rc = (regionCats[d.regionId] ??= {});
        rc[r.category] = (rc[r.category] ?? 0) + EVIDENCE_WEIGHT[r.evidence];
        if (r.evidence === "strong")
          strong.push({
            district: d.name,
            id: d.districtId,
            regionId: d.regionId,
            factor: r.factor,
            category: r.category,
            detail: r.detail,
          });
      }
    }
    const categories = Object.keys(catDistricts)
      .map((c) => ({
        category: c as ReasonCategory,
        districts: catDistricts[c]!.size,
        score: catScore[c] ?? 0,
      }))
      .sort((a, b) => b.districts - a.districts || b.score - a.score);

    const verdicts: Record<"state" | "district", Record<string, number>> = {
      state: {},
      district: {},
    };
    for (const d of districts)
      for (const c of d.officialFactorCheck ?? [])
        verdicts[c.method][c.verdict] = (verdicts[c.method][c.verdict] ?? 0) + 1;

    const urls = new Set<string>();
    const outlets = new Set<string>();
    let headlines = 0;
    for (const d of districts) {
      headlines += d.headlines.length;
      for (const s of d.sources) {
        urls.add(s.url);
        outlets.add(s.outlet);
      }
    }
    const coverage = { moderate: 0, thin: 0, rich: 0 } as Record<string, number>;
    for (const d of districts) coverage[d.coverage] = (coverage[d.coverage] ?? 0) + 1;

    return {
      n,
      categories,
      regionCats,
      strong,
      verdicts,
      sources: urls.size,
      outlets: outlets.size,
      headlines,
      coverage,
    };
  }, [research]);

  const regionRates = useMemo(() => {
    const out: Record<string, { avg: number | null; n: number }> = {};
    for (const r of KARNATAKA_REGIONS) {
      const rates = Object.values(byId)
        .filter((d) => d.regionId === r.id)
        .map((d) => d.dropoutRate)
        .filter((x): x is number => typeof x === "number");
      out[r.id] = {
        avg: rates.length ? rates.reduce((a, b) => a + b, 0) / rates.length : null,
        n: Object.values(byId).filter((d) => d.regionId === r.id).length,
      };
    }
    return out;
  }, [byId]);

  return (
    <div className="panel-surface @container pointer-events-auto flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl">
      <header className="border-b border-panel-border px-5 py-3.5">
        <p className="label-micro">Study overview</p>
        <h2 className="mt-1 text-[15px] font-semibold text-foreground">
          Secondary school dropouts in India
        </h2>
        <p className="mt-1 text-[12px] leading-relaxed text-muted-foreground">
          What media, government and NGO sources say about why students leave school across
          Karnataka&apos;s 30 districts. Click a region or district on the map to go deeper.
        </p>
      </header>

      <div className="min-h-0 flex-1 space-y-7 overflow-y-auto px-5 py-5 [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-border">
        {!agg ? (
          <p className="py-10 text-center text-[13px] text-muted-foreground">
            Loading the research…
          </p>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-2 @xl:grid-cols-4">
              <Stat value={agg.n} label="Districts researched" />
              <Stat value={agg.sources} label="Sources cited" />
              <Stat value={agg.headlines} label="News items" />
              <Stat
                value={`${agg.coverage["moderate"] ?? 0} / ${agg.n}`}
                label="Moderate coverage or better"
              />
            </div>

            <Section
              title="What drives dropout, statewide"
              hint="Share of districts where each kind of reason was documented. Bars count districts, not students."
            >
              <ul className="space-y-2.5">
                {agg.categories.map((c) => (
                  <li key={c.category}>
                    <div className="flex items-baseline justify-between gap-3">
                      <span className="text-[12px] text-foreground/90">
                        <span className="mr-1.5">{CATEGORY_EMOJI[c.category]}</span>
                        {CATEGORY_LABEL[c.category]}
                      </span>
                      <span className="shrink-0 text-[11px] tabular-nums text-muted-foreground">
                        {c.districts} of {agg.n}
                      </span>
                    </div>
                    <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-secondary">
                      <div
                        className="h-full rounded-full bg-primary/80"
                        style={{ width: `${(c.districts / agg.n) * 100}%` }}
                      />
                    </div>
                  </li>
                ))}
              </ul>
            </Section>

            <Section
              title="By region"
              hint="Average casefile dropout rate and the reasons documented most in each region's districts."
            >
              <ul className="space-y-2">
                {KARNATAKA_REGIONS.map((r) => {
                  const top = Object.entries(agg.regionCats[r.id] ?? {})
                    .sort((a, b) => b[1] - a[1])
                    .slice(0, 3);
                  const rate = regionRates[r.id];
                  return (
                    <li key={r.id}>
                      <button
                        type="button"
                        onClick={() => focusRegion(r.id)}
                        className="w-full rounded-xl border border-panel-border bg-secondary/30 px-3.5 py-3 text-left transition-colors hover:bg-secondary/60"
                      >
                        <div className="flex items-center justify-between gap-3">
                          <span className="flex items-center gap-2 text-[13px] font-medium text-foreground">
                            <span
                              className="size-2.5 rounded-[3px]"
                              style={{ backgroundColor: rgbaCss(r.color) }}
                              aria-hidden
                            />
                            {r.shortName}
                          </span>
                          <span className="text-[11px] text-muted-foreground tabular-nums">
                            {rate?.n ?? 0} districts
                            {rate?.avg != null && <> · avg dropout {rate.avg.toFixed(1)}%</>}
                          </span>
                        </div>
                        <div className="mt-2 flex flex-wrap gap-1.5">
                          {top.map(([cat]) => (
                            <span
                              key={cat}
                              className="rounded-full bg-background/50 px-2.5 py-0.5 text-[11px] text-muted-foreground"
                            >
                              {CATEGORY_EMOJI[cat]} {CATEGORY_LABEL[cat as ReasonCategory] ?? cat}
                            </span>
                          ))}
                        </div>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </Section>

            <Section
              title="Best-evidenced findings"
              hint="Reasons rated 'strong' — several sources, specific to the district."
            >
              <ul className="space-y-2">
                {agg.strong.slice(0, 10).map((s, i) => (
                  <li key={`${s.id}-${i}`}>
                    <button
                      type="button"
                      onClick={() => focusDistrict(s.id, s.regionId)}
                      className="w-full rounded-xl border border-panel-border bg-secondary/30 px-3.5 py-2.5 text-left transition-colors hover:bg-secondary/60"
                    >
                      <p className="text-[12.5px] font-semibold text-foreground">
                        {CATEGORY_EMOJI[s.category]} {s.district}: {s.factor}
                      </p>
                      <p className="mt-0.5 text-[11.5px] leading-snug text-muted-foreground">
                        {s.detail}
                      </p>
                    </button>
                  </li>
                ))}
              </ul>
            </Section>

            <Section
              title="UIDAI / NITI factors vs local evidence"
              hint="For each district we asked whether media and official sources support the factor the statistical files name."
            >
              <div className="space-y-3">
                {(["state", "district"] as const).map((m) => {
                  const tally = agg.verdicts[m];
                  const total = VERDICTS.reduce((a, v) => a + (tally[v] ?? 0), 0);
                  if (!total) return null;
                  return (
                    <div key={m}>
                      <p className="text-[11.5px] text-foreground/90">
                        {m === "state"
                          ? "State-level factor (household sanitation)"
                          : "District-specific factor"}
                      </p>
                      <div className="mt-1.5 flex h-2 overflow-hidden rounded-full bg-secondary">
                        {VERDICTS.map((v) =>
                          tally[v] ? (
                            <div
                              key={v}
                              className={VERDICT_BAR[v]}
                              style={{ width: `${(tally[v]! / total) * 100}%` }}
                              title={`${VERDICT_LABEL[v]}: ${tally[v]}`}
                            />
                          ) : null,
                        )}
                      </div>
                      <p className="mt-1 text-[10.5px] text-muted-foreground/80">
                        {VERDICTS.filter((v) => tally[v])
                          .map((v) => `${VERDICT_LABEL[v]} ${tally[v]}`)
                          .join(" · ")}
                      </p>
                    </div>
                  );
                })}
                <p className="text-[10.5px] leading-snug text-muted-foreground/60">
                  &quot;No local evidence&quot; means the sources were silent on the factor — not
                  that it is irrelevant.
                </p>
              </div>
            </Section>

            <p className="text-[10.5px] leading-snug text-muted-foreground/60">
              Built from {agg.sources} sources across {agg.outlets} outlets. Coverage:{" "}
              {agg.coverage["moderate"] ?? 0} districts moderate, {agg.coverage["thin"] ?? 0} thin.
              Every figure was checked against its cited page; claims that were not about the
              district were dropped.
            </p>
          </>
        )}
      </div>
    </div>
  );
}
