/**
 * Views for the stunting topic (the second study, beside dropout): NITI's prescriptive model for
 * under-5 stunting -- a statewide overview, one district, and one region. All numbers come from
 * public/data/niti-stunting.json (or /api/stunting); nothing here is about any persona.
 */

import { useEffect, useMemo } from "react";

import {
  KARNATAKA_REGIONS,
  regionColor,
  rgbaCss,
  useExplorerStore,
  usePersonaLibrary,
  prescribe,
  LIBRARY_LIVE,
  runTopic,
  STUNTING_QUERY,
  useStunting,
  useStuntingSettings,
  useWorldviewStore,
  type StuntingDistrict,
  type StuntingFactorInfo,
  type StuntingModel,
} from "@/lib/worldview";

import { StuntingKeyFindingsSummary } from "@/components/dashboard/KeyFindings";

import { StuntingKeyFindings } from "./StuntingResearchViews";

const pct = (v: number | null | undefined, d = 1) => (v == null ? "—" : `${v.toFixed(d)}%`);

function ordinal(n: number): string {
  const s = ["th", "st", "nd", "rd"];
  const v = n % 100;
  return `${n}${s[(v - 20) % 10] ?? s[v] ?? s[0]}`;
}

function useNames(): Record<string, string> {
  const districts = usePersonaLibrary((s) => s.districts);
  const load = usePersonaLibrary((s) => s.load);
  useEffect(() => {
    void load();
  }, [load]);
  return useMemo(
    () => Object.fromEntries(districts.map((d) => [d.districtId, d.name])),
    [districts],
  );
}

function regionOf(
  districtId: string,
  districts: { districtId: string; regionId: string }[],
): string {
  return districts.find((d) => d.districtId === districtId)?.regionId ?? "";
}

/** Horizontal bar, 0..max. */
function Bar({ value, max, color }: { value: number; max: number; color: string }) {
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-secondary">
      <div
        className="h-full rounded-full"
        style={{ width: `${Math.min(100, (value / max) * 100)}%`, backgroundColor: color }}
      />
    </div>
  );
}

function Loading({ data }: { data: StuntingModel | null | undefined }) {
  return (
    <p className="text-[12px] text-muted-foreground">
      {data === undefined ? "Loading the stunting data…" : "The stunting data could not be loaded."}
    </p>
  );
}

// ── Target controls (shared by every stunting view) ─────────────────────────

const WEIGHTS = [0.25, 0.5, 0.75, 1];

/** The workbook's controls: the target cut, and an optional bucket to prioritise (Custom Priority). */
export function StuntingControls({ buckets }: { buckets: string[] }) {
  const { reduceBy, priorityBucket, priorityWeight, set } = useStuntingSettings();
  const isDefault = reduceBy === 0.2 && !priorityBucket;
  return (
    <div className="rounded-xl border border-panel-border bg-secondary/30 px-3 py-2.5">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <label className="flex min-w-[220px] flex-1 items-center gap-3 text-[11.5px] text-muted-foreground">
          <span className="shrink-0">Cut stunting by</span>
          <input
            type="range"
            min={0.05}
            max={0.5}
            step={0.05}
            value={reduceBy}
            onChange={(e) => set({ reduceBy: Number(e.target.value) })}
            aria-label="Target reduction in stunting"
            className="min-w-0 flex-1 accent-foreground"
          />
          <span className="w-9 shrink-0 text-right font-semibold tabular-nums text-foreground">
            {Math.round(reduceBy * 100)}%
          </span>
        </label>
        <label className="flex items-center gap-2 text-[11.5px] text-muted-foreground">
          Priority
          <select
            value={priorityBucket ?? ""}
            onChange={(e) => set({ priorityBucket: e.target.value || null })}
            className="rounded-md border border-panel-border bg-background/60 px-2 py-1 text-[11.5px] text-foreground"
          >
            <option value="">Equal allocation</option>
            {buckets.map((b) => (
              <option key={b} value={b}>
                {b}
              </option>
            ))}
          </select>
        </label>
        {priorityBucket && (
          <label className="flex items-center gap-2 text-[11.5px] text-muted-foreground">
            takes
            <select
              value={priorityWeight}
              onChange={(e) => set({ priorityWeight: Number(e.target.value) })}
              className="rounded-md border border-panel-border bg-background/60 px-2 py-1 text-[11.5px] text-foreground"
            >
              {WEIGHTS.map((w) => (
                <option key={w} value={w}>
                  {Math.round(w * 100)}%
                </option>
              ))}
            </select>
            of the cut
          </label>
        )}
        {!isDefault && (
          <button
            type="button"
            onClick={() => set({ reduceBy: 0.2, priorityBucket: null, priorityWeight: 0.5 })}
            className="text-[11px] text-muted-foreground underline underline-offset-2 hover:text-foreground"
          >
            Reset to NITI default
          </button>
        )}
      </div>
    </div>
  );
}

