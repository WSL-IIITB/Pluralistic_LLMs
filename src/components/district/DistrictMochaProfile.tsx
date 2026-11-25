/**
 * The district sheet's "Profile" tab (both topics): District Mocha's background profile of the district -- baseline
 * figures, challenges, strengths, opportunities, goals, programmes, industries and role-based actions. Outside
 * context, labelled as such and linked to its page; items touching the active topic are marked.
 */

import { ExternalLink } from "lucide-react";
import { useState } from "react";

import { useDistrictMocha, useExplorerStore, type MochaProfile } from "@/lib/worldview";

/** Words that tie a profile item to each study topic. */
const TOPIC_WORDS: Record<string, RegExp> = {
  dropout:
    /school|literacy|literate|educat|dropout|girls?\b|child labou?r|migrat|student|teacher|enrol|college|skill/i,
  stunting:
    /nutri|stunt|anaemi|anemi|health|anganwadi|matern|child|infant|sanitation|drinking water|water supply|fluoride|hospital|ration|food|poverty/i,
};

function Relevant({ text, re }: { text: string; re: RegExp }) {
  if (!re.test(text)) return null;
  return (
    <span className="ml-1.5 inline-block rounded-full bg-primary/15 px-1.5 py-px align-middle text-[9.5px] font-medium tracking-wide text-primary uppercase">
      topic
    </span>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <p className="label-micro mb-2">{title}</p>
      {children}
    </section>
  );
}

function Items({ rows, re }: { rows: { title: string; detail: string }[]; re: RegExp }) {
  return (
    <ul className="space-y-2">
      {rows.map((r, i) => (
        <li key={i} className="text-[12px] leading-snug">
          <p className="font-medium text-foreground">
            {r.title}
            <Relevant text={`${r.title} ${r.detail}`} re={re} />
          </p>
          {r.detail && <p className="mt-0.5 text-muted-foreground">{r.detail}</p>}
        </li>
      ))}
    </ul>
  );
}

