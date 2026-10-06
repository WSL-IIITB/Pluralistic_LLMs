/**
 * The Personas tab: a cast of 12 composite residents (a man and a woman from each
 * of Karnataka's six regions). Pick one and their card comes alive — who they are,
 * who they live with, a day in their life, what shapes each part of their world,
 * what pulls their kids out of school, and (after a run) how they'd answer.
 * The long-form source description stays one click away.
 */

import { ChevronDown } from "lucide-react";
import { useEffect, useState } from "react";

import {
  KARNATAKA_REGIONS,
  personaCard,
  rgbaCss,
  useExplorerStore,
  usePersonaProfile,
  useWorldviewStore,
  type PersonaCard,
  type RGBAColor,
} from "@/lib/worldview";

// ── Cast picker ─────────────────────────────────────────────────────────────

function CastPicker() {
  const persona = useExplorerStore((s) => s.persona);
  const select = useExplorerStore((s) => s.selectPersona);

  return (
    <div className="grid grid-cols-3 gap-2 @2xl:grid-cols-6" role="tablist" aria-label="Choose a persona">
      {KARNATAKA_REGIONS.map((r) => (
        <div key={r.id} className="rounded-xl border border-panel-border bg-secondary/30 p-2">
          <p className="mb-2 flex items-center justify-center gap-1.5 text-center text-[10px] leading-tight font-medium text-muted-foreground">
            <span className="size-1.5 shrink-0 rounded-full" style={{ backgroundColor: rgbaCss(r.color) }} aria-hidden />
            <span className="truncate">{r.shortName}</span>
          </p>
          <div className="flex justify-center gap-1.5">
            {r.personas.map((p) => {
              const card = personaCard(r.id, p.id);
              const active = persona?.regionId === r.id && persona.personaId === p.id;
              return (
                <button
                  key={p.id}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  aria-label={`${card?.name ?? p.label} — ${r.shortName}`}
                  title={`${card?.name ?? p.label} · ${card?.role ?? ""}`}
                  onClick={() => select(r.id, p.id)}
                  className={
                    "flex size-10 items-center justify-center rounded-full text-xl leading-none transition-all duration-200 " +
                    (active ? "scale-110 ring-2 ring-offset-2 ring-offset-background" : "opacity-70 hover:scale-105 hover:opacity-100")
                  }
                  style={{
                    backgroundColor: rgbaCss(r.color, active ? 0.45 : 0.22),
                    ...(active ? ({ "--tw-ring-color": rgbaCss(r.color) } as React.CSSProperties) : {}),
                  }}
                >
                  {card?.emoji ?? "👤"}
                </button>
              );
            })}
          </div>
          <p className="mt-1.5 text-center text-[9px] tracking-wide text-muted-foreground/60 uppercase">♂ · ♀</p>
        </div>
      ))}
    </div>
  );
}

// ── Card sections ───────────────────────────────────────────────────────────

function Section({ title, children, className = "" }: { title: string; children: React.ReactNode; className?: string }) {
  return (
    <section className={className}>
      <p className="label-micro mb-2.5">{title}</p>
      {children}
    </section>
  );
}

function Hero({ card, color, regionName, genderLabel }: { card: PersonaCard; color: RGBAColor; regionName: string; genderLabel: string }) {
  return (
    <div
      className="relative overflow-hidden rounded-2xl border border-panel-border p-5"
      style={{ background: `linear-gradient(135deg, ${rgbaCss(color, 0.22)}, ${rgbaCss(color, 0.04)} 70%)` }}
    >
      <div className="flex items-start gap-4">
        <div
          className="flex size-20 shrink-0 items-center justify-center rounded-full text-[44px] leading-none shadow-lg ring-4"
          style={{ backgroundColor: rgbaCss(color, 0.35), ["--tw-ring-color" as string]: rgbaCss(color, 0.55) }}
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
              <span className="rounded-full bg-background/50 px-2.5 py-0.5 text-[11px] text-foreground">{card.community}</span>
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
      <div className="flex items-center gap-2 rounded-full py-1 pr-3.5 pl-1.5 text-[12px] font-medium text-foreground" style={{ backgroundColor: rgbaCss(color, 0.3) }}>
        <span className="text-lg leading-none">{card.emoji}</span>
        {card.name.startsWith("The ") ? "Them" : card.name.split(" ")[0]}
      </div>
      {card.household.map((m, i) => (
        <div key={i} className="flex items-center gap-2 rounded-full bg-secondary py-1 pr-3.5 pl-1.5 text-[12px] text-muted-foreground">
          <span className="text-lg leading-none">{m.emoji}</span>
          {m.who}
        </div>
      ))}
    </div>
  );
}

