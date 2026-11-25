/**
 * The stunting topic's media-research views: a district sheet with the same four tabs as dropout (on the ground,
 * news vs data, numbers, media & sources), and statewide key findings. Research files come from
 * scripts/research_stunting_districts.py (web search + Claude + page verification).
 */

import { ExternalLink } from "lucide-react";

import {
  prescribe,
  STUNTING_CATEGORY_EMOJI,
  STUNTING_CATEGORY_LABEL,
  useAllStuntingResearch,
  useExplorerStore,
  useStunting,
  useStuntingSettings,
  type ModelFactorWhy,
  type ResearchSource,
  type StuntingCategory,
  type StuntingResearch,
} from "@/lib/worldview";

import { StuntingDistrictView } from "./StuntingViews";

const VERDICT: Record<ModelFactorWhy["verdict"], { label: string; cls: string }> = {
  supported: {
    label: "Local evidence",
    cls: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
  },
  partly: { label: "Partly", cls: "bg-amber-500/15 text-amber-700 dark:text-amber-300" },
  "no-evidence": { label: "No local evidence", cls: "bg-secondary text-muted-foreground" },
};
const EVIDENCE_CLS = {
  strong: "text-emerald-700 dark:text-emerald-300",
  moderate: "text-amber-700 dark:text-amber-300",
  thin: "text-muted-foreground",
} as const;

function Sources({ ids, sources }: { ids: number[]; sources: ResearchSource[] }) {
  return (
    <span className="ml-1 inline-flex flex-wrap gap-1 align-baseline">
      {ids.map((id) => {
        const s = sources.find((x) => x.id === id);
        return s ? (
          <a
            key={id}
            href={s.url}
            target="_blank"
            rel="noreferrer"
            title={`${s.outlet} — ${s.title}`}
            className="rounded bg-secondary px-1 text-[10px] tabular-nums text-muted-foreground hover:text-foreground"
          >
            {id}
          </a>
        ) : null;
      })}
    </span>
  );
}

function Coverage({ r }: { r: StuntingResearch }) {
  return (
    <p className="text-[10px] leading-snug text-muted-foreground">
      {r.coverage} coverage · {r.sources.length} verified sources · researched {r.researchedOn} by
      automated web search. Every cited page was fetched and every number in a claim checked to be
      on it and attributable to this district; claims without numbers were not checked word by word
      {r.verificationNotes.length > 0
        ? ` (${r.verificationNotes.length} claims dropped in checking)`
        : ""}
      .
    </p>
  );
}

function OnTheGround({ r }: { r: StuntingResearch }) {
  return (
    <div className="space-y-4">
      <div>
        <p className="text-[14px] leading-snug font-semibold text-foreground">{r.headline}</p>
        {r.summary && (
          <p className="mt-1.5 text-[12.5px] leading-relaxed text-muted-foreground">{r.summary}</p>
        )}
      </div>
      {r.reasons.length > 0 && (
        <section>
          <p className="label-micro">What the sources point to</p>
          <ul className="mt-2 space-y-2">
            {r.reasons.map((x, i) => (
              <li
                key={i}
                className="rounded-lg border border-panel-border bg-secondary/30 px-3 py-2"
              >
                <p className="text-[12.5px] font-medium text-foreground">
                  {STUNTING_CATEGORY_EMOJI[x.category]} {x.factor}
                  <span className={`ml-2 text-[10px] font-normal ${EVIDENCE_CLS[x.evidence]}`}>
                    {x.evidence}
                  </span>
                </p>
                <p className="mt-0.5 text-[12px] leading-snug text-muted-foreground">
                  {x.detail}
                  <Sources ids={x.sources} sources={r.sources} />
                </p>
              </li>
            ))}
          </ul>
        </section>
      )}
      {r.keyFacts.length > 0 && (
        <section>
          <p className="label-micro">Key facts</p>
          <div className="mt-2 grid gap-2 @lg:grid-cols-2">
            {r.keyFacts.map((f, i) => (
              <div key={i} className="rounded-lg border border-panel-border px-3 py-2">
                <p className="text-[15px] leading-tight font-semibold text-foreground tabular-nums">
                  {f.value}
                </p>
                <p className="mt-0.5 text-[11px] text-muted-foreground">
                  {f.label}
                  <Sources ids={f.sources} sources={r.sources} />
                </p>
              </div>
            ))}
          </div>
        </section>
      )}
      {r.responses.length > 0 && (
        <section>
          <p className="label-micro">What is being done locally</p>
          <ul className="mt-2 space-y-1.5">
            {r.responses.map((x, i) => (
              <li key={i} className="text-[12px] leading-snug text-foreground/90">
                • {x.text}
                <Sources ids={x.sources} sources={r.sources} />
              </li>
            ))}
          </ul>
        </section>
      )}
      {r.gaps && <p className="text-[11px] leading-snug text-muted-foreground">Gaps: {r.gaps}</p>}
      <Coverage r={r} />
    </div>
  );
}