function Profile({ p, re }: { p: MochaProfile; re: RegExp }) {
  return (
    <div className="space-y-5">
      {p.tagline && <p className="text-[12.5px] leading-snug text-foreground/85">{p.tagline}</p>}

      {p.baseline.length > 0 && (
        <div className="grid grid-cols-2 gap-2 @lg:grid-cols-3">
          {p.baseline.map((b) => (
            <div
              key={b.label}
              className="rounded-xl border border-panel-border bg-secondary/40 px-3 py-2.5"
            >
              <p className="text-[17px] leading-none font-semibold tabular-nums text-foreground">
                {b.value}
              </p>
              <p className="mt-1 text-[10px] tracking-wide text-muted-foreground uppercase">
                {b.label}
                {b.year ? ` · ${b.year}` : ""}
              </p>
              {b.note && <p className="mt-0.5 text-[10.5px] text-muted-foreground">{b.note}</p>}
            </div>
          ))}
        </div>
      )}

      {p.challenges.length > 0 && (
        <Section title="Challenges">
          <Items rows={p.challenges} re={re} />
        </Section>
      )}
      {p.strengths.length > 0 && (
        <Section title="Strengths">
          <Items rows={p.strengths} re={re} />
        </Section>
      )}
      {p.opportunities.length > 0 && (
        <Section title="Opportunities">
          <Items rows={p.opportunities} re={re} />
        </Section>
      )}

      {p.goals.length > 0 && (
        <Section title="Goals">
          <ul className="space-y-1.5">
            {p.goals.map((g, i) => (
              <li key={i} className="flex gap-2.5 text-[12px] leading-snug">
                <span className="w-24 shrink-0 font-semibold text-foreground tabular-nums">
                  → {g.target}
                </span>
                <span className="text-muted-foreground">
                  {g.detail}
                  <Relevant text={g.detail} re={re} />
                </span>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {p.programmes.length > 0 && (
        <Section title="Core programmes">
          <ul className="space-y-1.5">
            {p.programmes.map((g, i) => (
              <li key={i} className="flex items-baseline justify-between gap-3 text-[12px]">
                <span className="text-foreground/90">
                  {g.name}
                  <Relevant text={`${g.name} ${g.status}`} re={re} />
                </span>
                <span className="shrink-0 text-right text-[11px] text-muted-foreground">
                  {g.status}
                </span>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {p.industries.length > 0 && (
        <Section title={p.industriesTitle ?? "Industries"}>
          <ul className="space-y-2">
            {p.industries.map((g, i) => (
              <li key={i} className="text-[12px] leading-snug">
                <p className="font-medium text-foreground">
                  {g.name}
                  {g.priority && (
                    <span className="ml-1.5 text-[10.5px] font-normal text-muted-foreground">
                      · {g.priority} priority
                    </span>
                  )}
                </p>
                <p className="text-muted-foreground">
                  {[g.stats, g.note].filter(Boolean).join(" — ")}
                </p>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {p.roles.length > 0 && (
        <Section title="Role-based actions">
          <ul className="space-y-1.5">
            {p.roles.map((r, i) => (
              <li key={i} className="text-[12px] leading-snug">
                <span className="font-medium text-foreground">{r.role}</span>
                <span className="text-muted-foreground"> — {r.action}</span>
                <Relevant text={`${r.role} ${r.action}`} re={re} />
              </li>
            ))}
          </ul>
        </Section>
      )}

      {p.linked.length > 0 && (
        <Section title="More on District Mocha">
          <ul className="space-y-1.5">
            {p.linked.map((l, i) => (
              <li key={i} className="text-[12px] leading-snug">
                <a
                  href={l.url}
                  target="_blank"
                  rel="noreferrer"
                  className="font-medium text-foreground hover:underline"
                >
                  {l.name}
                  <ExternalLink className="ml-1 inline size-3 align-baseline opacity-60" />
                </a>
                <span className="text-muted-foreground">
                  {" "}
                  · {l.kind}
                  {l.summary ? ` — ${l.summary}` : ""}
                </span>
              </li>
            ))}
          </ul>
        </Section>
      )}
    </div>
  );
}

export function DistrictMochaProfile({ districtId }: { districtId: string }) {
  const data = useDistrictMocha();
  const topic = useExplorerStore((s) => s.topic);
  const [which, setWhich] = useState(0);
  const d = data?.districts[districtId];
  if (data === undefined)
    return <p className="text-[12px] text-muted-foreground">Loading the district profile…</p>;
  if (!data || !d)
    return (
      <p className="rounded-xl border border-dashed border-panel-border px-4 py-3 text-[12px] text-muted-foreground">
        No District Mocha profile for this district.
      </p>
    );
  const profiles: MochaProfile[] = [d, ...(d.also ?? [])];
  const p = profiles[Math.min(which, profiles.length - 1)]!;
  const re = TOPIC_WORDS[topic] ?? TOPIC_WORDS["dropout"]!;
  return (
    <div className="space-y-5">
      <div className="rounded-xl border border-panel-border bg-secondary/30 px-3.5 py-2.5 text-[11px] leading-snug text-muted-foreground">
        <span className="font-medium text-foreground">
          Outside context, not this study&apos;s research.
        </span>{" "}
        From{" "}
        <a
          href={p.url}
          target="_blank"
          rel="noreferrer"
          className="text-foreground underline-offset-2 hover:underline"
        >
          {data.source.name}
        </a>
        , an AI-assisted development dashboard by another team. Figures are as published there,
        without per-figure sources, and were not checked by us. Items marked{" "}
        <span className="rounded-full bg-primary/15 px-1.5 py-px text-[9.5px] font-medium tracking-wide text-primary uppercase">
          topic
        </span>{" "}
        mention something tied to{" "}
        {topic === "stunting" ? "child nutrition and health" : "schooling"}.
      </div>

      {profiles.length > 1 && (
        <div className="flex gap-1.5">
          {profiles.map((x, i) => (
            <button
              key={x.name}
              type="button"
              onClick={() => setWhich(i)}
              className={
                "rounded-full border px-2.5 py-0.5 text-[11px] transition-colors " +
                (i === which
                  ? "border-primary/40 bg-primary/10 text-foreground"
                  : "border-panel-border text-muted-foreground hover:text-foreground")
              }
            >
              {x.name}
            </button>
          ))}
        </div>
      )}

      <Profile p={p} re={re} />
    </div>
  );
}