function Vitals({ card, color }: { card: PersonaCard; color: RGBAColor }) {
  return (
    <div className="grid grid-cols-2 gap-2 @xl:grid-cols-4">
      {card.vitals.map((v) => (
        <div key={v.label} className="rounded-xl border border-panel-border bg-secondary/40 px-3 py-2.5">
          <p className="text-[15px] leading-tight font-semibold text-foreground" style={{ color: rgbaCss(color) }}>
            {v.value}
          </p>
          <p className="mt-0.5 text-[10px] tracking-wide text-muted-foreground uppercase">{v.label}</p>
        </div>
      ))}
    </div>
  );
}

function DayInLife({ card, color }: { card: PersonaCard; color: RGBAColor }) {
  return (
    <ol className="relative ml-3.5 space-y-3.5 border-l border-border pl-6">
      {card.dayInLife.map((b, i) => (
        <li key={i} className="relative animate-in fade-in slide-in-from-left-2 fill-mode-both" style={{ animationDelay: `${i * 70}ms` }}>
          <span
            className="absolute top-0 -left-[2.35rem] flex size-8 items-center justify-center rounded-full bg-background text-base ring-2"
            style={{ ["--tw-ring-color" as string]: rgbaCss(color, 0.6) }}
          >
            {b.emoji}
          </span>
          <p className="text-[11px] font-semibold tracking-wide uppercase" style={{ color: rgbaCss(color) }}>
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
                (on ? "text-foreground" : "border-panel-border bg-secondary/40 text-muted-foreground hover:text-foreground")
              }
              style={on ? { backgroundColor: rgbaCss(color, 0.25), borderColor: rgbaCss(color, 0.7) } : undefined}
            >
              <span className="text-sm leading-none">{t.emoji}</span>
              {t.label}
            </button>
          );
        })}
      </div>

      <div key={topic.key} className="mt-3 rounded-2xl border border-panel-border bg-secondary/30 p-4 animate-in fade-in zoom-in-95 duration-300">
        <p className="text-[14px] leading-snug font-semibold text-foreground">{topic.headline}</p>
        <ul className="mt-3 space-y-2">
          {topic.points.map((pt, i) => (
            <li key={i} className="flex gap-2.5 text-[13px] leading-snug text-foreground/85">
              <span className="mt-[7px] size-1.5 shrink-0 rounded-full" style={{ backgroundColor: rgbaCss(color) }} aria-hidden />
              {pt}
            </li>
          ))}
        </ul>
        {topic.stat && (
          <div className="mt-4 flex items-center gap-3 rounded-xl bg-background/50 px-3.5 py-3">
            <span className="text-[26px] leading-none font-semibold tabular-nums" style={{ color: rgbaCss(color) }}>
              {topic.stat.value}
            </span>
            <span className="text-[12px] leading-snug text-muted-foreground">{topic.stat.label}</span>
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
              <ChevronDown className={`size-3 transition-transform ${showFull ? "" : "-rotate-90"}`} aria-hidden />
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

function SchoolPressures({ card, color }: { card: PersonaCard; color: RGBAColor }) {
  return (
    <div className="grid gap-2 @xl:grid-cols-2">
      {card.schoolPressures.map((p, i) => (
        <div
          key={i}
          className="flex gap-3 rounded-xl border border-panel-border bg-secondary/30 p-3 transition-colors hover:bg-secondary/60 animate-in fade-in zoom-in-95 fill-mode-both"
          style={{ animationDelay: `${i * 60}ms` }}
        >
          <span className="flex size-9 shrink-0 items-center justify-center rounded-lg text-lg" style={{ backgroundColor: rgbaCss(color, 0.22) }}>
            {p.emoji}
          </span>
          <div className="min-w-0">
            <p className="text-[12.5px] font-semibold text-foreground">{p.label}</p>
            <p className="mt-0.5 text-[12px] leading-snug text-muted-foreground">{p.detail}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

function TheirAnswer({ regionId, personaId, name }: { regionId: string; personaId: string; name: string }) {
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
      {tldr && <p className="text-[13.5px] leading-snug font-semibold text-foreground">{tldr.text}</p>}
      <div className="mt-2 space-y-2 text-[12.5px] leading-relaxed text-muted-foreground">
        {rest.map((s, i) => (
          <p key={i}>{s.text}</p>
        ))}
      </div>
    </div>
  );
}

// ── Panel ───────────────────────────────────────────────────────────────────

function PersonaView({ regionId, personaId }: { regionId: string; personaId: string }) {
  const card = personaCard(regionId, personaId);
  const profile = usePersonaProfile(regionId, personaId);
  const region = KARNATAKA_REGIONS.find((r) => r.id === regionId);
  const [showDescription, setShowDescription] = useState(false);

  if (!card || !region) {
    return <p className="py-8 text-center text-[13px] text-muted-foreground">No card available for this persona.</p>;
  }
  const fullText: Record<string, string> = {};
  for (const t of profile?.topics ?? []) fullText[t.key] = t.profile;
  const genderLabel = personaId === "female" ? "Woman" : "Man";

  return (
    <div key={`${regionId}-${personaId}`} className="space-y-6 animate-in fade-in slide-in-from-bottom-2 duration-300">
      <Hero card={card} color={region.color} regionName={region.shortName} genderLabel={genderLabel} />

      {profile?.definition && (
        <div>
          <button
            type="button"
            onClick={() => setShowDescription((v) => !v)}
            aria-expanded={showDescription}
            className="label-micro flex items-center gap-1.5 transition-colors hover:text-foreground"
          >
            <ChevronDown className={`size-3 transition-transform ${showDescription ? "" : "-rotate-90"}`} aria-hidden />
            Full persona description
          </button>
          {showDescription && (
            <p className="mt-2 text-[12.5px] leading-relaxed text-muted-foreground animate-in fade-in duration-200">
              {profile.definition}
            </p>
          )}
        </div>
      )}

      <Section title="Household">
        <Household card={card} color={region.color} />
      </Section>
      <Section title="At a glance">
        <Vitals card={card} color={region.color} />
      </Section>
      <Section title="A day in their life">
        <DayInLife card={card} color={region.color} />
      </Section>
      <Section title="Explore their world">
        <TopicExplorer key={`${regionId}-${personaId}`} card={card} color={region.color} fullText={fullText} />
      </Section>
      <Section title="What pulls kids out of school here">
        <SchoolPressures card={card} color={region.color} />
      </Section>
      <Section title="What keeps them up at night">
        <div className="flex flex-wrap gap-2">
          {card.worries.map((w) => (
            <span key={w} className="rounded-full border border-panel-border bg-secondary/50 px-3 py-1 text-[12px] text-foreground/90">
              {w}
            </span>
          ))}
        </div>
      </Section>
      <Section title="Their answer to your query">
        <TheirAnswer regionId={regionId} personaId={personaId} name={card.name} />
      </Section>
    </div>
  );
}

export function PersonasPanel() {
  const persona = useExplorerStore((s) => s.persona);
  const select = useExplorerStore((s) => s.selectPersona);

  // First visit: open on a persona so the screen is never an empty prompt.
  useEffect(() => {
    if (!persona) select("old-mysuru", "male");
  }, [persona, select]);

  return (
    <div className="panel-surface @container pointer-events-auto flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl">
      <header className="border-b border-panel-border px-5 py-3.5">
        <p className="label-micro">Meet the personas</p>
        <h2 className="mt-1 text-sm font-medium text-foreground">Twelve composite residents, two from each region</h2>
      </header>
      <div className="min-h-0 flex-1 space-y-6 overflow-y-auto px-5 py-4 [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-border">
        <CastPicker />
        {persona && <PersonaView regionId={persona.regionId} personaId={persona.personaId} />}
      </div>
    </div>
  );
}
