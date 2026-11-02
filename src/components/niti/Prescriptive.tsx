/**
 * The NITI team's prescriptive model: 18 school and household factors per district and the "top changes" it ranks
 * highest. `PrescriptiveSummary` explains the model for the whole state (UIDAI / NITI tab); `DistrictPrescriptiveProfile`
 * shows one district's profile, factor by factor, with what each factor measures and why it could matter (the map's
 * district sheet). The workbook's own ranking ("NITI") and the capped one ("feasible") are shown side by side.
 */

import { ChevronDown } from "lucide-react";
import { useMemo } from "react";

import {
  formatFactorValue,
  useNitiPrescriptive,
  type NitiPrescriptive,
  type PrescriptiveArea,
  type PrescriptiveFactorInfo,
} from "@/lib/worldview";

function useFactorInfo(data: NitiPrescriptive | null | undefined) {
  return useMemo(() => {
    const out: Record<string, PrescriptiveFactorInfo> = {};
    for (const f of data?.factors ?? []) out[f.name] = f;
    return out;
  }, [data]);
}

function Loading({ data }: { data: NitiPrescriptive | null | undefined }) {
  return (
    <p className="text-[12px] text-muted-foreground">
      {data === undefined
        ? "Loading the NITI prescriptive model…"
        : "The NITI prescriptive file could not be loaded. Reload the page to try again."}
    </p>
  );
}

