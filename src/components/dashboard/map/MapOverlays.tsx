/**
 * Overlays on the right-half map: region pills + a "back to Karnataka" control
 * along the top, and the district / region detail sheet along the bottom
 * (shown when the map is focused on something).
 */

import { ArrowLeft, ExternalLink, X } from "lucide-react";
import { useMemo, useState } from "react";

import {
  CATEGORY_EMOJI,
  KARNATAKA_REGIONS,
  personaCard,
  regionColor,
  regionMeta,
  rgbaCss,
  useDistrictProfiles,
  researchSnapshotActive,
  useDistrictResearch,
  useExplorerStore,
  type DistrictNitiFactor,
  type DistrictProfile,
  type DistrictResearch,
} from "@/lib/worldview";
import { useDistrictGeo } from "./useDistrictGeo";

// ── Top: region pills ───────────────────────────────────────────────────────

export function RegionPills() {
  const regionId = useExplorerStore((s) => s.regionId);
  const districtId = useExplorerStore((s) => s.districtId);
  const focusRegion = useExplorerStore((s) => s.focusRegion);
  const resetFocus = useExplorerStore((s) => s.resetFocus);
  const focused = !!(regionId || districtId);

  return (
    <div className="pointer-events-none absolute inset-x-3 top-3 z-10 flex flex-wrap items-center gap-1.5">
      {focused && (
        <button
          type="button"
          onClick={resetFocus}
          className="pointer-events-auto flex items-center gap-1.5 rounded-full border border-panel-border bg-panel px-3 py-1 text-[11px] font-medium text-foreground backdrop-blur-md transition-colors hover:bg-secondary"
        >
          <ArrowLeft className="size-3" />
          All Karnataka
        </button>
      )}
      {KARNATAKA_REGIONS.map((r) => {
        const active = regionId === r.id;
        return (
          <button
            key={r.id}
            type="button"
            onClick={() => focusRegion(r.id)}
            aria-pressed={active}
            className={
              "pointer-events-auto flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium backdrop-blur-md transition-colors " +
              (active
                ? "border-foreground/40 bg-secondary text-foreground"
                : "border-panel-border bg-panel text-muted-foreground hover:text-foreground")
            }
          >
            <span className="size-2 rounded-full" style={{ backgroundColor: rgbaCss(r.color) }} aria-hidden />
            {r.shortName}
          </button>
        );
      })}
    </div>
  );
}

// ── Bottom: detail sheet ────────────────────────────────────────────────────

const METHOD_TITLE: Record<DistrictNitiFactor["method"], string> = {
  state: "State-level top factor",
  district: "District-specific factor",
};

function percent(n: number): string {
  return `${n.toFixed(1)}%`;
}

function ordinal(n: number): string {
  const s = ["th", "st", "nd", "rd"];
  const v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]!);
}

/** All districts on a 0–max axis, one dot each; the selected one is ringed. */
function RateStrip({ rates, current, color }: { rates: number[]; current: number | null; color: string }) {
  const max = Math.max(40, ...rates);
  const pos = (v: number) => `${(v / max) * 100}%`;
  return (
    <div className="mt-3">
      <div className="relative h-5">
        <div className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-border" />
        {rates.map((r, i) => (
          <span
            key={i}
            className="absolute top-1/2 size-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-muted-foreground/45"
            style={{ left: pos(r) }}
          />
        ))}
        {current !== null && (
          <span
            className="absolute top-1/2 size-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-background"
            style={{ left: pos(current), backgroundColor: color }}
          />
        )}
      </div>
      <div className="mt-1 flex justify-between text-[10px] tabular-nums text-muted-foreground/60">
        <span>0%</span>
        <span>{Math.round(max / 2)}%</span>
        <span>{Math.round(max)}%</span>
      </div>
    </div>
  );
}

function PersonaButtons({ regionId }: { regionId: string }) {
  const selectPersona = useExplorerStore((s) => s.selectPersona);
  const setTab = useExplorerStore((s) => s.setTab);
  const meta = regionMeta(regionId);
  if (!meta) return null;
  return (
    <div className="flex flex-wrap gap-1.5">
      {meta.personas.map((p) => {
        const card = personaCard(regionId, p.id);
        return (
          <button
            key={p.id}
            type="button"
            onClick={() => {
              selectPersona(regionId, p.id);
              setTab("Personas");
            }}
            className="flex items-center gap-1.5 rounded-full border border-panel-border bg-secondary/60 py-1 pr-3 pl-1.5 text-[11px] text-foreground transition-colors hover:bg-secondary"
          >
            <span className="text-sm leading-none">{card?.emoji ?? "👤"}</span>
            Meet the {p.id === "female" ? "woman" : "man"}
          </button>
        );
      })}
    </div>
  );
}