// ── One district ─────────────────────────────────────────────────────────────

export function StuntingDistrictView({
  districtId,
  compact = false,
}: {
  districtId: string;
  compact?: boolean;
}) {
  const data = useStunting();
  if (!data) return <Loading data={data} />;
  const d = data.districts[districtId];
  if (!d || d.stunting == null)
    return (
      <p className="rounded-xl border border-dashed border-panel-border px-4 py-3 text-[12px] leading-snug text-muted-foreground">
        The stunting workbook has no figures for {d?.area ?? "this district"} (it carries only an
        empty placeholder row), so there is nothing to show here.
      </p>
    );
  return <DistrictBody d={d} data={data} compact={compact} />;
}

function DistrictBody({
  d,
  data,
  compact,
}: {
  d: StuntingDistrict;
  data: StuntingModel;
  compact: boolean;
}) {
  const info: Record<string, StuntingFactorInfo> = Object.fromEntries(
    data.factors.map((f) => [f.name, f]),
  );
  const n = data.source.withData;
  const settings = useStuntingSettings();
  const { target, factors: all } = prescribe(data, d, settings);
  const maxChange = Math.max(...all.map((f) => f.change ?? 0), 1);
  const factors = compact ? all.slice(0, 5) : all;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-x-6 gap-y-2">
        <div>
          <p className="label-micro">Children under 5 who are stunted</p>
          <p className="mt-1 text-[34px] leading-none font-semibold tracking-tight text-foreground">
            {pct(d.stunting)}
          </p>
        </div>
        <div className="pb-1 text-[11px] leading-snug text-muted-foreground">
          {d.rankHighest && (
            <p>
              {d.rankHighest === 1 ? "Highest" : `${ordinal(d.rankHighest)} highest`} of {n}{" "}
              districts · Karnataka mean {pct(data.statewide.mean)}
            </p>
          )}
          <p>
            Model target ({Math.round(settings.reduceBy * 100)}% less):{" "}
            <span className="font-medium text-foreground tabular-nums">{pct(target)}</span>
          </p>
        </div>
      </div>

      <StuntingControls buckets={[...new Set(d.factors.map((f) => f.bucket))]} />

      <div>
        <p className="label-micro">
          What each factor would need to reach{compact ? " · top 5" : ""}
        </p>
        <p className="mt-1 text-[11px] leading-snug text-muted-foreground">
          Each factor&apos;s share of the cut, run back through the model: today&apos;s value → the
          value it would need. Largest change first, as in the NITI dashboard.
        </p>
        <ul className="mt-2.5 space-y-2">
          {factors.map((f) => {
            const fi = info[f.name];
            return (
              <li
                key={f.name}
                className="rounded-lg border border-panel-border bg-secondary/30 px-3 py-2"
              >
                <div className="flex items-baseline justify-between gap-3">
                  <p className="min-w-0 text-[12.5px] font-medium text-foreground" title={f.name}>
                    {fi?.short ?? f.name}
                    <span className="ml-1.5 text-[10.5px] font-normal text-muted-foreground">
                      {f.bucket}
                    </span>
                  </p>
                  <p className="shrink-0 text-[11.5px] tabular-nums text-foreground">
                    {pct(f.value)} → <span className="font-semibold">{pct(f.prescribed)}</span>
                  </p>
                </div>
                <div className="mt-1.5 flex items-center gap-3">
                  <div className="flex-1">
                    <Bar value={f.change ?? 0} max={maxChange} color="var(--chart-2)" />
                  </div>
                  <p className="w-[150px] shrink-0 text-right text-[10.5px] tabular-nums text-muted-foreground">
                    {f.change == null ? "—" : `${f.change.toFixed(1)}% change`} · rank {f.rank}/{n}
                    {f.atLimit ? " · at 0/100 limit" : ""}
                  </p>
                </div>
              </li>
            );
          })}
        </ul>
      </div>
      <p className="text-[10px] leading-snug text-muted-foreground">
        NFHS-6 district indicators (pre-school attendance: Poshan Tracker FY 2024-25). Rank 1 = best
        in Karnataka in the direction the model links to less stunting. {data.method.caveat}
      </p>
    </div>
  );
}

