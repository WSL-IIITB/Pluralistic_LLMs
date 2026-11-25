/**
 * The Personas tab: a man and a woman for every Karnataka district (the persona library).
 * Pick a region, a district and a person; their card shows who they are -- work, family,
 * a day in their life, their world -- and nothing about the dropout study. Ask them any
 * question side by side with a persona-free answer on the same evidence, fine-tune them,
 * or create a new persona anywhere. For the 12 researched personas the study's own lens on
 * their household (school pressures, the district's NITI numbers) stays available in a
 * separate, clearly labelled section.
 */

import { ChevronDown, Plus, SlidersHorizontal } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { PersonaAsk } from "@/components/persona/PersonaAsk";
import { PersonaEditor } from "@/components/persona/PersonaEditor";
import { PersonaIntro } from "@/components/persona/PersonaIntro";
import { StuntingDistrictView } from "@/components/stunting/StuntingViews";
import { useTheme } from "@/lib/theme";
import {
  formatFactorValue,
  KARNATAKA_REGIONS,
  LIBRARY_LIVE,
  personaCard,
  rgbaCss,
  studyLens,
  stuntingLens,
  useStunting,
  useDistrictProfiles,
  useDistrictResearch,
  useExplorerStore,
  useNitiPrescriptive,
  usePersonaLibrary,
  useWorldviewStore,
  type Gender,
  type LibraryPersona,
  type LibraryPersonaSummary,
  type PersonaCard,
  type PersonaStudyLens,
  type PersonaStuntingLens,
  type RGBAColor,
} from "@/lib/worldview";

/** Region colour for TEXT: darkened on the light theme so it stays readable (fills use the raw colour). */
function useInk(color: RGBAColor): string {
  const theme = useTheme();
  const k = theme === "light" ? 0.58 : 1;
  return `rgb(${Math.round(color[0] * k)} ${Math.round(color[1] * k)} ${Math.round(color[2] * k)})`;
}

const SOURCE_BADGE: Record<string, { label: string; title: string }> = {
  curated: { label: "Researched", title: "Hand-researched from cited public sources" },
  generated: {
    label: "Generated",
    title: "Written by an LLM from the region's research brief; not source-verified",
  },
  custom: { label: "Your persona", title: "Created or fine-tuned in this dashboard" },
  draft: { label: "Draft", title: "Not saved yet" },
};

function personaEmoji(p: LibraryPersonaSummary): string {
  if (p.emoji) return p.emoji;
  if (p.curatedRef)
    return personaCard(p.curatedRef.regionId, p.curatedRef.personaId)?.emoji ?? "👤";
  return p.gender === "female" ? "👩" : "👨";
}

function personaLabel(p: LibraryPersonaSummary): string {
  if (p.curatedRef)
    return personaCard(p.curatedRef.regionId, p.curatedRef.personaId)?.name ?? p.name;
  return p.name;
}

// ── Picker: region -> district -> persona ──────────────────────────────────

