/**
 * The UIDAI / NITI tab: everything in the two official dominant-factor workbooks, in one place.
 *
 * Karnataka first (every district row, both methods, the casefile dropout rate as separate context, and what our
 * research checks found), then the full all-India data the workbooks hold (each state's state-level factor, the
 * most common district-level factors, and a browser for any state's rows). The values are shown as published and
 * never compared or blended: what they measure is not verified.
 */

import { useMemo, useState } from "react";

import { CHECK_STYLE, WHY_STYLE } from "@/components/dashboard/map/factorWhyStyle";
import {
  KARNATAKA_REGIONS,
  rgbaCss,
  shortFactor,
  useAllResearch,
  useDistrictProfiles,
  useExplorerStore,
  useNitiData,
  type DistrictProfile,
  type DistrictResearch,
  type NitiRow,
} from "@/lib/worldview";

type Method = "state" | "district";

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
      {hint && <p className="mt-1 text-[11px] leading-snug text-muted-foreground">{hint}</p>}
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

const CHECK_SHORT: Record<string, string> = {
  supports: "supports",
  contradicts: "contradicts",
  unclear: "unclear",
  "no-evidence": "none found",
};
const WHY_SHORT: Record<string, string> = {
  supported: "supported",
  partly: "partly",
  "not-supported": "not supported",
  "no-evidence": "none found",
};

function Pill({ text, className }: { text: string; className: string }) {
  return (
    <span
      className={"rounded-full px-1.5 py-px text-[10px] font-medium whitespace-nowrap " + className}
    >
      {text}
    </span>
  );
}

/** Research verdicts for one method of one district: the earlier local-evidence check, then the "why" research. */
function Verdicts({ r, method }: { r: DistrictResearch | undefined; method: Method }) {
  const check = r?.officialFactorCheck?.find((c) => c.method === method);
  const why = [
    ...new Set(
      (r?.dominantFactorWhy?.entries ?? [])
        .filter((e) => e.method === method)
        .map((e) => e.verdict),
    ),
  ];
  return (
    <div className="flex flex-wrap gap-1">
      {check ? (
        <Pill
          text={`check: ${CHECK_SHORT[check.verdict]}`}
          className={CHECK_STYLE[check.verdict].className}
        />
      ) : (
        <span className="text-[10px] text-muted-foreground">no check</span>
      )}
      {why.map((v) => (
        <Pill key={v} text={`why: ${WHY_SHORT[v]}`} className={WHY_STYLE[v].className} />
      ))}
    </div>
  );
}

function valuesFor(
  p: DistrictProfile,
  method: Method,
  name: string,
): { label: string; value: number; factor: string }[] {
  return p.nitiFactors
    .filter((f) => f.method === method)
    .map((f) => ({
      label: f.area.toLowerCase() === name.toLowerCase() ? "" : f.area,
      value: f.value,
      factor: f.factor,
    }));
}