// ── One region ───────────────────────────────────────────────────────────────

export function StuntingRegionView({ regionId }: { regionId: string }) {
  const data = useStunting();
  const names = useNames();
  const districts = usePersonaLibrary((s) => s.districts);
  const focusDistrict = useExplorerStore((s) => s.focusDistrict);
  if (!data) return <Loading data={data} />;
  const ids = districts.filter((d) => d.regionId === regionId).map((d) => d.districtId);
  const rows = ids.map((id) => ({ id, d: data.districts[id] })).filter((r) => r.d);
  const vals = rows.map((r) => r.d!.stunting).filter((v): v is number => v != null);
  const avg = vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
  const color = rgbaCss(regionColor(regionId));
  return (
    <div className="grid gap-5 @lg:grid-cols-2">
      <section>
        <p className="label-micro">Average under-5 stunting · {vals.length} districts</p>
        <p className="mt-1.5 text-[34px] leading-none font-semibold tracking-tight text-foreground">
          {pct(avg)}
        </p>
        <p className="mt-2 text-[11px] text-muted-foreground">
          Karnataka mean {pct(data.statewide.mean)} (NFHS-6)
        </p>
      </section>
      <section>
        <p className="label-micro">Districts — click to zoom in</p>
        <ul className="mt-2 space-y-1.5">
          {rows
            .sort((a, b) => (b.d!.stunting ?? -1) - (a.d!.stunting ?? -1))
            .map(({ id, d }) => (
              <li key={id}>
                <button
                  type="button"
                  onClick={() => focusDistrict(id, regionId, "numbers")}
                  className="flex w-full items-center gap-2 rounded-md px-1 py-0.5 text-left text-[11.5px] text-muted-foreground transition-colors hover:text-foreground"
                >
                  <span className="w-28 shrink-0 truncate">{names[id] ?? d!.area}</span>
                  <span className="flex-1">
                    {d!.stunting != null && <Bar value={d!.stunting} max={50} color={color} />}
                  </span>
                  <span className="w-12 shrink-0 text-right tabular-nums text-foreground">
                    {pct(d!.stunting)}
                  </span>
                </button>
              </li>
            ))}
        </ul>
      </section>
    </div>
  );
}

// ── Statewide ────────────────────────────────────────────────────────────────