function Picker({ onCreate }: { onCreate: (districtId: string, gender: Gender) => void }) {
  const { districts, personas, status } = usePersonaLibrary();
  const selectedId = useExplorerStore((s) => s.libraryPersonaId);
  const select = useExplorerStore((s) => s.selectLibraryPersona);
  const selected = personas.find((p) => p.id === selectedId);
  const [regionId, setRegionId] = useState(selected?.regionId ?? KARNATAKA_REGIONS[0]!.id);
  const [districtId, setDistrictId] = useState<string | null>(selected?.districtId ?? null);

  // Follow selections made elsewhere (the map's "Meet the man/woman" buttons).
  useEffect(() => {
    if (selected) {
      setRegionId(selected.regionId);
      setDistrictId(selected.districtId);
    }
  }, [selected]);

  const region = KARNATAKA_REGIONS.find((r) => r.id === regionId)!;
  const regionDistricts = districts.filter((d) => d.regionId === regionId);
  const count = (did: string) => personas.filter((p) => p.districtId === did).length;
  const here = personas.filter((p) => p.districtId === districtId);

  if (status === "error")
    return (
      <p className="text-[12px] text-muted-foreground">The persona library could not be loaded.</p>
    );

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-1.5" role="tablist" aria-label="Region">
        {KARNATAKA_REGIONS.map((r) => {
          const on = r.id === regionId;
          return (
            <button
              key={r.id}
              type="button"
              role="tab"
              aria-selected={on}
              onClick={() => {
                setRegionId(r.id);
                setDistrictId(null);
              }}
              className={
                "flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[11.5px] font-medium transition-all " +
                (on
                  ? "text-foreground"
                  : "border-panel-border text-muted-foreground hover:text-foreground")
              }
              style={
                on
                  ? { backgroundColor: rgbaCss(r.color, 0.25), borderColor: rgbaCss(r.color, 0.7) }
                  : undefined
              }
            >
              <span
                className="size-1.5 rounded-full"
                style={{ backgroundColor: rgbaCss(r.color) }}
                aria-hidden
              />
              {r.shortName}
            </button>
          );
        })}
      </div>

      <div className="flex flex-wrap gap-1.5" role="tablist" aria-label="District">
        {regionDistricts.map((d) => {
          const on = d.districtId === districtId;
          const n = count(d.districtId);
          return (
            <button
              key={d.districtId}
              type="button"
              role="tab"
              aria-selected={on}
              onClick={() => setDistrictId(d.districtId)}
              className={
                "rounded-lg border px-2.5 py-1 text-[11.5px] transition-colors " +
                (on
                  ? "border-foreground/40 bg-secondary text-foreground"
                  : "border-panel-border text-muted-foreground hover:text-foreground")
              }
            >
              {d.name}
              <span className="ml-1.5 text-[10px] tabular-nums opacity-70">{n}</span>
            </button>
          );
        })}
      </div>

      {districtId ? (
        <div className="grid gap-2 @xl:grid-cols-2">
          {(["male", "female"] as const).map((g) => {
            const people = here.filter((p) => p.gender === g);
            return (
              <div key={g} className="rounded-xl border border-panel-border bg-secondary/30 p-2">
                <p className="mb-1.5 px-1 text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
                  {g === "female" ? "Women" : "Men"}
                </p>
                <div className="space-y-1">
                  {people.map((p) => {
                    const active = p.id === selectedId;
                    return (
                      <button
                        key={p.id}
                        type="button"
                        onClick={() => select(p.id, p.districtId, p.regionId)}
                        className={
                          "flex w-full items-center gap-2.5 rounded-lg px-2 py-1.5 text-left transition-colors " +
                          (active ? "bg-background/80" : "hover:bg-background/50")
                        }
                        style={
                          active
                            ? { boxShadow: `inset 0 0 0 1.5px ${rgbaCss(region.color, 0.8)}` }
                            : undefined
                        }
                      >
                        <span
                          className="flex size-8 shrink-0 items-center justify-center rounded-full text-lg"
                          style={{ backgroundColor: rgbaCss(region.color, 0.25) }}
                        >
                          {personaEmoji(p)}
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-[12.5px] font-medium text-foreground">
                            {personaLabel(p)}
                          </span>
                          <span className="block truncate text-[10.5px] text-muted-foreground">
                            {SOURCE_BADGE[p.source]?.label}
                            {p.role ? ` · ${p.role}` : ""}
                          </span>
                        </span>
                      </button>
                    );
                  })}
                  {people.length === 0 && (
                    <p className="px-2 py-1.5 text-[11.5px] text-muted-foreground">
                      No persona here yet.
                    </p>
                  )}
                  {LIBRARY_LIVE && (
                    <button
                      type="button"
                      onClick={() => onCreate(districtId, g)}
                      className="flex w-full items-center gap-1.5 rounded-lg px-2 py-1.5 text-[11.5px] text-muted-foreground transition-colors hover:bg-background/50 hover:text-foreground"
                    >
                      <Plus className="size-3.5" /> Create a {g === "female" ? "woman" : "man"} here
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <p className="text-[11.5px] text-muted-foreground">
          Choose a district to meet the people who live there.
        </p>
      )}
    </div>
  );
}

// ── Card sections ───────────────────────────────────────────────────────────

function Section({
  title,
  children,
  className = "",
}: {
  title: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={className}>
      <p className="label-micro mb-2.5">{title}</p>
      {children}
    </section>
  );
}

function Hero({
  card,
  color,
  regionName,
  genderLabel,
}: {
  card: PersonaCard;
  color: RGBAColor;
  regionName: string;
  genderLabel: string;
}) {
  return (
    <div
      className="relative overflow-hidden rounded-2xl border border-panel-border p-5"
      style={{
        background: `linear-gradient(135deg, ${rgbaCss(color, 0.22)}, ${rgbaCss(color, 0.04)} 70%)`,
      }}
    >
      <div className="flex items-start gap-4">
        <div
          className="flex size-20 shrink-0 items-center justify-center rounded-full text-[44px] leading-none shadow-lg ring-4"
          style={{
            backgroundColor: rgbaCss(color, 0.35),
            ["--tw-ring-color" as string]: rgbaCss(color, 0.55),
          }}
          aria-hidden
        >
          {card.emoji}
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
            {regionName} · {genderLabel} · composite persona
          </p>
          <h2 className="mt-1 text-xl leading-tight font-semibold text-foreground">
            {card.name}
            <span className="ml-2 text-sm font-normal text-muted-foreground">{card.ageLabel}</span>
          </h2>
          <p className="mt-0.5 text-[13px] text-foreground/90">
            {card.role} · {card.place}
          </p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {card.community && (
              <span className="rounded-full bg-background/50 px-2.5 py-0.5 text-[11px] text-foreground">
                {card.community}
              </span>
            )}
          </div>
        </div>
      </div>
      <p className="mt-4 text-[13px] leading-relaxed text-foreground/90 italic">{card.tagline}</p>
    </div>
  );
}

function Household({ card, color }: { card: PersonaCard; color: RGBAColor }) {
  return (
    <div className="flex flex-wrap gap-2">
      <div
        className="flex items-center gap-2 rounded-full py-1 pr-3.5 pl-1.5 text-[12px] font-medium text-foreground"
        style={{ backgroundColor: rgbaCss(color, 0.3) }}
      >
        <span className="text-lg leading-none">{card.emoji}</span>
        {card.name.startsWith("The ") ? "Them" : card.name.split(" ")[0]}
      </div>
      {card.household.map((m, i) => (
        <div
          key={i}
          className="flex items-center gap-2 rounded-full bg-secondary py-1 pr-3.5 pl-1.5 text-[12px] text-muted-foreground"
        >
          <span className="text-lg leading-none">{m.emoji}</span>
          {m.who}
        </div>
      ))}
    </div>
  );
}

function Vitals({ card, color }: { card: PersonaCard; color: RGBAColor }) {
  const ink = useInk(color);
  return (
    <div className="grid grid-cols-2 gap-2 @xl:grid-cols-4">
      {card.vitals.map((v) => (
        <div
          key={v.label}
          className="rounded-xl border border-panel-border bg-secondary/40 px-3 py-2.5"
        >
          <p
            className="text-[15px] leading-tight font-semibold text-foreground"
            style={{ color: ink }}
          >
            {v.value}
          </p>
          <p className="mt-0.5 text-[10px] tracking-wide text-muted-foreground uppercase">
            {v.label}
          </p>
        </div>
      ))}
    </div>
  );
}

function DayInLife({ card, color }: { card: PersonaCard; color: RGBAColor }) {
  const ink = useInk(color);
  return (
    <ol className="relative ml-3.5 space-y-3.5 border-l border-border pl-6">
      {card.dayInLife.map((b, i) => (
        <li
          key={i}
          className="relative animate-in fade-in slide-in-from-left-2 fill-mode-both"
          style={{ animationDelay: `${i * 70}ms` }}
        >
          <span
            className="absolute top-0 -left-[2.35rem] flex size-8 items-center justify-center rounded-full bg-background text-base ring-2"
            style={{ ["--tw-ring-color" as string]: rgbaCss(color, 0.6) }}
          >
            {b.emoji}
          </span>
          <p className="text-[11px] font-semibold tracking-wide uppercase" style={{ color: ink }}>
            {b.when}
          </p>
          <p className="text-[13px] leading-snug text-foreground/90">{b.text}</p>
        </li>
      ))}
    </ol>
  );
}

function TopicExplorer({
  card,
  color,
  fullText,
}: {
  card: PersonaCard;
  color: RGBAColor;
  fullText: Record<string, string>;
}) {
  const ink = useInk(color);
  const [active, setActive] = useState(card.topics[0]?.key ?? "");
  const [showFull, setShowFull] = useState(false);
  const topic = card.topics.find((t) => t.key === active) ?? card.topics[0];
  useEffect(() => {
    setShowFull(false);
  }, [active]);
  if (!topic) return null;
  const full = fullText[topic.key];

  return (
    <div>
      <div className="flex flex-wrap gap-1.5" role="tablist" aria-label="Aspects of life">
        {card.topics.map((t) => {
          const on = t.key === topic.key;
          return (
            <button
              key={t.key}
              type="button"
              role="tab"
              aria-selected={on}
              onClick={() => setActive(t.key)}
              className={
                "flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[12px] font-medium transition-all " +
                (on
                  ? "text-foreground"
                  : "border-panel-border bg-secondary/40 text-muted-foreground hover:text-foreground")
              }
              style={
                on
                  ? { backgroundColor: rgbaCss(color, 0.25), borderColor: rgbaCss(color, 0.7) }
                  : undefined
              }
            >
              <span className="text-sm leading-none">{t.emoji}</span>
              {t.label}
            </button>
          );
        })}
      </div>

      <div
        key={topic.key}
        className="mt-3 rounded-2xl border border-panel-border bg-secondary/30 p-4 animate-in fade-in zoom-in-95 duration-300"
      >
        <p className="text-[14px] leading-snug font-semibold text-foreground">{topic.headline}</p>
        <ul className="mt-3 space-y-2">
          {topic.points.map((pt, i) => (
            <li key={i} className="flex gap-2.5 text-[13px] leading-snug text-foreground/85">
              <span
                className="mt-[7px] size-1.5 shrink-0 rounded-full"
                style={{ backgroundColor: rgbaCss(color) }}
                aria-hidden
              />
              {pt}
            </li>
          ))}
        </ul>
        {topic.stat && (
          <div className="mt-4 flex items-center gap-3 rounded-xl bg-background/50 px-3.5 py-3">
            <span
              className="text-[26px] leading-none font-semibold tabular-nums"
              style={{ color: ink }}
            >
              {topic.stat.value}
            </span>
            <span className="text-[12px] leading-snug text-muted-foreground">
              {topic.stat.label}
            </span>
          </div>
        )}
        {full && (
          <>
            <button
              type="button"
              onClick={() => setShowFull((v) => !v)}
              aria-expanded={showFull}
              className="label-micro mt-3.5 flex items-center gap-1.5 transition-colors hover:text-foreground"
            >
              <ChevronDown
                className={`size-3 transition-transform ${showFull ? "" : "-rotate-90"}`}
                aria-hidden
              />
              Read the full profile
            </button>
            {showFull && (
              <div className="mt-2.5 space-y-2.5 text-[12.5px] leading-relaxed text-muted-foreground">
                {full
                  .replace(/\[S\d+\]/g, "")
                  .split(/\n{2,}/)
                  .map((para, i) => (
                    <p key={i}>{para}</p>
                  ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

/** The region's two UIDAI/NITI dominant factors, how each could reach this persona, and what the research says for their district. */
function DominantFactors({
  card,
  lens,
  regionId,
}: {
  card: PersonaCard;
  lens: PersonaStudyLens;
  regionId: string;
}) {
  const fx = lens.factorEffects;
  const { byId } = useDistrictProfiles();
  const research = useDistrictResearch(fx?.districtId ?? null);
  const focusDistrict = useExplorerStore((s) => s.focusDistrict);
  if (!fx) return null;

  const profile = byId[fx.districtId];
  const districtName = research.status === "ready" ? research.data.name : card.place;
  const why = research.status === "ready" ? research.data.dominantFactorWhy : undefined;
  const blocks = [
    { method: "state", title: "State-level factor", line: fx.sanitation },
    { method: "district", title: "District-level factor", line: fx.district },
  ] as const;

  return (
    <div className="space-y-2.5">
      <div className="grid gap-2.5 @xl:grid-cols-2">
        {blocks.map((b) => {
          const rows = (profile?.nitiFactors ?? []).filter((f) => f.method === b.method);
          const entries = why?.entries.filter((e) => e.method === b.method) ?? [];
          return (
            <div
              key={b.method}
              className="rounded-xl border border-panel-border bg-secondary/30 p-3.5"
            >
              <p className="label-micro">{b.title}</p>
              {rows[0] && (
                <p className="mt-1 text-[12.5px] font-semibold text-foreground">{rows[0].factor}</p>
              )}
              {rows.length > 0 && (
                <p className="mt-1 text-[11px] text-muted-foreground">
                  {districtName}:{" "}
                  {rows
                    .map(
                      (f) =>
                        `${f.area.toLowerCase() === districtName.toLowerCase() ? "" : `${f.area} `}${f.value}`,
                    )
                    .join(" · ")}
                </p>
              )}
              <p className="mt-2 text-[12px] leading-snug text-foreground/90">{b.line}</p>
              {entries.find((x) => x.mechanism) && (
                <div className="mt-2.5 border-t border-panel-border pt-2">
                  <p className="text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
                    How it could work in {districtName}
                  </p>
                  <p className="mt-1 text-[11px] leading-snug text-muted-foreground">
                    {entries.find((x) => x.mechanism)!.mechanism}
                  </p>
                </div>
              )}
            </div>
          );
        })}
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="max-w-[560px] text-[10.5px] leading-snug text-muted-foreground">
          The sentences above are an interpretation of this persona&apos;s profile, written
          conditionally: the persona data does not measure these factors.
        </p>
        <button
          type="button"
          onClick={() => focusDistrict(fx.districtId, regionId)}
          className="rounded-full border border-panel-border px-3 py-1.5 text-[11px] font-medium text-foreground transition-colors hover:bg-secondary"
        >
          See the proof for {districtName} on the map
        </button>
      </div>
    </div>
  );
}

/** The persona's district through the NITI prescriptive model: its top three changes and where it lags, each with
 * how it would reach this household. Numbers come live from niti-prescriptive.json; the sentences are the card's. */
function DistrictInNumbers({
  studyLens: sl,
  regionId,
  color,
}: {
  studyLens: PersonaStudyLens;
  regionId: string;
  color: RGBAColor;
}) {
  const data = useNitiPrescriptive();
  const focusDistrict = useExplorerStore((s) => s.focusDistrict);
  const ink = useInk(color);
  const lens = sl.dataLens;
  const did = sl.factorEffects?.districtId;
  if (!lens || !did) return null;
  if (!data)
    return (
      <p className="text-[12px] text-muted-foreground">
        {data === undefined
          ? "Loading the district's numbers…"
          : "The NITI file could not be loaded."}
      </p>
    );
  const district = data.districts[did];
  const area = district?.areas.find((a) => a.area === lens.area);
  if (!district || !area) return null;
  const info = Object.fromEntries(data.factors.map((f) => [f.name, f]));
  const row = (name: string) => area.factors.find((f) => f.name === name);
  const label = area.area === district.areas[0]?.area ? district.name : area.area;
  const lag = row(lens.lag.factor);

  return (
    <div className="space-y-2.5">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <p className="text-[12.5px] font-semibold text-foreground">{label}</p>
        {area.dropout2023_24 != null && (
          <p className="text-[11.5px] text-muted-foreground">
            secondary dropout 2023-24{" "}
            <span className="font-semibold tabular-nums" style={{ color: ink }}>
              {area.dropout2023_24.toFixed(1)}%
            </span>
            {area.dropout2024_25 != null && <> · 2024-25 file {area.dropout2024_25.toFixed(1)}%</>}
          </p>
        )}
      </div>
      <p className="text-[11px] text-muted-foreground">
        The three changes the NITI model ranks highest for this district, and what each would mean
        for this household:
      </p>
      <div className="grid gap-2 @xl:grid-cols-3">
        {lens.changes.map((c, i) => {
          const f = row(c.factor);
          return (
            <div
              key={c.factor}
              className="rounded-xl border border-panel-border bg-secondary/30 p-3"
            >
              <p className="text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
                Change {i + 1}
              </p>
              <p className="mt-0.5 text-[12.5px] font-semibold text-foreground">
                {info[c.factor]?.short ?? c.factor}
              </p>
              {f && (
                <p className="text-[11px] text-muted-foreground tabular-nums">
                  {formatFactorValue(c.factor, f.value)} · rank {f.rank} of 35
                </p>
              )}
              <p
                className="mt-2 border-l-2 pl-2.5 text-[11.5px] leading-snug text-foreground/90"
                style={{ borderColor: rgbaCss(color, 0.75) }}
              >
                {c.effect}
              </p>
            </div>
          );
        })}
      </div>
      {lag && (
        <div className="rounded-xl border border-dashed border-panel-border px-3 py-2.5">
          <p className="text-[11.5px] text-foreground/90">
            <span className="font-semibold">Where the district lags most: </span>
            {info[lens.lag.factor]?.short ?? lens.lag.factor}{" "}
            <span className="text-muted-foreground tabular-nums">
              ({formatFactorValue(lens.lag.factor, lag.value)}, rank {lag.rank} of 35)
            </span>
          </p>
          <p className="mt-1 text-[11.5px] leading-snug text-muted-foreground">{lens.lag.effect}</p>
        </div>
      )}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="max-w-[560px] text-[10.5px] leading-snug text-muted-foreground">
          Numbers from the NITI team&apos;s prescriptive model (UDISE 2023-24, NFHS-5). The
          sentences interpret this persona&apos;s card in the light of those numbers; they are not
          data.
        </p>
        <button
          type="button"
          onClick={() => focusDistrict(did, regionId, "numbers")}
          className="rounded-full border border-panel-border px-3 py-1.5 text-[11px] font-medium text-foreground transition-colors hover:bg-secondary"
        >
          Full district profile on the map
        </button>
      </div>
    </div>
  );
}

function SchoolPressures({ lens, color }: { lens: PersonaStudyLens; color: RGBAColor }) {
  return (
    <div className="grid gap-2 @xl:grid-cols-2">
      {lens.schoolPressures.map((p, i) => (
        <div
          key={i}
          className="flex gap-3 rounded-xl border border-panel-border bg-secondary/30 p-3 transition-colors hover:bg-secondary/60 animate-in fade-in zoom-in-95 fill-mode-both"
          style={{ animationDelay: `${i * 60}ms` }}
        >
          <span
            className="flex size-9 shrink-0 items-center justify-center rounded-lg text-lg"
            style={{ backgroundColor: rgbaCss(color, 0.22) }}
          >
            {p.emoji}
          </span>
          <div className="min-w-0">
            <p className="text-[12.5px] font-semibold text-foreground">{p.label}</p>
            <p className="mt-0.5 text-[12px] leading-snug text-muted-foreground">{p.detail}</p>
            {lens.factorEffects?.pressures[i] && (
              <p
                className="mt-2 border-l-2 pl-2.5 text-[11.5px] leading-snug text-foreground/90"
                style={{ borderColor: rgbaCss(color, 0.75) }}
              >
                <span className="font-semibold">What it does: </span>
                {lens.factorEffects.pressures[i]}
              </p>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

function TheirAnswer({
  regionId,
  personaId,
  name,
}: {
  regionId: string;
  personaId: string;
  name: string;
}) {
  const answer = useWorldviewStore((s) => s.answer);
  const query = useWorldviewStore((s) => s.query);
  const segs = answer.filter((a) => a.regionId === regionId && a.personaId === personaId);
  const tldr = segs.find((s) => s.kind === "tldr");
  const rest = segs.filter((s) => s !== tldr);

  if (segs.length === 0) {
    return (
      <p className="rounded-xl border border-dashed border-panel-border px-4 py-3 text-[12px] leading-snug text-muted-foreground">
        Run a query on the Map tab to hear how {name.replace(/^The /, "the ")} would answer it.
      </p>
    );
  }
  return (
    <div className="rounded-2xl border border-panel-border bg-secondary/30 p-4">
      {query && <p className="mb-2 text-[11px] text-muted-foreground">On “{query}”</p>}
      {tldr && (
        <p className="text-[13.5px] leading-snug font-semibold text-foreground">{tldr.text}</p>
      )}
      <div className="mt-2 space-y-2 text-[12.5px] leading-relaxed text-muted-foreground">
        {rest.map((s, i) => (
          <p key={i}>{s.text}</p>
        ))}
      </div>
    </div>
  );
}

// ── Panel ───────────────────────────────────────────────────────────────────

/** The dropout study's interpretation of a researched persona's household -- not part of the persona. */
function StudyLensSection({
  card,
  lens,
  regionId,
  color,
}: {
  card: PersonaCard;
  lens: PersonaStudyLens;
  regionId: string;
  color: RGBAColor;
}) {
  const [open, setOpen] = useState(false);
  return (
    <section className="rounded-2xl border border-dashed border-panel-border p-4">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-start gap-2 text-left"
      >
        <ChevronDown
          className={`mt-0.5 size-3.5 shrink-0 transition-transform ${open ? "" : "-rotate-90"}`}
          aria-hidden
        />
        <span>
          <span className="label-micro block">
            Study lens · school dropout (separate from the persona)
          </span>
          <span className="mt-1 block text-[11.5px] leading-snug text-muted-foreground">
            How the dropout study reads this household: what could pull their children out of
            school, and their district&apos;s UIDAI/NITI factors. The persona above knows none of
            this; it is the data side.
          </span>
        </span>
      </button>
      {open && (
        <div className="mt-4 space-y-6">
          <Section title="What could pull kids out of school here">
            <SchoolPressures lens={lens} color={color} />
          </Section>
          {lens.dataLens && (
            <Section title="Their district in numbers">
              <DistrictInNumbers studyLens={lens} regionId={regionId} color={color} />
            </Section>
          )}
          {lens.factorEffects && (
            <Section title="How the dominant factors could reach them">
              <DominantFactors card={card} lens={lens} regionId={regionId} />
            </Section>
          )}
        </div>
      )}
    </section>
  );
}

/** The stunting study's numbers for the persona's district -- data, shown beside the persona, never part of it. */
function StuntingDataSection({
  districtId,
  districtName,
  lens,
  color,
}: {
  districtId: string;
  districtName: string;
  lens: PersonaStuntingLens | null;
  color: RGBAColor;
}) {
  const data = useStunting();
  const info = Object.fromEntries((data?.factors ?? []).map((f) => [f.name, f]));
  const [open, setOpen] = useState(false);
  return (
    <section className="rounded-2xl border border-dashed border-panel-border p-4">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-start gap-2 text-left"
      >
        <ChevronDown
          className={`mt-0.5 size-3.5 shrink-0 transition-transform ${open ? "" : "-rotate-90"}`}
          aria-hidden
        />
        <span>
          <span className="label-micro block">
            District data · under-5 stunting (separate from the persona)
          </span>
          <span className="mt-1 block text-[11.5px] leading-snug text-muted-foreground">
            {districtName}&apos;s stunting figures and NITI&apos;s provisional model. The persona
            knows none of this; it is the data side, and the Ask above hands it to both answers as
            evidence.
          </span>
        </span>
      </button>
      {open && (
        <div className="mt-4">
          {lens?.changes && lens.changes.length > 0 && (
            <div className="mb-5">
              <p className="label-micro">
                How the district&apos;s top factors could reach this household
              </p>
              {lens.underFive && (
                <p className="mt-1 text-[11.5px] text-muted-foreground">{lens.underFive}</p>
              )}
              <div className="mt-2 grid gap-2 @xl:grid-cols-3">
                {lens.changes.map((c) => (
                  <div
                    key={c.factor}
                    className="rounded-xl border border-panel-border bg-secondary/30 p-3"
                  >
                    <p className="text-[12px] font-semibold text-foreground">
                      {info[c.factor]?.short ?? c.factor}
                    </p>
                    <p
                      className="mt-1.5 border-l-2 pl-2.5 text-[11.5px] leading-snug text-foreground/90"
                      style={{ borderColor: rgbaCss(color, 0.75) }}
                    >
                      {c.effect}
                    </p>
                  </div>
                ))}
              </div>
              <p className="mt-1.5 text-[10.5px] text-muted-foreground">
                An interpretation of the persona&apos;s card in the light of the model, written
                conditionally; not data.
              </p>
            </div>
          )}
          <StuntingDistrictView districtId={districtId} compact />
        </div>
      )}
    </section>
  );
}

function PersonaView({ persona, onFineTune }: { persona: LibraryPersona; onFineTune: () => void }) {
  const ref = persona.curatedRef ?? null;
  const card = persona.card ?? (ref ? personaCard(ref.regionId, ref.personaId) : null);
  const region = KARNATAKA_REGIONS.find((r) => r.id === persona.regionId);
  const lens = ref ? studyLens(ref.regionId, ref.personaId) : null;
  const [showDescription, setShowDescription] = useState(false);
  const anchor = `persona-card-${persona.id}`;
  const topic = useExplorerStore((s) => s.topic);

  if (!card || !region) {
    return (
      <p className="py-8 text-center text-[13px] text-muted-foreground">
        No card available for this persona.
      </p>
    );
  }
  const fullText: Record<string, string> = {};
  for (const t of persona.topics) fullText[t.key] = t.profile;
  const genderLabel = persona.gender === "female" ? "Woman" : "Man";
  const badge = SOURCE_BADGE[persona.source];

  return (
    <div
      key={persona.id}
      className="space-y-6 animate-in fade-in slide-in-from-bottom-2 duration-300"
    >
      {card.intro && ref ? (
        <PersonaIntro
          key={`intro-${persona.id}`}
          card={card}
          regionId={ref.regionId}
          personaId={ref.personaId}
          color={region.color}
          regionName={region.shortName}
          onExplore={() =>
            document.getElementById(anchor)?.scrollIntoView({ behavior: "smooth", block: "start" })
          }
        />
      ) : (
        <Hero
          card={card}
          color={region.color}
          regionName={`${persona.districtName}, ${region.shortName}`}
          genderLabel={genderLabel}
        />
      )}

      <div className="flex flex-wrap items-center gap-2">
        {badge && (
          <span
            title={badge.title}
            className="rounded-full border border-panel-border px-2.5 py-0.5 text-[10.5px] font-medium text-muted-foreground"
          >
            {badge.label}
          </span>
        )}
        <span className="text-[10.5px] text-muted-foreground">
          {persona.districtName} district · persona {persona.version}
        </span>
        {LIBRARY_LIVE && (
          <button
            type="button"
            onClick={onFineTune}
            className="ml-auto flex items-center gap-1.5 rounded-full border border-panel-border px-3 py-1 text-[11px] font-medium text-foreground transition-colors hover:bg-secondary"
          >
            <SlidersHorizontal className="size-3" />
            {persona.source === "custom" ? "Edit" : "Fine-tune / re-create"}
          </button>
        )}
      </div>

      {persona.definition && (
        <div>
          <button
            type="button"
            onClick={() => setShowDescription((v) => !v)}
            aria-expanded={showDescription}
            className="label-micro flex items-center gap-1.5 transition-colors hover:text-foreground"
          >
            <ChevronDown
              className={`size-3 transition-transform ${showDescription ? "" : "-rotate-90"}`}
              aria-hidden
            />
            Full persona description
          </button>
          {showDescription && (
            <p className="mt-2 text-[12.5px] leading-relaxed text-muted-foreground animate-in fade-in duration-200">
              {persona.definition}
            </p>
          )}
        </div>
      )}

      <div id={anchor} className="scroll-mt-4" />
      {card.household.length > 0 && (
        <Section title="Household">
          <Household card={card} color={region.color} />
        </Section>
      )}
      {card.vitals.length > 0 && (
        <Section title="At a glance">
          <Vitals card={card} color={region.color} />
        </Section>
      )}
      {card.dayInLife.length > 0 && (
        <Section title="A day in their life">
          <DayInLife card={card} color={region.color} />
        </Section>
      )}
      <Section title="Explore their world">
        <TopicExplorer key={persona.id} card={card} color={region.color} fullText={fullText} />
      </Section>
      {card.worries.length > 0 && (
        <Section title="What keeps them up at night">
          <div className="flex flex-wrap gap-2">
            {card.worries.map((w) => (
              <span
                key={w}
                className="rounded-full border border-panel-border bg-secondary/50 px-3 py-1 text-[12px] text-foreground/90"
              >
                {w}
              </span>
            ))}
          </div>
        </Section>
      )}

      <Section title="Ask a question · without and with this persona">
        <PersonaAsk persona={persona} color={region.color} />
      </Section>

      {ref && (
        <Section title="Their answer to your Map query">
          <TheirAnswer regionId={ref.regionId} personaId={ref.personaId} name={card.name} />
        </Section>
      )}

      {topic === "stunting" ? (
        <StuntingDataSection
          districtId={persona.districtId}
          districtName={persona.districtName}
          lens={ref ? stuntingLens(ref.regionId, ref.personaId) : null}
          color={region.color}
        />
      ) : (
        lens &&
        ref && (
          <StudyLensSection card={card} lens={lens} regionId={ref.regionId} color={region.color} />
        )
      )}
    </div>
  );
}

export function PersonasPanel() {
  const { status, personas, load, fetchPersona } = usePersonaLibrary();
  const selectedId = useExplorerStore((s) => s.libraryPersonaId);
  const select = useExplorerStore((s) => s.selectLibraryPersona);
  const selectCurated = useExplorerStore((s) => s.selectPersona);
  const [persona, setPersona] = useState<LibraryPersona | null>(null);
  const [editor, setEditor] = useState<{
    districtId: string;
    gender: Gender;
    base: LibraryPersona | null;
  } | null>(null);

  useEffect(() => {
    void load();
  }, [load]);

  // First visit: open on a persona so the screen is never an empty prompt.
  useEffect(() => {
    if (!selectedId) selectCurated("old-mysuru", "male");
  }, [selectedId, selectCurated]);

  useEffect(() => {
    let alive = true;
    if (!selectedId || status !== "ready") return;
    void fetchPersona(selectedId).then((p) => alive && setPersona(p));
    return () => {
      alive = false;
    };
  }, [selectedId, status, fetchPersona]);

  const total = personas.length;
  const districtsCovered = useMemo(
    () => new Set(personas.map((p) => p.districtId)).size,
    [personas],
  );

  return (
    <div className="panel-surface @container pointer-events-auto flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl">
      <header className="border-b border-panel-border px-5 py-3.5">
        <p className="label-micro">Meet the personas</p>
        <h2 className="mt-1 text-sm font-medium text-foreground">
          A man and a woman for every district
          {status === "ready" && (
            <span className="ml-2 text-[11px] font-normal text-muted-foreground">
              {total} personas in {districtsCovered} of 30 districts
            </span>
          )}
        </h2>
      </header>
      <div className="min-h-0 flex-1 space-y-6 overflow-y-auto px-5 py-4 [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-border">
        <Picker onCreate={(districtId, gender) => setEditor({ districtId, gender, base: null })} />
        {editor && (
          <PersonaEditor
            key={`${editor.base?.id ?? "new"}-${editor.districtId}-${editor.gender}`}
            districtId={editor.districtId}
            gender={editor.gender}
            base={editor.base}
            onClose={() => setEditor(null)}
            onDeleted={() => {
              setEditor(null);
              setPersona(null);
              selectCurated("old-mysuru", "male");
            }}
            onSaved={(p) => {
              setEditor(null);
              setPersona(p);
              select(p.id, p.districtId, p.regionId);
            }}
          />
        )}
        {persona && persona.id === selectedId && (
          <PersonaView
            persona={persona}
            onFineTune={() =>
              setEditor({ districtId: persona.districtId, gender: persona.gender, base: persona })
            }
          />
        )}
        {status === "loading" && (
          <p className="text-[12px] text-muted-foreground">Loading personas…</p>
        )}
      </div>
    </div>
  );
}
