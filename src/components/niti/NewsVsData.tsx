/**
 * News vs data: how the news research and the UIDAI/NITI data, which name different "main" factors, may connect.
 *
 * The news mostly reports poverty, child labour and child marriage; the data's district-level factor for almost
 * every Karnataka district is the share of English-medium schools, and household sanitation is the state-level one.
 * `NewsVsDataSummary` explains the links for the whole state (UIDAI / NITI tab); `DistrictNewsVsData` does it for one
 * district (the map's district sheet), with the NITI model's top three changes and the local reports on them.
 * Everything comes from public/data/news-vs-data.json: counts over the research files and the workbooks, and
 * general reasoning on how a data factor could be tied to a kind of news reason (shown as possible links).
 */

import { MessageCircleQuestion } from "lucide-react";

import { EVIDENCE_STYLE } from "@/components/dashboard/map/factorWhyStyle";
import {
  CATEGORY_EMOJI,
  formatFactorValue,
  shortFactor,
  useDistrictResearch,
  useExplorerStore,
  useNewsVsData,
  type NewsVsDataDistrict,
  type NewsVsDataStatewide,
  type TopChange,
} from "@/lib/worldview";
import { useChatStore } from "@/lib/worldview/chatStore";

/** A short factor label for use mid-sentence: lower-case first letter, except "English". */
function inline(factor: string): string {
  const s = shortFactor(factor);
  return s.startsWith("English") ? s : s.charAt(0).toLowerCase() + s.slice(1);
}

function Block({
  title,
  emoji,
  children,
}: {
  title: string;
  emoji: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-panel-border bg-secondary/30 p-3.5">
      <p className="flex items-center gap-1.5 text-[12px] font-semibold text-foreground">
        <span aria-hidden>{emoji}</span>
        {title}
      </p>
      <div className="mt-2.5 space-y-2 text-[11.5px] leading-snug text-muted-foreground">
        {children}
      </div>
    </div>
  );
}

function AskButton({ question, label }: { question: string; label: string }) {
  const queue = useChatStore((s) => s.queue);
  const setTab = useExplorerStore((s) => s.setTab);
  return (
    <button
      type="button"
      onClick={() => {
        queue(question);
        setTab("Ask");
      }}
      className="inline-flex items-center gap-1.5 rounded-full border border-panel-border px-3 py-1.5 text-[11px] font-medium text-primary transition-colors hover:bg-secondary"
    >
      <MessageCircleQuestion className="size-3.5" aria-hidden />
      {label}
    </button>
  );
}

/** Numbered "how they connect" points: a title and the reasoning behind the link. */
function Connections({ items, note }: { items: { title: string; text: string }[]; note: string }) {
  return (
    <div>
      <ol className="space-y-2.5">
        {items.map((d, i) => (
          <li key={d.title} className="flex gap-2.5">
            <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-primary/15 text-[10.5px] font-semibold text-primary tabular-nums">
              {i + 1}
            </span>
            <p className="text-[11.5px] leading-snug text-muted-foreground">
              <span className="font-medium text-foreground/90">{d.title}. </span>
              {d.text}
            </p>
          </li>
        ))}
      </ol>
      <p className="mt-2 text-[10px] leading-snug text-muted-foreground">{note}</p>
    </div>
  );
}

const STANCE_LABEL: Record<string, string> = {
  gap: "shows the gap",
  progress: "reports progress",
  context: "background",
};