const EVIDENCE_STYLE: Record<DistrictResearch["reasons"][number]["evidence"], string> = {
  strong: "bg-emerald-500/15 text-emerald-300",
  moderate: "bg-amber-500/15 text-amber-300",
  thin: "bg-secondary text-muted-foreground",
};

function SourceChips({ ids, sources }: { ids: number[]; sources: DistrictResearch["sources"] }) {
  return (
    <span className="ml-1 inline-flex flex-wrap gap-1 align-middle">
      {ids.map((id) => {
        const src = sources.find((s) => s.id === id);
        if (!src) return null;
        return (
          <a
            key={id}
            href={src.url}
            target="_blank"
            rel="noopener noreferrer"
            title={`${src.outlet}${src.date ? ` · ${src.date}` : ""} — ${src.title}`}
            className="rounded bg-secondary px-1.5 text-[10px] leading-4 tabular-nums text-muted-foreground transition-colors hover:text-foreground"
          >
            {id}
          </a>
        );
      })}
    </span>
  );
}

function ResearchState({ districtId, name, view }: { districtId: string; name: string; view: "reasons" | "media" }) {
  const entry = useDistrictResearch(districtId);
  if (entry.status === "loading") return <p className="text-[12px] text-muted-foreground">Loading research…</p>;
  if (entry.status === "none")
    return <p className="text-[12px] leading-snug text-muted-foreground">No in-depth research has been added for {name} yet.</p>;
  const r = entry.data;

  if (view === "media") {
    return (
      <div className="space-y-5">
        <section>
          <p className="label-micro mb-2">In the news</p>
          <ul className="space-y-3">
            {r.headlines.map((h) => (
              <li key={h.url}>
                <a href={h.url} target="_blank" rel="noopener noreferrer" className="group flex items-start gap-1.5 text-[12.5px] leading-snug font-medium text-foreground hover:underline">
                  <span>{h.title}</span>
                  <ExternalLink className="mt-0.5 size-3 shrink-0 text-muted-foreground/60 group-hover:text-foreground" aria-hidden />
                </a>
                <p className="mt-0.5 text-[10.5px] text-muted-foreground/70">
                  {h.outlet}
                  {h.date && ` · ${h.date}`}
                </p>
                <p className="mt-1 text-[12px] leading-snug text-muted-foreground">{h.takeaway}</p>
              </li>
            ))}
          </ul>
        </section>
        <section>
          <p className="label-micro mb-2">All sources ({r.sources.length})</p>
          <ol className="space-y-1.5">
            {r.sources.map((s) => (
              <li key={s.id} className="flex gap-2 text-[11px] leading-snug text-muted-foreground">
                <span className="w-4 shrink-0 text-right tabular-nums text-muted-foreground/60">{s.id}</span>
                <a href={s.url} target="_blank" rel="noopener noreferrer" className="min-w-0 hover:text-foreground">
                  <span className="text-foreground/85">{s.title}</span> — {s.outlet}
                  {s.date && `, ${s.date}`} <span className="uppercase opacity-60">· {s.type}</span>
                </a>
              </li>
            ))}
          </ol>
        </section>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <section>
        <p className="text-[14px] leading-snug font-semibold text-foreground">{r.headline}</p>
        <p className="mt-2 text-[12.5px] leading-relaxed text-muted-foreground">{r.summary}</p>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-[10.5px] text-muted-foreground/70">
          <span className="rounded-full bg-secondary px-2 py-0.5 uppercase">{r.coverage} coverage</span>
          <span>Researched {r.researchedOn}</span>
        </div>
      </section>

      <section>
        <p className="label-micro mb-2">Why students leave here</p>
        <ul className="space-y-2.5">
          {r.reasons.map((x, i) => (
            <li key={i} className="rounded-xl border border-panel-border bg-secondary/30 p-3">
              <div className="flex items-start justify-between gap-2">
                <p className="text-[12.5px] font-semibold text-foreground">
                  <span className="mr-1.5">{CATEGORY_EMOJI[x.category] ?? "📌"}</span>
                  {x.factor}
                </p>
                <span className={"shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium uppercase " + EVIDENCE_STYLE[x.evidence]}>
                  {x.evidence}
                </span>
              </div>
              <p className="mt-1 text-[12px] leading-snug text-muted-foreground">
                {x.detail}
                <SourceChips ids={x.sources} sources={r.sources} />
              </p>
            </li>
          ))}
        </ul>
      </section>

      {r.keyFacts.length > 0 && (
        <section>
          <p className="label-micro mb-2">Key facts</p>
          <div className="grid gap-2 @lg:grid-cols-2">
            {r.keyFacts.map((f, i) => (
              <div key={i} className="rounded-xl border border-panel-border bg-secondary/30 px-3 py-2.5">
                <p className="text-[14px] leading-tight font-semibold text-foreground">{f.value}</p>
                <p className="mt-0.5 text-[11px] leading-snug text-muted-foreground">
                  {f.label}
                  <SourceChips ids={f.sources} sources={r.sources} />
                </p>
              </div>
            ))}
          </div>
        </section>
      )}

      {r.responses.length > 0 && (
        <section>
          <p className="label-micro mb-2">What's being done</p>
          <ul className="space-y-1.5">
            {r.responses.map((x, i) => (
              <li key={i} className="text-[12px] leading-snug text-muted-foreground">
                • {x.text}
                <SourceChips ids={x.sources} sources={r.sources} />
              </li>
            ))}
          </ul>
        </section>
      )}

      {r.gaps && <p className="text-[10.5px] leading-snug text-muted-foreground/60">Gaps: {r.gaps}</p>}
      {researchSnapshotActive() && (
        <p className="text-[10.5px] leading-snug text-amber-300/80">
          Showing the research as it was when this run was saved.
        </p>
      )}
      {r.verificationNotes && (
        <p className="text-[10.5px] leading-snug text-muted-foreground/60">Checked against cited pages: {r.verificationNotes}</p>
      )}
    </div>
  );
}

const VERDICT_STYLE: Record<NonNullable<DistrictResearch["officialFactorCheck"]>[number]["verdict"], { label: string; className: string }> = {
  supports: { label: "Local evidence supports", className: "bg-emerald-500/15 text-emerald-300" },
  contradicts: { label: "Local evidence contradicts", className: "bg-red-500/15 text-red-300" },
  unclear: { label: "Unclear", className: "bg-amber-500/15 text-amber-300" },
  "no-evidence": { label: "No local evidence found", className: "bg-secondary text-muted-foreground" },
};

function DistrictNumbers({
  districtId,
  profile,
  name,
  allRates,
}: {
  districtId: string;
  profile: DistrictProfile | undefined;
  name: string;
  allRates: number[];
}) {
  const research = useDistrictResearch(districtId);
  const checks = research.status === "ready" ? (research.data.officialFactorCheck ?? []) : [];
  const sources = research.status === "ready" ? research.data.sources : [];
  const color = rgbaCss(regionColor(profile?.regionId ?? ""));
  const rate = profile?.dropoutRate ?? null;
  const sorted = useMemo(() => [...allRates].sort((a, b) => b - a), [allRates]);
  const median = sorted.length ? sorted[Math.floor(sorted.length / 2)]! : null;
  const rank = rate !== null ? sorted.findIndex((r) => r <= rate) + 1 : null;

  const byMethod = (m: DistrictNitiFactor["method"]) => (profile?.nitiFactors ?? []).filter((f) => f.method === m);

  return (
    <div className="grid gap-5 @lg:grid-cols-2">
      <section>
        <p className="label-micro">Secondary dropout rate</p>
        {rate !== null ? (
          <>
            <div className="mt-1.5 flex items-baseline gap-2">
              <span className="text-[34px] leading-none font-semibold tracking-tight text-foreground">{percent(rate)}</span>
              {rank !== null && (
                <span className="text-[11px] text-muted-foreground">
                  {ordinal(rank)} highest of {sorted.length} districts
                  {median !== null ? ` · median ${percent(median)}` : ""}
                </span>
              )}
            </div>
            <RateStrip rates={allRates} current={rate} color={color} />
          </>
        ) : (
          <p className="mt-1.5 text-[12px] leading-snug text-muted-foreground">
            {name} is reported only as sub-areas in the casefile — see below.
          </p>
        )}
        {(profile?.subAreas.length ?? 0) > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {profile!.subAreas.map((s) => (
              <span key={s.name} className="rounded-md bg-secondary px-2 py-1 text-[11px] text-muted-foreground">
                {s.name} <span className="font-medium text-foreground tabular-nums">{percent(s.dropoutRate)}</span>
              </span>
            ))}
          </div>
        )}
        <p className="mt-3 text-[10px] leading-snug text-muted-foreground/60">Source: LKI-SSM casefile.</p>
      </section>

      <section>
        <p className="label-micro">Dominant factors · UIDAI / NITI</p>
        {(["state", "district"] as const).map((m) => {
          const rows = byMethod(m);
          if (!rows.length) return null;
          const check = checks.find((c) => c.method === m);
          return (
            <div key={m} className="mt-2.5">
              <p className="text-[10px] font-medium tracking-wide text-muted-foreground/70 uppercase">{METHOD_TITLE[m]}</p>
              <ul className="mt-1 space-y-1.5">
                {rows.map((f, i) => (
                  <li key={i} className="flex items-start justify-between gap-3 text-[12px] leading-snug">
                    <span className="text-foreground/90">
                      {f.factor}
                      {f.area.toLowerCase() !== name.toLowerCase() && (
                        <span className="text-muted-foreground"> · {f.area}</span>
                      )}
                    </span>
                    <span className="shrink-0 rounded bg-secondary px-1.5 py-0.5 text-[11px] tabular-nums text-muted-foreground">
                      {f.value}
                    </span>
                  </li>
                ))}
              </ul>
              {check && (
                <div className="mt-2 rounded-lg border border-panel-border bg-secondary/30 px-2.5 py-2">
                  <span className={"rounded-full px-2 py-0.5 text-[10px] font-medium " + VERDICT_STYLE[check.verdict].className}>
                    {VERDICT_STYLE[check.verdict].label}
                  </span>
                  <p className="mt-1.5 text-[11.5px] leading-snug text-muted-foreground">
                    {check.note}
                    <SourceChips ids={check.sources} sources={sources} />
                  </p>
                </div>
              )}
            </div>
          );
        })}
        {(profile?.nitiFactors.length ?? 0) === 0 && (
          <p className="mt-2 text-[12px] text-muted-foreground">No UIDAI/NITI factor rows for this district.</p>
        )}
        <p className="mt-3 text-[10px] leading-snug text-muted-foreground/60">
          The two methods are shown separately and never blended; values are as published in each file.
        </p>
      </section>
    </div>
  );
}