/** What the news says here vs what the NITI model prescribes, with the local evidence for each prescribed factor. */
function NewsVsModel({ r, districtId }: { r: StuntingResearch; districtId: string }) {
  const data = useStunting();
  const settings = useStuntingSettings();
  const d = data?.districts[districtId];
  const info = Object.fromEntries((data?.factors ?? []).map((f) => [f.name, f]));
  const top = data && d ? prescribe(data, d, settings).factors.slice(0, 3) : [];
  const cats = [...new Set(r.reasons.map((x) => x.category))];
  return (
    <div className="space-y-4">
      <p className="text-[11.5px] leading-snug text-muted-foreground">
        The news and the model answer different questions: the news reports what families and
        officials say is happening; the model ranks which measured factors would have to move
        furthest for a cut in stunting. Shown side by side, never blended.
      </p>
      <div className="grid gap-3 @lg:grid-cols-2">
        <section className="rounded-xl border border-panel-border bg-secondary/30 p-3">
          <p className="label-micro">What the news says</p>
          {cats.length ? (
            <ul className="mt-2 space-y-1.5">
              {cats.map((c) => (
                <li key={c} className="text-[12px] text-foreground/90">
                  {STUNTING_CATEGORY_EMOJI[c]} {STUNTING_CATEGORY_LABEL[c]}
                  <span className="ml-1 text-muted-foreground">
                    —{" "}
                    {r.reasons
                      .filter((x) => x.category === c)
                      .map((x) => x.factor)
                      .join("; ")}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-[12px] text-muted-foreground">
              No district-specific reasons found.
            </p>
          )}
        </section>
        <section className="rounded-xl border border-panel-border bg-secondary/30 p-3">
          <p className="label-micro">What the model prescribes</p>
          {top.length ? (
            <ul className="mt-2 space-y-1.5">
              {top.map((f) => (
                <li key={f.name} className="text-[12px] text-foreground/90">
                  {info[f.name]?.short ?? f.name}{" "}
                  <span className="tabular-nums text-muted-foreground">
                    {f.value.toFixed(1)}% → {f.prescribed.toFixed(1)}%
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-[12px] text-muted-foreground">
              No model figures for this district.
            </p>
          )}
        </section>
      </div>
      {r.modelFactorWhy.length > 0 && (
        <section>
          <p className="label-micro">Is there local evidence for the model&apos;s top factors?</p>
          <p className="mt-1 text-[10.5px] text-muted-foreground">
            Checked for the factors the model prescribes most change for at its default 20% target.
          </p>
          <ul className="mt-2 space-y-2">
            {r.modelFactorWhy.map((w) => (
              <li key={w.factor} className="rounded-lg border border-panel-border px-3 py-2">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-[12.5px] font-medium text-foreground">
                    {info[w.factor]?.short ?? w.factor}
                  </p>
                  <span
                    className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${VERDICT[w.verdict].cls}`}
                  >
                    {VERDICT[w.verdict].label}
                  </span>
                </div>
                {w.why && (
                  <p className="mt-1 text-[12px] leading-snug text-muted-foreground">{w.why}</p>
                )}
                {w.proof.map((p, i) => (
                  <p
                    key={i}
                    className="mt-1 border-l-2 border-panel-border pl-2 text-[11.5px] leading-snug text-foreground/85"
                  >
                    {p.claim}
                    <Sources ids={p.sources} sources={r.sources} />
                  </p>
                ))}
                {w.mechanism && (
                  <p className="mt-1 text-[10.5px] leading-snug text-muted-foreground">
                    How it could work (general, not local evidence): {w.mechanism}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function Media({ r }: { r: StuntingResearch }) {
  return (
    <div className="space-y-4">
      <section>
        <p className="label-micro">In the news</p>
        {r.headlines.length ? (
          <ul className="mt-2 space-y-2">
            {r.headlines.map((h) => (
              <li key={h.url}>
                <a
                  href={h.url}
                  target="_blank"
                  rel="noreferrer"
                  className="group flex items-start gap-1.5 text-[12.5px] font-medium text-foreground hover:underline"
                >
                  {h.title}
                  <ExternalLink className="mt-0.5 size-3 shrink-0 text-muted-foreground" />
                </a>
                <p className="text-[10.5px] text-muted-foreground">
                  {h.outlet}
                  {h.date ? ` · ${h.date}` : ""}
                </p>
                <p className="mt-0.5 text-[12px] leading-snug text-muted-foreground">
                  {h.takeaway}
                </p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-[12px] text-muted-foreground">
            No district-specific news items survived checking.
          </p>
        )}
      </section>
      <section>
        <p className="label-micro">All verified sources</p>
        <ol className="mt-2 space-y-1">
          {r.sources.map((s) => (
            <li key={s.id} className="text-[11.5px] leading-snug text-muted-foreground">
              <span className="tabular-nums">{s.id}.</span>{" "}
              <a
                href={s.url}
                target="_blank"
                rel="noreferrer"
                className="text-foreground/90 hover:underline"
              >
                {s.title}
              </a>{" "}
              · {s.outlet}
              {s.date ? ` · ${s.date}` : ""} · {s.type}
            </li>
          ))}
        </ol>
      </section>
      <Coverage r={r} />
    </div>
  );
}

const TABS = [
  { id: "reasons", label: "On the ground" },
  { id: "compare", label: "News vs data" },
  { id: "numbers", label: "Numbers" },
  { id: "media", label: "Media & sources" },
] as const;

/** The map's district sheet for the stunting topic. */
export function StuntingDistrictSheet({ districtId }: { districtId: string }) {
  const all = useAllStuntingResearch();
  const tab = useExplorerStore((s) => s.districtTab);
  const setTab = useExplorerStore((s) => s.setDistrictTab);
  const r = all?.[districtId];
  const missing = (
    <p className="rounded-xl border border-dashed border-panel-border px-4 py-3 text-[12px] text-muted-foreground">
      {all === undefined
        ? "Loading the stunting research…"
        : "No stunting research for this district yet."}
    </p>
  );
  return (
    <div>
      <div className="mb-4 flex gap-1 rounded-lg bg-secondary/60 p-1" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => setTab(t.id)}
            className={
              "flex-1 rounded-md px-2.5 py-1.5 text-[11.5px] font-medium transition-colors " +
              (tab === t.id
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground")
            }
          >
            {t.label}
          </button>
        ))}
      </div>
      {tab === "numbers" ? (
        <StuntingDistrictView districtId={districtId} />
      ) : !r ? (
        missing
      ) : tab === "compare" ? (
        <NewsVsModel r={r} districtId={districtId} />
      ) : tab === "media" ? (
        <Media r={r} />
      ) : (
        <OnTheGround r={r} />
      )}
    </div>
  );
}

// ── Statewide key findings ───────────────────────────────────────────────────

export function StuntingKeyFindings() {
  const all = useAllStuntingResearch();
  const data = useStunting();
  const focusDistrict = useExplorerStore((s) => s.focusDistrict);
  if (!all || !data) return null;
  const files = Object.values(all);
  if (!files.length) return null;
  const n = files.length;
  const cov = { rich: 0, moderate: 0, thin: 0 };
  files.forEach((f) => (cov[f.coverage] += 1));
  const sources = files.reduce((a, f) => a + f.sources.length, 0);
  const catDistricts = new Map<StuntingCategory, Set<string>>();
  for (const f of files)
    for (const r of f.reasons)
      (
        catDistricts.get(r.category) ?? catDistricts.set(r.category, new Set()).get(r.category)!
      ).add(f.districtId);
  const cats = [...catDistricts.entries()].sort((a, b) => b[1].size - a[1].size);
  const strong = files.flatMap((f) =>
    f.reasons.filter((r) => r.evidence === "strong").map((r) => ({ f, r })),
  );
  const info = Object.fromEntries(data.factors.map((f) => [f.name, f]));
  const why = new Map<string, Record<ModelFactorWhy["verdict"], number>>();
  for (const f of files)
    for (const w of f.modelFactorWhy) {
      const t = why.get(w.factor) ?? { supported: 0, partly: 0, "no-evidence": 0 };
      t[w.verdict] += 1;
      why.set(w.factor, t);
    }
  return (
    <div className="space-y-6">
      <section>
        <p className="label-micro">Key findings from the media research</p>
        <p className="mt-1 text-[11.5px] leading-snug text-muted-foreground">
          {n} districts researched from {sources} verified sources: {cov.rich} rich, {cov.moderate}{" "}
          moderate, {cov.thin} thin coverage. Collected by automated web search; every number in a
          claim was checked to be on its cited page and attributable to the district.
        </p>
      </section>
      <section>
        <p className="label-micro">What the news points to, by number of districts</p>
        <ul className="mt-2 space-y-1.5">
          {cats.map(([c, ds]) => (
            <li key={c} className="flex items-center gap-3 text-[12px]">
              <span className="w-56 shrink-0 truncate text-foreground/90">
                {STUNTING_CATEGORY_EMOJI[c]} {STUNTING_CATEGORY_LABEL[c]}
              </span>
              <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-secondary">
                <span
                  className="block h-full rounded-full bg-[var(--chart-2)]"
                  style={{ width: `${(ds.size / n) * 100}%` }}
                />
              </span>
              <span className="w-14 shrink-0 text-right tabular-nums text-muted-foreground">
                {ds.size} of {n}
              </span>
            </li>
          ))}
        </ul>
      </section>
      {why.size > 0 && (
        <section>
          <p className="label-micro">
            News vs data: local evidence for the model&apos;s top factors
          </p>
          <p className="mt-1 text-[11px] leading-snug text-muted-foreground">
            For each factor the model prescribes most change for, in how many districts the news
            gives local evidence for why it matters.
          </p>
          <ul className="mt-2 space-y-1">
            {[...why.entries()]
              .sort(
                (a, b) =>
                  b[1].supported +
                  b[1].partly +
                  b[1]["no-evidence"] -
                  (a[1].supported + a[1].partly + a[1]["no-evidence"]),
              )
              .map(([factor, t]) => (
                <li key={factor} className="flex items-baseline justify-between gap-3 text-[12px]">
                  <span className="text-foreground/90">{info[factor]?.short ?? factor}</span>
                  <span className="shrink-0 text-[11px] tabular-nums text-muted-foreground">
                    {t.supported} local evidence · {t.partly} partly · {t["no-evidence"]} none
                  </span>
                </li>
              ))}
          </ul>
        </section>
      )}
      {strong.length > 0 && (
        <section>
          <p className="label-micro">Best-evidenced findings ({strong.length})</p>
          <ul className="mt-2 space-y-1.5">
            {strong.slice(0, 12).map(({ f, r }, i) => (
              <li key={i} className="text-[12px] leading-snug">
                <button
                  type="button"
                  onClick={() => focusDistrict(f.districtId, f.regionId, "reasons")}
                  className="font-medium text-foreground hover:underline"
                >
                  {f.name.split(" (")[0]}
                </button>
                <span className="text-muted-foreground">
                  {" "}
                  · {r.factor}: {r.detail}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