/** The NITI model's top changes and the household pressures in the news: where they meet, for the whole state. */
function PrescriptiveConnect({ s }: { s: NewsVsDataStatewide }) {
  const p = s.prescriptive;
  if (!p) return null;
  return (
    <div className="rounded-xl border border-panel-border bg-secondary/30 p-3.5">
      <p className="text-[12px] font-semibold text-foreground">
        The NITI model&apos;s top changes and the news
      </p>
      <p className="mt-1.5 text-[11.5px] leading-snug text-muted-foreground">{p.text}</p>
      <ul className="mt-3 space-y-1 text-[11.5px]">
        {p.byFactor.slice(0, 8).map((f) => (
          <li key={f.short} className="flex items-baseline justify-between gap-2">
            <span className="text-foreground/90">{f.short}</span>
            <span className="shrink-0 text-[11px] text-muted-foreground tabular-nums">
              top change in {f.districts} · local reports of the gap in {f.withSources}
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-[10.5px] leading-snug text-muted-foreground">
        Each district&apos;s three changes, with links to the local reports, are in its sheet under
        “News vs data”.
      </p>
    </div>
  );
}

/** One district's top three changes: why each could matter there, and the local reports on it. */
function DistrictTopChanges({
  districtId,
  name,
  changes,
}: {
  districtId: string;
  name: string;
  changes: TopChange[];
}) {
  const research = useDistrictResearch(districtId);
  const pre = research.status === "ready" ? research.data.prescriptiveEvidence : undefined;
  if (!changes.length) return null;
  return (
    <div>
      <p className="label-micro mb-2">Top three changes · NITI model</p>
      <div className="space-y-2.5">
        {changes.map((c) => {
          const ev = pre?.changes.find((x) => x.factor === c.factor);
          return (
            <div
              key={c.factor}
              className="rounded-xl border border-panel-border bg-secondary/30 p-3"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-primary/15 text-[10.5px] font-semibold text-primary tabular-nums">
                  {c.rank}
                </span>
                <span className="text-[12px] font-semibold text-foreground">{c.short}</span>
                {c.value != null && (
                  <span className="text-[11px] text-muted-foreground tabular-nums">
                    {formatFactorValue(c.factor, c.value)} · rank {c.karnatakaRank} of 35
                  </span>
                )}
              </div>
              <p className="mt-1.5 text-[11.5px] leading-snug text-muted-foreground">{c.line}</p>
              {ev && ev.findings.length > 0 && (
                <ul className="mt-2 space-y-1.5">
                  {ev.findings.map((f, i) => (
                    <li key={i} className="text-[11px] leading-snug text-muted-foreground">
                      <span
                        className={
                          "mr-1.5 rounded px-1.5 py-px text-[9.5px] font-medium tracking-wide uppercase " +
                          (f.scope === "district"
                            ? "bg-primary/15 text-primary"
                            : "bg-secondary text-muted-foreground")
                        }
                      >
                        {f.scope === "district" ? name : "Statewide"} · {STANCE_LABEL[f.stance]}
                      </span>
                      <span className="text-foreground/90">{f.claim}</span>
                      {f.quote && <span className="italic"> “{f.quote}”</span>}
                      {f.sources.map((sid) => {
                        const src = pre!.sources.find((x) => x.id === sid);
                        return src ? (
                          <a
                            key={sid}
                            href={src.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            title={`${src.outlet}${src.date ? ` · ${src.date}` : ""} — ${src.title}`}
                            className="ml-1 rounded bg-secondary px-1.5 text-[10px] leading-4 text-muted-foreground transition-colors hover:text-foreground"
                          >
                            {src.outlet}
                          </a>
                        ) : null;
                      })}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          );
        })}
      </div>
      <p className="mt-2 text-[10px] leading-snug text-muted-foreground">
        Changes from the NITI prescriptive model (feasible ranking). Each report links to its page.
      </p>
    </div>
  );
}

// ── Statewide ───────────────────────────────────────────────────────────────

function NewsBlock({ s }: { s: NewsVsDataStatewide }) {
  const cats = s.news.categories.slice(0, 5);
  const cl = s.news.childLabour;
  return (
    <Block title="What the news says" emoji="📰">
      <ul className="space-y-1.5">
        {cats.map((c) => (
          <li key={c.category}>
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-foreground/90">
                <span aria-hidden>{CATEGORY_EMOJI[c.category]} </span>
                {c.label}
              </span>
              <span className="shrink-0 tabular-nums">
                {c.districts}/{s.districts}
              </span>
            </div>
            <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-secondary">
              <div
                className="h-full rounded-full bg-primary/70"
                style={{ width: `${(c.districts / s.districts) * 100}%` }}
              />
            </div>
          </li>
        ))}
      </ul>
      <p className="text-[10.5px]">Districts whose news reports the reason (of {s.districts}).</p>
      <p>
        <span className="font-medium text-foreground/90">Child labour</span> is named outright in{" "}
        {cl.districts.length} districts.
      </p>
      <p>
        Of {s.news.headlines.total} headlines: child marriage {s.news.headlines.childMarriage},
        child labour {s.news.headlines.childLabour}, language of instruction{" "}
        {s.news.headlines.language}.
      </p>
    </Block>
  );
}

function DataBlock({ s }: { s: NewsVsDataStatewide }) {
  const nat = s.data.national;
  const total = s.data.districtFactors.reduce((a, f) => a + f.rows, 0);
  return (
    <Block title="What the data says" emoji="📊">
      {s.data.stateFactors.map((f) => (
        <p key={f.factor}>
          <span className="font-medium text-foreground/90">State-level:</span> {inline(f.factor)} on
          every Karnataka row ({f.rows}).
        </p>
      ))}
      <div>
        <p className="font-medium text-foreground/90">District-level:</p>
        <ul className="mt-1 space-y-1">
          {s.data.districtFactors.map((f) => (
            <li key={f.factor} className="flex items-baseline justify-between gap-2">
              <span className="text-foreground/90">{shortFactor(f.factor)}</span>
              <span className="shrink-0 tabular-nums">
                {f.rows}/{total} rows
              </span>
            </li>
          ))}
        </ul>
      </div>
      <p>
        Across India, {inline(nat.topDistrictFactor)} is the{" "}
        {nat.topDistrictFactorRank === 1 ? "most common" : `#${nat.topDistrictFactorRank}`}{" "}
        district-level factor ({nat.topDistrictFactorRows} of {nat.rows} districts).
      </p>
      <p>
        The workbooks&apos; factors are school, teacher, inspection, household-amenity and
        women&apos;s-schooling indicators: the conditions around a child, where the news describes
        what happens to the child.
      </p>
    </Block>
  );
}

function MeetBlock({ s }: { s: NewsVsDataStatewide }) {
  const m = s.meet;
  return (
    <Block title="Where they meet" emoji="🤝">
      {m.touchingLanguage.length > 0 && (
        <div>
          <p className="font-medium text-foreground/90">
            In the news, the language of instruction:
          </p>
          <ul className="mt-1 space-y-1">
            {m.touchingLanguage.map((t) => (
              <li key={`${t.name}-${t.factor}`}>
                <span className="text-foreground/90">{t.name}:</span> “{t.factor}”
              </li>
            ))}
          </ul>
        </div>
      )}
      {m.generalClaims.length > 0 && (
        <p>
          <span className="font-medium text-foreground/90">Research from elsewhere: </span>“
          {m.generalClaims.join("”; “")}”.
        </p>
      )}
      <p>
        Household sanitation and the girls&apos; exits the news reports both turn on adolescent
        girls&apos; safety and privacy.
      </p>
    </Block>
  );
}

export function NewsVsDataSummary() {
  const data = useNewsVsData();
  if (data === undefined)
    return <p className="text-[12px] text-muted-foreground">Loading the comparison…</p>;
  if (data === null)
    return (
      <p className="text-[12px] text-muted-foreground">
        The news-vs-data file could not be loaded. Reload the page to try again.
      </p>
    );
  const s = data.statewide;
  return (
    <div className="space-y-4">
      <p className="text-[12.5px] leading-relaxed text-foreground/90">{s.lead}</p>

      <div className="grid gap-2.5 @2xl:grid-cols-3">
        <NewsBlock s={s} />
        <DataBlock s={s} />
        <MeetBlock s={s} />
      </div>

      <div>
        <p className="mb-2 text-[12px] font-semibold text-foreground">How they connect</p>
        <Connections
          items={s.connections}
          note="Possible links: reasoning on how each data factor could be tied to the reasons the news reports."
        />
      </div>

      <PrescriptiveConnect s={s} />

      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="max-w-[520px] text-[10.5px] leading-snug text-muted-foreground">
          For one district&apos;s own picture, use its “News vs data” button below: it opens the
          district&apos;s sheet on the map.
        </p>
        <AskButton
          label="Ask about this"
          question="Why does child labour show up most in the news about secondary school dropout in Karnataka, while the UIDAI/NITI data shows the medium of instruction (English-medium schools) as the dominant factor? Explain what the news says, what the data says, and how the two could be connected."
        />
      </div>
    </div>
  );
}

// ── One district ────────────────────────────────────────────────────────────

function districtQuestion(name: string, d: NewsVsDataDistrict): string {
  const row = d.data.find((f) => f.method === "district");
  const factor = row ? inline(row.factor) : "its dominant factor";
  const news = d.news.topCategories.slice(0, 2).join(" and ") || "several reasons";
  return (
    `In ${name}, the news on secondary school dropout mostly reports ${news}, but the UIDAI/NITI data flags ` +
    `${factor} as the dominant factor. How could ${factor} be connected to what the news reports here, and what could help?`
  );
}

export function DistrictNewsVsData({ districtId, name }: { districtId: string; name: string }) {
  const data = useNewsVsData();
  if (data === undefined)
    return <p className="text-[12px] text-muted-foreground">Loading the comparison…</p>;
  const d = data?.districts[districtId];
  if (!d)
    return (
      <p className="text-[12px] leading-snug text-muted-foreground">
        No news-vs-data comparison for {name}: it needs both research and factor rows.
      </p>
    );

  return (
    <div className="space-y-4">
      <div className="grid gap-2.5 @lg:grid-cols-2">
        <Block title="The news says" emoji="📰">
          <p>
            {d.news.reasons} reasons, mostly{" "}
            <span className="text-foreground/90">{d.news.topCategories.join(", ")}</span>.
          </p>
          <ul className="space-y-1">
            {d.news.top.map((r) => (
              <li key={r.factor} className="flex items-start justify-between gap-2">
                <span className="text-foreground/90">
                  <span aria-hidden>{CATEGORY_EMOJI[r.category]} </span>
                  {r.factor}
                </span>
                <span
                  className={
                    "shrink-0 rounded-full px-1.5 py-px text-[9.5px] font-medium " +
                    EVIDENCE_STYLE[r.evidence]
                  }
                >
                  {r.evidence}
                </span>
              </li>
            ))}
          </ul>
        </Block>
        <Block title="The data says" emoji="📊">
          {(["district", "state"] as const).map((m) => {
            const rows = d.data.filter((f) => f.method === m);
            if (!rows.length) return null;
            return (
              <div key={m}>
                <p className="text-[10px] font-medium tracking-wide uppercase">
                  {m === "district" ? "District-level factor" : "State-level factor"}
                </p>
                <p className="mt-0.5 text-foreground/90">{shortFactor(rows[0]!.factor)}</p>
                {rows.map((f) => (
                  <p key={f.area} className="tabular-nums">
                    {f.area.toLowerCase() === name.toLowerCase() ? "" : `${f.area}: `}
                    {f.share != null
                      ? `${f.share.toFixed(1)}% · rank ${f.shareRank} of 35`
                      : f.weight}
                  </p>
                ))}
              </div>
            );
          })}
        </Block>
      </div>

      <div>
        <p className="label-micro mb-2">How they may connect here</p>
        <Connections
          items={d.connections}
          note="Possible links: reasoning on how the data's factors could be tied to the reasons the news reports here. Shares and ranks are from the NITI data (35 Karnataka rows)."
        />
      </div>

      <DistrictTopChanges districtId={districtId} name={name} changes={d.topChanges ?? []} />

      <div className="flex flex-wrap items-center justify-end gap-2">
        <AskButton label={`Ask about ${name}`} question={districtQuestion(name, d)} />
      </div>
    </div>
  );
}