function TallyBars({
  title,
  tally,
  info,
  rows,
}: {
  title: string;
  tally: Record<string, number>;
  info: Record<string, PrescriptiveFactorInfo>;
  rows: number;
}) {
  const top = Object.entries(tally).slice(0, 6);
  return (
    <div className="rounded-xl border border-panel-border bg-secondary/30 p-3.5">
      <p className="text-[12px] font-semibold text-foreground">{title}</p>
      <ul className="mt-2.5 space-y-1.5 text-[11.5px]">
        {top.map(([name, n]) => (
          <li key={name}>
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-foreground/90">{info[name]?.short ?? name}</span>
              <span className="shrink-0 tabular-nums text-muted-foreground">
                {n}/{rows}
              </span>
            </div>
            <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-secondary">
              <div
                className="h-full rounded-full bg-primary/70"
                style={{ width: `${(n / rows) * 100}%` }}
              />
            </div>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-[10.5px] text-muted-foreground">
        Rows whose top three changes include the factor (of {rows}).
      </p>
    </div>
  );
}

/** The 18 factors grouped by bucket: what each measures, why it could matter, and what a change looks like. */
function FactorGlossary({ factors }: { factors: PrescriptiveFactorInfo[] }) {
  const buckets = useMemo(() => {
    const m = new Map<string, PrescriptiveFactorInfo[]>();
    for (const f of factors) m.set(f.bucket, [...(m.get(f.bucket) ?? []), f]);
    return [...m.entries()];
  }, [factors]);
  return (
    <div className="space-y-3">
      {buckets.map(([bucket, fs]) => (
        <div key={bucket}>
          <p className="text-[10.5px] font-medium tracking-wide text-muted-foreground uppercase">
            {bucket}
          </p>
          <div className="mt-1.5 space-y-1.5">
            {fs.map((f) => (
              <details key={f.name} className="group rounded-lg border border-panel-border">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-2.5 py-2 text-[11.5px] marker:hidden [&::-webkit-details-marker]:hidden">
                  <span className="font-medium text-foreground/90">{f.short}</span>
                  <span className="flex shrink-0 items-center gap-2 text-[10.5px] text-muted-foreground tabular-nums">
                    Karnataka median {formatFactorValue(f.name, f.karnataka.median)}
                    <ChevronDown className="size-3.5 transition-transform group-open:rotate-180" />
                  </span>
                </summary>
                <div className="space-y-1.5 border-t border-panel-border px-2.5 py-2 text-[11.5px] leading-snug text-muted-foreground">
                  <p>
                    <span className="font-medium text-foreground/90">Measures: </span>
                    {f.measures}
                  </p>
                  <p>
                    <span className="font-medium text-foreground/90">
                      Why it could matter (reasoning):{" "}
                    </span>
                    {f.why}
                  </p>
                  <p>
                    <span className="font-medium text-foreground/90">
                      What a change looks like:{" "}
                    </span>
                    {f.change}
                  </p>
                  <p className="text-[10.5px] tabular-nums">
                    Model: {f.better} is linked to lower dropout · slope {f.slope.toFixed(2)} ·
                    correlation {f.pearson.toFixed(2)} · range across Karnataka{" "}
                    {formatFactorValue(f.name, f.karnataka.min)}–
                    {formatFactorValue(f.name, f.karnataka.max)}
                  </p>
                </div>
              </details>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

export function PrescriptiveSummary() {
  const data = useNitiPrescriptive();
  const info = useFactorInfo(data);
  if (!data) return <Loading data={data} />;
  const rows = data.source.karnatakaRows;
  return (
    <div className="space-y-4">
      <ul className="space-y-1.5 rounded-xl border border-panel-border bg-secondary/30 px-3.5 py-3 text-[11.5px] leading-snug text-muted-foreground">
        <li>
          <span className="font-medium text-foreground/90">The model. </span>
          {data.method.model}
        </li>
        <li>
          <span className="font-medium text-foreground/90">Top changes. </span>
          {data.method.sensitivity} {data.method.contribution}
        </li>
        <li>
          <span className="font-medium text-foreground/90">Two rankings. </span>
          “NITI” is the ranking exactly as the workbook computes it. “Feasible” is the same formula
          with percentages capped at 100%. {data.method.feasible} In the published formula, the 10%
          step goes past 100% in {data.statewide.pastLimitRows} factor rows.
        </li>
        <li>{data.method.step}</li>
        <li>{data.method.caveat}</li>
      </ul>

      <div className="grid gap-2.5 @xl:grid-cols-2">
        <TallyBars
          title="Feasible ranking (capped at 100%)"
          tally={data.statewide.topFeasible}
          info={info}
          rows={rows}
        />
        <TallyBars
          title="NITI ranking (as published)"
          tally={data.statewide.topNiti}
          info={info}
          rows={rows}
        />
      </div>

      <div>
        <p className="text-[12px] font-semibold text-foreground">
          The {data.factors.length} factors, explained
        </p>
        <p className="mt-0.5 mb-2 text-[11px] text-muted-foreground">
          What each factor measures, why it could be linked to dropout (general reasoning, not a
          finding), and what improving it would look like.
        </p>
        <FactorGlossary factors={data.factors} />
      </div>

      <p className="text-[10.5px] leading-snug text-muted-foreground">
        Source: {data.source.from}; data {data.source.dataset}. {rows} Karnataka rows, {"  "}
        {data.source.factorsPerDistrict} factors each. Each district&apos;s full profile is in its
        sheet on the map, under Numbers.
      </p>
    </div>
  );
}

// ── One district ────────────────────────────────────────────────────────────

function AreaProfile({
  area,
  info,
  showName,
}: {
  area: PrescriptiveArea;
  info: Record<string, PrescriptiveFactorInfo>;
  showName: boolean;
}) {
  const max = Math.max(...area.factors.map((f) => f.feasible.contribution), 1);
  const top = area.topFeasible;
  const buckets = useMemo(() => {
    const m = new Map<string, typeof area.factors>();
    for (const f of area.factors) {
      const b = info[f.name]?.bucket ?? "Other";
      m.set(b, [...(m.get(b) ?? []), f]);
    }
    return [...m.entries()];
  }, [area, info]);

  return (
    <div className="space-y-3">
      {showName && <p className="text-[12px] font-semibold text-foreground">{area.area}</p>}
      <div className="flex flex-wrap gap-2">
        {area.dropout2023_24 != null && (
          <span className="rounded-md bg-secondary px-2 py-1 text-[11px] text-muted-foreground">
            Secondary dropout 2023-24{" "}
            <span className="font-medium text-foreground tabular-nums">
              {area.dropout2023_24.toFixed(1)}%
            </span>
          </span>
        )}
        {area.dropout2024_25 != null && (
          <span className="rounded-md bg-secondary px-2 py-1 text-[11px] text-muted-foreground">
            2024-25 file{" "}
            <span className="font-medium text-foreground tabular-nums">
              {area.dropout2024_25.toFixed(1)}%
            </span>
          </span>
        )}
      </div>

      <div className="rounded-xl border border-panel-border bg-secondary/30 p-3">
        <p className="text-[11.5px] font-semibold text-foreground">
          Top three changes the model ranks highest
        </p>
        <ol className="mt-2 space-y-2">
          {top.map((name, i) => {
            const f = area.factors.find((x) => x.name === name)!;
            const fi = info[name];
            return (
              <li key={name} className="flex gap-2.5">
                <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-primary/15 text-[10.5px] font-semibold text-primary tabular-nums">
                  {i + 1}
                </span>
                <div className="min-w-0 text-[11.5px] leading-snug">
                  <p className="font-medium text-foreground/90">
                    {fi?.short ?? name}{" "}
                    <span className="font-normal text-muted-foreground tabular-nums">
                      {formatFactorValue(name, f.value)} · rank {f.rank} of 35 ·{" "}
                      {f.feasible.contribution}% of the modelled effect
                    </span>
                  </p>
                  {fi && <p className="mt-0.5 text-muted-foreground">{fi.change}</p>}
                </div>
              </li>
            );
          })}
        </ol>
        <p className="mt-2.5 text-[10.5px] leading-snug text-muted-foreground">
          The NITI workbook&apos;s own ranking:{" "}
          {area.topNiti.map((n) => info[n]?.short ?? n).join(", ")}
          {area.topNiti.some((n) => area.factors.find((f) => f.name === n)?.pastLimit) &&
            " (includes factors already near 100%, where the published 10% step goes past 100%)"}
          .
        </p>
      </div>

      <div className="space-y-2.5">
        {buckets.map(([bucket, fs]) => (
          <div key={bucket}>
            <p className="text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
              {bucket}
            </p>
            <ul className="mt-1 space-y-1">
              {fs.map((f) => {
                const fi = info[f.name];
                return (
                  <li key={f.name}>
                    <details className="group">
                      <summary className="cursor-pointer list-none marker:hidden [&::-webkit-details-marker]:hidden">
                        <div className="flex items-baseline justify-between gap-2 text-[11.5px]">
                          <span className="flex items-center gap-1 text-foreground/90">
                            <ChevronDown className="size-3 shrink-0 text-muted-foreground transition-transform group-open:rotate-180" />
                            {fi?.short ?? f.name}
                            {top.includes(f.name) && (
                              <span className="rounded bg-primary/15 px-1 text-[9.5px] font-medium text-primary">
                                top 3
                              </span>
                            )}
                          </span>
                          <span className="shrink-0 text-[11px] text-muted-foreground tabular-nums">
                            {formatFactorValue(f.name, f.value)} · #{f.rank}
                          </span>
                        </div>
                        <div className="mt-1 ml-4 h-1 overflow-hidden rounded-full bg-secondary">
                          <div
                            className="h-full rounded-full bg-primary/60"
                            style={{ width: `${(f.feasible.contribution / max) * 100}%` }}
                          />
                        </div>
                      </summary>
                      {fi && (
                        <div className="mt-1.5 ml-4 space-y-1 text-[11px] leading-snug text-muted-foreground">
                          <p>{fi.measures}</p>
                          <p>
                            <span className="font-medium text-foreground/80">
                              Why it could matter (reasoning):{" "}
                            </span>
                            {fi.why}
                          </p>
                          <p className="tabular-nums">
                            Karnataka median {formatFactorValue(f.name, fi.karnataka.median)} ·
                            share of the modelled effect: feasible {f.feasible.contribution}%, NITI{" "}
                            {f.niti.contribution}%{f.pastLimit && " · already near 100%"}
                          </p>
                        </div>
                      )}
                    </details>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
}

export function DistrictPrescriptiveProfile({ districtId }: { districtId: string }) {
  const data = useNitiPrescriptive();
  const info = useFactorInfo(data);
  if (!data) return <Loading data={data} />;
  const d = data.districts[districtId];
  if (!d) return <p className="text-[12px] text-muted-foreground">No NITI profile rows here.</p>;
  return (
    <div className="space-y-5">
      {d.areas.map((a) => (
        <AreaProfile key={a.area} area={a} info={info} showName={d.areas.length > 1} />
      ))}
      <p className="text-[10px] leading-snug text-muted-foreground">
        From the NITI team&apos;s prescriptive model ({data.source.dataset}). # is the rank among
        Karnataka&apos;s 35 rows, 1 = best. Bars show each factor&apos;s share of the modelled
        effect of a 10% improvement (capped at 100%). A correlation across districts, not proof of
        cause.
      </p>
    </div>
  );
}