export function StuntingOverview() {
  const data = useStunting();
  const names = useNames();
  const districts = usePersonaLibrary((s) => s.districts);
  const focusDistrict = useExplorerStore((s) => s.focusDistrict);
  const settings = useStuntingSettings();
  if (!data) return <Loading data={data} />;
  const ranked = Object.values(data.districts)
    .filter((d) => d.stunting != null)
    .sort((a, b) => b.stunting! - a.stunting!);
  const regionAvg = KARNATAKA_REGIONS.map((r) => {
    const v = ranked
      .filter((d) => regionOf(d.districtId, districts) === r.id)
      .map((d) => d.stunting!);
    return { r, avg: v.length ? v.reduce((a, b) => a + b, 0) / v.length : null, n: v.length };
  }).sort((a, b) => (b.avg ?? 0) - (a.avg ?? 0));
  const byBucket = data.factors.reduce<Record<string, StuntingFactorInfo[]>>((acc, f) => {
    (acc[f.bucket] ??= []).push(f);
    return acc;
  }, {});

  return (
    <div className="space-y-7">
      <StuntingKeyFindingsSummary />

      <section>
        <p className="label-micro">Under-5 stunting · Karnataka</p>
        <div className="mt-3 grid grid-cols-2 gap-2 @xl:grid-cols-4">
          {[
            { v: pct(data.statewide.mean), l: "District mean" },
            {
              v: pct(data.statewide.highest?.value),
              l: `Highest · ${names[data.statewide.highest?.districtId ?? ""] ?? ""}`,
            },
            {
              v: pct(data.statewide.lowest?.value),
              l: `Lowest · ${names[data.statewide.lowest?.districtId ?? ""] ?? ""}`,
            },
            {
              v: `${data.source.withData}/${data.source.karnatakaDistricts}`,
              l: "Districts with data",
            },
          ].map((s) => (
            <div
              key={s.l}
              className="rounded-xl border border-panel-border bg-secondary/40 px-3 py-2.5"
            >
              <p className="text-[20px] leading-none font-semibold tabular-nums text-foreground">
                {s.v}
              </p>
              <p className="mt-1 text-[10px] tracking-wide text-muted-foreground uppercase">
                {s.l}
              </p>
            </div>
          ))}
        </div>
        {data.source.missing.length > 0 && (
          <p className="mt-2 text-[11px] text-muted-foreground">
            No figures in the workbook for {data.source.missing.join(", ")}.
          </p>
        )}
      </section>

      <StuntingKeyFindings />

      <StatewideTarget data={data} settings={settings} />

      <section>
        <p className="label-micro">By region</p>
        <ul className="mt-2.5 space-y-1.5">
          {regionAvg.map(({ r, avg, n }) => (
            <li key={r.id} className="flex items-center gap-3 text-[12px]">
              <span className="w-32 shrink-0 truncate text-foreground/90">{r.shortName}</span>
              <span className="flex-1">
                {avg != null && <Bar value={avg} max={50} color={rgbaCss(r.color)} />}
              </span>
              <span className="w-24 shrink-0 text-right tabular-nums text-muted-foreground">
                {pct(avg)} · {n} dist.
              </span>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <p className="label-micro">Every district — click to open it on the map</p>
        <ul className="mt-2.5 grid gap-x-5 gap-y-1 @xl:grid-cols-2">
          {ranked.map((d, i) => {
            const rid = regionOf(d.districtId, districts);
            return (
              <li key={d.districtId}>
                <button
                  type="button"
                  onClick={() => focusDistrict(d.districtId, rid, "numbers")}
                  className="flex w-full items-center gap-2 rounded-md px-1 py-0.5 text-left text-[11.5px] text-muted-foreground transition-colors hover:bg-secondary/50 hover:text-foreground"
                >
                  <span className="w-5 shrink-0 text-right tabular-nums">{i + 1}</span>
                  <span className="w-28 shrink-0 truncate text-foreground/90">
                    {names[d.districtId] ?? d.area}
                  </span>
                  <span className="flex-1">
                    <Bar value={d.stunting!} max={50} color={rgbaCss(regionColor(rid))} />
                  </span>
                  <span className="w-11 shrink-0 text-right tabular-nums text-foreground">
                    {pct(d.stunting)}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      </section>

      <section>
        <p className="label-micro">The model&apos;s {data.factors.length} factors</p>
        <p className="mt-1 text-[11px] leading-snug text-muted-foreground">
          Correlation with stunting across Karnataka&apos;s districts (Pearson r), and the Karnataka
          range.
        </p>
        <div className="mt-3 space-y-3">
          {Object.entries(byBucket).map(([bucket, fs]) => (
            <div
              key={bucket}
              className="rounded-xl border border-panel-border bg-secondary/30 px-3 py-2.5"
            >
              <p className="text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
                {bucket}
              </p>
              <ul className="mt-1.5 space-y-1.5">
                {fs.map((f) => (
                  <li key={f.name} className="text-[12px] leading-snug" title={f.measures}>
                    <div className="flex items-baseline justify-between gap-3">
                      <span className="text-foreground/90">{f.short}</span>
                      <span className="shrink-0 text-[11px] tabular-nums text-muted-foreground">
                        r {f.pearson?.toFixed(2) ?? "—"} · {f.karnataka.min.toFixed(0)}–
                        {f.karnataka.max.toFixed(0)}% · {f.better} is better
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>

      <section className="space-y-1.5 text-[11px] leading-snug text-muted-foreground">
        <p className="label-micro">How the model works</p>
        <p>{data.method.model}</p>
        <p>
          {data.method.target} {data.method.allocation} {data.method.prescribed}
        </p>
        <p>{data.method.caveat}</p>
        <p>
          Source: {data.source.from}. {data.source.dataset}.
        </p>
      </section>
    </div>
  );
}

/** What the chosen target means across Karnataka: which factor needs the largest change, in how many districts. */
function StatewideTarget({
  data,
  settings,
}: {
  data: StuntingModel;
  settings: ReturnType<typeof useStuntingSettings.getState>;
}) {
  const info = Object.fromEntries(data.factors.map((f) => [f.name, f]));
  const withData = Object.values(data.districts).filter((d) => d.stunting != null);
  const top: Record<string, number> = {};
  let atLimit = 0;
  let cells = 0;
  for (const d of withData) {
    const { factors } = prescribe(data, d, settings);
    if (factors[0]) top[factors[0].name] = (top[factors[0].name] ?? 0) + 1;
    atLimit += factors.filter((f) => f.atLimit).length;
    cells += factors.length;
  }
  const rows = Object.entries(top).sort((a, b) => b[1] - a[1]);
  const buckets = [...new Set(data.factors.map((f) => f.bucket))];
  return (
    <section>
      <p className="label-micro">Set a target</p>
      <div className="mt-2.5">
        <StuntingControls buckets={buckets} />
      </div>
      <p className="mt-3 text-[11.5px] leading-snug text-muted-foreground">
        At a {Math.round(settings.reduceBy * 100)}% cut, the factor that would have to move furthest
        (relative to today&apos;s value), by number of districts:
      </p>
      <ul className="mt-2 space-y-1.5">
        {rows.map(([name, n]) => (
          <li key={name} className="flex items-center gap-3 text-[12px]">
            <span className="w-44 shrink-0 truncate text-foreground/90" title={name}>
              {info[name]?.short ?? name}
            </span>
            <span className="flex-1">
              <Bar value={n} max={withData.length} color="var(--chart-2)" />
            </span>
            <span className="w-16 shrink-0 text-right tabular-nums text-muted-foreground">
              {n} of {withData.length}
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-[11px] leading-snug text-muted-foreground">
        {atLimit === 0
          ? "Every prescription stays within 0-100%."
          : `${atLimit} of ${cells} factor prescriptions hit the 0/100% limit, so those factors cannot deliver their share of the cut on their own.`}
      </p>
    </section>
  );
}

/** The left-column panel for the stunting topic (Map and UIDAI / NITI tabs). */
/** A live stunting pipeline run: start it, or follow its progress. */
function StuntingRunCard({
  onRun,
  isStreaming,
}: {
  onRun?: (() => void) | undefined;
  isStreaming?: boolean | undefined;
}) {
  const query = useWorldviewStore((s) => s.query);
  const runState = useWorldviewStore((s) => s.runState);
  const status = useWorldviewStore((s) => s.status);
  const setTab = useExplorerStore((s) => s.setTab);
  const haveRun = runTopic(query) === "stunting" && (runState === "done" || runState === "empty");
  if (isStreaming && runTopic(query) === "stunting")
    return (
      <div className="rounded-xl border border-panel-border bg-secondary/30 px-3 py-2.5">
        <p className="label-micro">Stunting analysis running</p>
        <p className="mt-1 text-[11.5px] text-muted-foreground">{status.ticker}</p>
        <div className="mt-2 h-1 overflow-hidden rounded-full bg-secondary">
          <div
            className="h-full rounded-full bg-foreground/60"
            style={{ width: `${Math.round(status.progress * 100)}%` }}
          />
        </div>
      </div>
    );
  if (haveRun)
    return (
      <p className="text-[11.5px] text-muted-foreground">
        Persona analysis loaded: “{query}”.{" "}
        <button
          type="button"
          onClick={() => setTab("Divergence")}
          className="underline underline-offset-2 hover:text-foreground"
        >
          Divergence
        </button>{" "}
        ·{" "}
        <button
          type="button"
          onClick={() => setTab("Data")}
          className="underline underline-offset-2 hover:text-foreground"
        >
          Data
        </button>
      </p>
    );
  if (!onRun || !LIBRARY_LIVE) return null;
  return (
    <div className="rounded-xl border border-dashed border-panel-border px-3 py-2.5">
      <p className="text-[11.5px] leading-snug text-muted-foreground">
        No persona analysis on stunting yet. Run the full pipeline on “{STUNTING_QUERY}”: social
        posts and web sources by region, 12 persona replies, then Divergence and the comparison with
        this model. Takes 10-20 minutes and uses paid model calls.
      </p>
      <button
        type="button"
        onClick={onRun}
        disabled={isStreaming}
        className="mt-2 rounded-full bg-foreground px-3.5 py-1.5 text-[11.5px] font-medium text-background disabled:opacity-50"
      >
        Run the stunting analysis
      </button>
    </div>
  );
}

export function StuntingPanel({
  onRun,
  isStreaming,
}: {
  onRun?: () => void;
  isStreaming?: boolean;
}) {
  return (
    <div className="panel-surface @container pointer-events-auto flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl">
      <header className="border-b border-panel-border px-5 py-3.5">
        <p className="label-micro">Study · under-5 stunting</p>
        <h2 className="mt-1 text-sm font-medium text-foreground">
          How stunted Karnataka&apos;s children are, district by district, and what NITI&apos;s
          model prescribes
        </h2>
      </header>
      <div className="min-h-0 flex-1 space-y-6 overflow-y-auto px-5 py-4 [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-border">
        <StuntingRunCard onRun={onRun} isStreaming={isStreaming} />
        <StuntingOverview />
      </div>
    </div>
  );
}

/**
 * On the run-based tabs (Ask chat, Divergence, Data): says which study the loaded analysis belongs to when it is
 * not the selected topic -- e.g. no stunting run exists yet, so the dropout run is still on screen.
 */
export function RunTopicNote({
  tab,
  onRunStunting,
  isStreaming,
}: {
  tab: string;
  onRunStunting?: () => void;
  isStreaming?: boolean;
}) {
  const topic = useExplorerStore((s) => s.topic);
  const setTopic = useExplorerStore((s) => s.setTopic);
  const query = useWorldviewStore((s) => s.query);
  const shown = tab === "Ask" ? "dropout" : runTopic(query);
  if (topic === shown) return null;
  return (
    <div className="panel-surface pointer-events-auto w-full rounded-xl px-4 py-2.5">
      <p className="text-[12px] text-muted-foreground">
        {tab === "Ask" ? (
          <>The Ask chat answers from the dropout study only. </>
        ) : (
          <>
            This tab shows the <span className="text-foreground">{shown}</span> analysis
            {query ? ` (“${query}”)` : ""}; there is no {topic} run yet.{" "}
          </>
        )}
        {topic === "stunting" && tab !== "Ask" && onRunStunting && LIBRARY_LIVE && !isStreaming ? (
          <button
            type="button"
            onClick={onRunStunting}
            className="underline underline-offset-2 hover:text-foreground"
          >
            Run the stunting analysis
          </button>
        ) : (
          <button
            type="button"
            onClick={() => setTopic(shown)}
            className="underline underline-offset-2 hover:text-foreground"
          >
            Switch to {shown}
          </button>
        )}
      </p>
    </div>
  );
}