type DistrictTab = "numbers" | "reasons" | "media";
const DISTRICT_TABS: { id: DistrictTab; label: string }[] = [
  { id: "reasons", label: "On the ground" },
  { id: "numbers", label: "Numbers" },
  { id: "media", label: "Media & sources" },
];

function DistrictBody({
  districtId,
  profile,
  name,
  allRates,
}: {
  districtId: string;
  profile: DistrictProfile | undefined;
  name: string;
  allRates: number[];
}) {
  const [tab, setTab] = useState<DistrictTab>("reasons");
  return (
    <div>
      <div className="mb-4 flex gap-1 rounded-lg bg-secondary/60 p-1" role="tablist">
        {DISTRICT_TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => setTab(t.id)}
            className={
              "flex-1 rounded-md px-2.5 py-1.5 text-[11.5px] font-medium transition-colors " +
              (tab === t.id ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground")
            }
          >
            {t.label}
          </button>
        ))}
      </div>
      {tab === "numbers" ? (
        <DistrictNumbers districtId={districtId} profile={profile} name={name} allRates={allRates} />
      ) : (
        <ResearchState districtId={districtId} name={name} view={tab} />
      )}
    </div>
  );
}

function RegionBody({ regionId, byId, names }: { regionId: string; byId: Record<string, DistrictProfile>; names: Record<string, string> }) {
  const focusDistrict = useExplorerStore((s) => s.focusDistrict);
  const ids = Object.values(byId)
    .filter((d) => d.regionId === regionId)
    .map((d) => d.districtId);
  const rates = ids.map((id) => byId[id]?.dropoutRate).filter((r): r is number => typeof r === "number");
  const avg = rates.length ? rates.reduce((a, b) => a + b, 0) / rates.length : null;
  const hi = ids.reduce<string | null>((best, id) => ((byId[id]?.dropoutRate ?? -1) > (byId[best ?? ""]?.dropoutRate ?? -1) ? id : best), null);
  const lo = ids.reduce<string | null>((best, id) => {
    const r = byId[id]?.dropoutRate;
    if (r == null) return best;
    return best === null || r < (byId[best]?.dropoutRate ?? Infinity) ? id : best;
  }, null);

  return (
    <div className="grid gap-5 @lg:grid-cols-2">
      <section>
        <p className="label-micro">Average dropout rate · {ids.length} districts</p>
        <p className="mt-1.5 text-[34px] leading-none font-semibold tracking-tight text-foreground">{avg !== null ? percent(avg) : "—"}</p>
        <p className="mt-2 text-[11px] leading-snug text-muted-foreground">
          {hi && `Highest: ${names[hi] ?? hi} ${percent(byId[hi]?.dropoutRate ?? 0)}`}
          {hi && lo && " · "}
          {lo && `Lowest: ${names[lo] ?? lo} ${percent(byId[lo]?.dropoutRate ?? 0)}`}
        </p>
      </section>
      <section>
        <p className="label-micro">Districts — click to zoom in</p>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {ids.map((id) => (
            <button
              key={id}
              type="button"
              onClick={() => focusDistrict(id, regionId)}
              className="rounded-md bg-secondary px-2 py-1 text-[11px] text-muted-foreground transition-colors hover:text-foreground"
            >
              {names[id] ?? id}
              {byId[id]?.dropoutRate != null && (
                <span className="ml-1.5 tabular-nums text-foreground/80">{percent(byId[id]!.dropoutRate!)}</span>
              )}
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}

export function MapDetailSheet() {
  const regionId = useExplorerStore((s) => s.regionId);
  const districtId = useExplorerStore((s) => s.districtId);
  const focusRegion = useExplorerStore((s) => s.focusRegion);
  const resetFocus = useExplorerStore((s) => s.resetFocus);
  const { byId } = useDistrictProfiles();
  const { geo } = useDistrictGeo();

  const names = useMemo(() => {
    const out: Record<string, string> = {};
    for (const [id, d] of Object.entries(geo?.districts ?? {})) out[id] = d.name;
    return out;
  }, [geo]);
  const allRates = useMemo(
    () => Object.values(byId).map((d) => d.dropoutRate).filter((r): r is number => typeof r === "number"),
    [byId],
  );

  if (!regionId && !districtId) return null;
  const rid = regionId ?? byId[districtId ?? ""]?.regionId ?? "";
  const meta = regionMeta(rid);
  const title = districtId ? (names[districtId] ?? districtId) : (meta?.name ?? rid);

  return (
    <div
      key={`${rid}-${districtId ?? ""}`}
      className="panel-surface @container pointer-events-auto absolute inset-x-3 bottom-3 z-10 flex max-h-[46%] flex-col overflow-hidden rounded-xl shadow-2xl animate-in fade-in slide-in-from-bottom-3 duration-300"
    >
      <header className="flex items-start gap-3 border-b border-panel-border px-4 py-3">
        <span className="mt-1 h-8 w-1 shrink-0 rounded-full" style={{ backgroundColor: rgbaCss(regionColor(rid)) }} aria-hidden />
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-[15px] font-semibold text-foreground">{title}</h2>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-muted-foreground">
            {districtId && meta && (
              <button type="button" onClick={() => focusRegion(rid)} className="underline-offset-2 hover:text-foreground hover:underline">
                {meta.shortName} region
              </button>
            )}
            {!districtId && <span>Persona region</span>}
          </div>
        </div>
        <button
          type="button"
          onClick={resetFocus}
          aria-label="Close and zoom out"
          className="flex size-7 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
        >
          <X className="size-4" />
        </button>
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4 [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-border">
        {districtId ? (
          <DistrictBody key={districtId} districtId={districtId} profile={byId[districtId]} name={title} allRates={allRates} />
        ) : (
          <RegionBody regionId={rid} byId={byId} names={names} />
        )}
        <div className="mt-5 border-t border-panel-border pt-4">
          <p className="label-micro mb-2">Who lives here</p>
          <PersonaButtons regionId={rid} />
        </div>
      </div>
    </div>
  );
}