function KarnatakaTable({
  byId,
  research,
}: {
  byId: Record<string, DistrictProfile>;
  research: Record<string, DistrictResearch> | null;
}) {
  const focusDistrict = useExplorerStore((s) => s.focusDistrict);
  const stateFactor = Object.values(byId)[0]?.nitiFactors.find((f) => f.method === "state")?.factor;

  return (
    <div>
      {stateFactor && (
        <p className="mb-2 text-[11px] text-muted-foreground">
          State-level factor on every Karnataka row:{" "}
          <span className="text-foreground/90">{stateFactor}</span>
        </p>
      )}
      <div className="overflow-hidden rounded-xl border border-panel-border">
        {KARNATAKA_REGIONS.map((region) => {
          const ids = Object.values(byId)
            .filter((d) => d.regionId === region.id)
            .map((d) => d.districtId)
            .sort((a, b) => (research?.[a]?.name ?? a).localeCompare(research?.[b]?.name ?? b));
          return (
            <div key={region.id}>
              <p className="border-b border-panel-border bg-secondary/40 px-3 py-1.5 text-[11px] font-semibold text-foreground">
                <span
                  className="mr-1.5 inline-block size-2 rounded-[3px] align-middle"
                  style={{ backgroundColor: rgbaCss(region.color) }}
                  aria-hidden
                />
                {region.shortName}
              </p>
              {ids.map((id) => {
                const p = byId[id]!;
                const r = research?.[id];
                const name = r?.name ?? id;
                const st = valuesFor(p, "state", name);
                const di = valuesFor(p, "district", name);
                const rate =
                  p.dropoutRate != null
                    ? `${p.dropoutRate}%`
                    : p.subAreas
                        .map(
                          (s) => `${s.name.replace(name, "").trim() || s.name} ${s.dropoutRate}%`,
                        )
                        .join(" · ");
                return (
                  <div key={id} className="border-b border-panel-border px-3 py-2.5 last:border-0">
                    <div className="flex items-baseline justify-between gap-3">
                      <button
                        type="button"
                        onClick={() => focusDistrict(id, region.id)}
                        className="text-left text-[12.5px] font-semibold text-foreground underline-offset-2 hover:underline"
                        title="Show on the map"
                      >
                        {name}
                      </button>
                      <span className="shrink-0 text-[11px] text-muted-foreground">
                        dropout* <span className="tabular-nums text-foreground/90">{rate}</span>
                      </span>
                    </div>
                    <div className="mt-1.5 grid grid-cols-[5.5rem_1fr] gap-x-2 gap-y-1.5 text-[11.5px]">
                      <span className="text-muted-foreground">State-level</span>
                      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                        {st.map((v, i) => (
                          <span key={i} className="tabular-nums">
                            {v.label && <span className="text-muted-foreground">{v.label} </span>}
                            <span className="text-foreground">{v.value}</span>
                          </span>
                        ))}
                        <Verdicts r={r} method="state" />
                      </div>
                      <span className="text-muted-foreground">District-level</span>
                      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                        {di.map((v, i) => (
                          <span key={i} title={v.factor}>
                            <span className="text-foreground/90">{shortFactor(v.factor)}</span>
                            {v.label && (
                              <span className="text-muted-foreground"> · {v.label}</span>
                            )}{" "}
                            <span className="tabular-nums text-foreground">{v.value}</span>
                          </span>
                        ))}
                        <Verdicts r={r} method="district" />
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function VerdictTally({ research }: { research: Record<string, DistrictResearch> }) {
  const tally = (method: Method) => {
    const check: Record<string, number> = {};
    const why: Record<string, number> = {};
    for (const r of Object.values(research)) {
      for (const c of r.officialFactorCheck ?? [])
        if (c.method === method) check[c.verdict] = (check[c.verdict] ?? 0) + 1;
      for (const e of r.dominantFactorWhy?.entries ?? [])
        if (e.method === method) why[e.verdict] = (why[e.verdict] ?? 0) + 1;
    }
    return { check, why };
  };
  const line = (counts: Record<string, number>, short: Record<string, string>) =>
    Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .map(([k, n]) => `${short[k] ?? k} ${n}`)
      .join(" · ") || "none";
  return (
    <div className="grid gap-2 @lg:grid-cols-2">
      {(["state", "district"] as const).map((m) => {
        const t = tally(m);
        return (
          <div
            key={m}
            className="rounded-xl border border-panel-border bg-secondary/30 px-3 py-2.5 text-[11.5px]"
          >
            <p className="font-medium text-foreground">
              {m === "state" ? "State-level factor rows" : "District-level factor rows"}
            </p>
            <p className="mt-1 text-muted-foreground">
              <span className="text-foreground/80">Local-evidence check:</span>{" "}
              {line(t.check, CHECK_SHORT)}
            </p>
            <p className="mt-0.5 text-muted-foreground">
              <span className="text-foreground/80">“Why dominant” research:</span>{" "}
              {line(t.why, WHY_SHORT)}
            </p>
          </div>
        );
      })}
    </div>
  );
}

function StateFactorTable({ rows }: { rows: NitiRow[] }) {
  const byState = useMemo(() => {
    const m = new Map<string, { factors: Map<string, number>; districts: number }>();
    for (const r of rows) {
      const e = m.get(r.state) ?? { factors: new Map<string, number>(), districts: 0 };
      e.districts += 1;
      e.factors.set(r.stateFactor, (e.factors.get(r.stateFactor) ?? 0) + 1);
      m.set(r.state, e);
    }
    return [...m.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [rows]);
  return (
    <div className="max-h-[320px] overflow-y-auto rounded-xl border border-panel-border [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-border">
      <table className="w-full border-collapse text-[11.5px]">
        <thead className="sticky top-0 bg-card">
          <tr className="border-b border-panel-border text-left text-[10px] tracking-wide text-muted-foreground uppercase">
            <th className="px-2.5 py-2 font-medium">State / UT</th>
            <th className="px-2.5 py-2 font-medium">State-level factor</th>
            <th className="px-2.5 py-2 text-right font-medium">Districts</th>
          </tr>
        </thead>
        <tbody>
          {byState.map(([state, e]) => (
            <tr
              key={state}
              className={
                "border-b border-panel-border align-top last:border-0 " +
                (state === "Karnataka" ? "bg-primary/10" : "")
              }
            >
              <td className="px-2.5 py-1.5 font-medium text-foreground">{state}</td>
              <td className="px-2.5 py-1.5 text-foreground/90">
                {[...e.factors.entries()].map(([f, n]) => (
                  <div key={f}>
                    {f}
                    {e.factors.size > 1 && (
                      <span className="text-muted-foreground"> ({n} districts)</span>
                    )}
                  </div>
                ))}
              </td>
              <td className="px-2.5 py-1.5 text-right tabular-nums text-muted-foreground">
                {e.districts}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TopDistrictFactors({ rows }: { rows: NitiRow[] }) {
  const top = useMemo(() => {
    const c = new Map<string, number>();
    for (const r of rows)
      if (r.districtFactor) c.set(r.districtFactor, (c.get(r.districtFactor) ?? 0) + 1);
    return [...c.entries()].sort((a, b) => b[1] - a[1]);
  }, [rows]);
  const max = top[0]?.[1] ?? 1;
  return (
    <div>
      <ul className="space-y-1.5">
        {top.slice(0, 12).map(([f, n]) => (
          <li key={f}>
            <div className="flex items-baseline justify-between gap-3 text-[11.5px]">
              <span className="text-foreground/90">{f}</span>
              <span className="shrink-0 tabular-nums text-muted-foreground">{n}</span>
            </div>
            <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-secondary">
              <div
                className="h-full rounded-full bg-primary/70"
                style={{ width: `${(n / max) * 100}%` }}
              />
            </div>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-[10.5px] text-muted-foreground">
        {top.length} different district-level factors appear across India; the 12 most common are
        shown. Bars count districts, not importance.
      </p>
    </div>
  );
}

function StateBrowser({ rows }: { rows: NitiRow[] }) {
  const states = useMemo(() => [...new Set(rows.map((r) => r.state))].sort(), [rows]);
  const [state, setState] = useState("Karnataka");
  const list = rows.filter((r) => r.state === state);
  const oneStateFactor =
    new Set(list.map((r) => r.stateFactor)).size === 1 ? list[0]?.stateFactor : undefined;
  return (
    <div>
      <label className="flex items-center gap-2 text-[11.5px] text-muted-foreground">
        State / UT
        <select
          value={state}
          onChange={(e) => setState(e.target.value)}
          className="rounded-md border border-panel-border bg-card px-2 py-1 text-[12px] text-foreground"
        >
          {states.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <span className="tabular-nums">{list.length} rows</span>
      </label>
      {oneStateFactor && (
        <p className="mt-2 text-[11px] text-muted-foreground">
          State-level factor for every row:{" "}
          <span className="text-foreground/90">{oneStateFactor}</span>
        </p>
      )}
      <div className="mt-2 max-h-[360px] overflow-auto rounded-xl border border-panel-border [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-border">
        <table className="w-full min-w-[560px] border-collapse text-[11.5px]">
          <thead className="sticky top-0 bg-card">
            <tr className="border-b border-panel-border text-left text-[10px] tracking-wide text-muted-foreground uppercase">
              <th className="px-2.5 py-2 font-medium">District (as in the workbook)</th>
              <th className="px-2.5 py-2 font-medium">
                State-level{oneStateFactor ? " value" : " factor and value"}
              </th>
              <th className="px-2.5 py-2 font-medium">District-level factor and value</th>
            </tr>
          </thead>
          <tbody>
            {list.map((r) => (
              <tr key={r.district} className="border-b border-panel-border align-top last:border-0">
                <td className="px-2.5 py-1.5 text-foreground">{r.district}</td>
                <td className="px-2.5 py-1.5">
                  {!oneStateFactor && <span className="text-foreground/90">{r.stateFactor} </span>}
                  <span className="tabular-nums text-foreground">{r.stateValue}</span>
                </td>
                <td className="px-2.5 py-1.5">
                  <span className="text-foreground/90">{r.districtFactor ?? "—"}</span>{" "}
                  <span className="tabular-nums text-foreground">{r.districtValue ?? ""}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function NitiPanel() {
  const data = useNitiData();
  const research = useAllResearch();
  const { byId } = useDistrictProfiles();

  const stats = useMemo(() => {
    if (!data) return null;
    return {
      stateFactors: new Set(data.rows.map((r) => r.stateFactor)).size,
      districtFactors: new Set(data.rows.map((r) => r.districtFactor).filter(Boolean)).size,
      karnataka: data.rows.filter((r) => r.state === "Karnataka").length,
    };
  }, [data]);
  const extraStates = data
    ? [...new Set(data.factorOnlyRows.state.map((r) => r.state))].sort()
    : [];

  return (
    <div className="panel-surface @container pointer-events-auto flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl">
      <header className="border-b border-panel-border px-5 py-3.5">
        <p className="label-micro">Official statistics</p>
        <h2 className="mt-1 text-[15px] font-semibold text-foreground">
          UIDAI / NITI Aayog dominant-factor data
        </h2>
        <p className="mt-1 text-[12px] leading-relaxed text-muted-foreground">
          Everything in the two dominant-factor workbooks we were given: for every district in
          India, the factor a statistical analysis linked most strongly to secondary dropout, by two
          different methods. Karnataka first, then the whole country.
        </p>
      </header>

      <div className="min-h-0 flex-1 space-y-7 overflow-y-auto px-5 py-5 [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-border">
        {data === undefined ? (
          <p className="py-10 text-center text-[13px] text-muted-foreground">
            Loading the UIDAI / NITI data…
          </p>
        ) : data === null ? (
          <p className="py-10 text-center text-[13px] text-muted-foreground">
            The UIDAI / NITI data file could not be loaded. Reload the page to try again.
          </p>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-2 @xl:grid-cols-4">
              <Stat value={data.source.rows} label="District rows, India" />
              <Stat value={data.source.states} label="States / UTs" />
              <Stat value={stats?.karnataka ?? 0} label="Karnataka rows (30 districts)" />
              <Stat
                value={`${stats?.stateFactors ?? 0} / ${stats?.districtFactors ?? 0}`}
                label="Distinct factors (state / district)"
              />
            </div>

            <Section title="How to read this data">
              <ul className="space-y-1.5 rounded-xl border border-panel-border bg-secondary/30 px-3.5 py-3 text-[11.5px] leading-snug text-muted-foreground">
                <li>
                  <span className="font-medium text-foreground/90">State-level method.</span>{" "}
                  {data.methods.state}
                </li>
                <li>
                  <span className="font-medium text-foreground/90">District-level method.</span>{" "}
                  {data.methods.district}
                </li>
                <li>
                  The value column has no label in the workbooks, and what it measures could not be
                  verified. Values are shown as published; they are not percentages to compare
                  across districts, and the two methods are never blended.
                </li>
                <li>
                  A dominant factor is a statistical flag, not a proven cause. Our research checked
                  each Karnataka flag against local evidence: none was supported by
                  district-specific proof (see the research column and summary below).
                </li>
                <li>
                  * The dropout rate comes from a different source, the LKI-SSM casefile, and is
                  shown only for context.
                </li>
              </ul>
            </Section>

            <Section
              title="Karnataka, district by district"
              hint="Every Karnataka row in both workbooks, grouped by region. Click a district to see it on the map; its sheet has the full research."
            >
              {Object.keys(byId).length ? (
                <KarnatakaTable byId={byId} research={research} />
              ) : (
                <p className="text-[12px] text-muted-foreground">Loading district data…</p>
              )}
            </Section>

            {research && (
              <Section
                title="What our research found about these flags (Karnataka)"
                hint="Two checks per factor row: an earlier check against local evidence, and the later “why is this factor dominant here?” deep research, page-verified."
              >
                <VerdictTally research={research} />
              </Section>
            )}

            <Section
              title="All of India: state-level factor by state"
              hint="The state-level method ranks one factor highest for a whole state. Karnataka is highlighted."
            >
              <StateFactorTable rows={data.rows} />
              {extraStates.length > 0 && (
                <p className="mt-2 text-[10.5px] leading-snug text-muted-foreground">
                  {extraStates.join(", ")} show two state-level factors across their districts. The
                  same five state blocks also list {data.source.factorOnlyRows.state} factor names
                  with no district and a value of 0 (likely an export artefact); those rows are kept
                  in the data file but not shown as districts.
                </p>
              )}
            </Section>

            <Section title="All of India: most common district-level factors">
              <TopDistrictFactors rows={data.rows} />
            </Section>

            <Section
              title="Browse any state"
              hint="Every row the workbooks hold for one state or union territory."
            >
              <StateBrowser rows={data.rows} />
            </Section>

            <p className="text-[10.5px] leading-snug text-muted-foreground">
              Source: {data.source.files.join(" and ")} ({data.source.rows} district rows each,
              paired by state and district).
            </p>
          </>
        )}
      </div>
    </div>
  );
}
