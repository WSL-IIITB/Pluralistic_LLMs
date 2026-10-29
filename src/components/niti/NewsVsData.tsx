/**
 * News vs data: why the news research and the UIDAI/NITI data point to different "main" factors.
 *
 * The news mostly reports poverty, child labour and child marriage; the data's district-level factor for almost
 * every Karnataka district is the share of English-medium schools. `NewsVsDataSummary` explains the gap for the
 * whole state (UIDAI / NITI tab); `DistrictNewsVsData` does it for one district (the map's district sheet).
 * Everything shown comes from public/data/news-vs-data.json: counts and templated sentences over our verified
 * research files and the two workbooks, no model-written text.
 */

import { MessageCircleQuestion } from "lucide-react";

import { EVIDENCE_STYLE } from "@/components/dashboard/map/factorWhyStyle";
import {
  CATEGORY_EMOJI,
  shortFactor,
  useExplorerStore,
  useNewsVsData,
  type NewsVsDataDistrict,
  type NewsVsDataStatewide,
} from "@/lib/worldview";
import { useChatStore } from "@/lib/worldview/chatStore";

const WHY_TEXT: Record<string, string> = {
  supported: "supported by proof about this district",
  partly: "partly: only research from elsewhere backs it",
  "not-supported": "not supported",
  "no-evidence": "no evidence found",
};
const CHECK_TEXT: Record<string, string> = {
  supports: "local evidence supports it",
  contradicts: "local evidence contradicts it",
  unclear: "local evidence is unclear",
  "no-evidence": "sources silent",
};
const WHY_SHORT: [string, string][] = [
  ["supported", "supported"],
  ["partly", "partly"],
  ["not-supported", "not supported"],
  ["no-evidence", "no evidence"],
];

/** A short factor label for use mid-sentence: lower-case first letter, except "English". */
function inline(factor: string): string {
  const s = shortFactor(factor);
  return s.startsWith("English") ? s : s.charAt(0).toLowerCase() + s.slice(1);
}

/** "supported 0 · partly 6 · no evidence 29" -- "supported" is always shown, even at 0. */
function verdictLine(counts: Record<string, number>): string {
  return WHY_SHORT.filter(([k]) => k === "supported" || counts[k])
    .map(([k, label]) => `${label} ${counts[k] ?? 0}`)
    .join(" · ");
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
      <p className="text-[10.5px]">
        Districts where the research found the reason (of {s.districts}).
      </p>
      <p>
        <span className="font-medium text-foreground/90">Child labour</span> is named outright in{" "}
        {cl.districts.length} districts ({cl.reasons} reasons: {cl.strong} strong, {cl.moderate}{" "}
        moderate, {cl.thin} thin evidence).
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
        {nat.socialFactors.length === 0
          ? `None of the ${new Set([...nat.stateFactorNames, ...nat.districtFactorNames]).size} different factors in the workbooks measures child labour, child marriage, migration or income.`
          : `Factors touching social conditions: ${nat.socialFactors.join(", ")}.`}
      </p>
    </Block>
  );
}

function FoundBlock({ s }: { s: NewsVsDataStatewide }) {
  const f = s.found;
  return (
    <Block title="What we found" emoji="🔎">
      <p>
        <span className="font-medium text-foreground/90">District-level rows</span>, checked with
        deep research and page-verified proof: {verdictLine(f.why.district)}.
      </p>
      <p>
        <span className="font-medium text-foreground/90">State-level rows</span>:{" "}
        {verdictLine(f.why.state)}.
      </p>
      <p>
        For the district-level factor, verified proof about a Karnataka district itself:{" "}
        {f.districtLevelProof.district}. From elsewhere: {f.districtLevelProof.general} item(s)
        {f.generalClaims.length > 0 && <>, saying “{f.generalClaims.join("” and “")}”</>}.
      </p>
      <p>
        News reasons that touch the language of instruction:{" "}
        {s.news.touchingLanguage.length
          ? s.news.touchingLanguage
              .map((t) => `${t.name} (“${t.factor}”, ${t.evidence})`)
              .join("; ")
          : "none"}
        .
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
        <FoundBlock s={s} />
      </div>

      <div>
        <p className="text-[12px] font-semibold text-foreground">Why they differ</p>
        <ol className="mt-2 space-y-2.5">
          {s.differ.map((d, i) => (
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
      </div>

      <div className="rounded-xl border border-dashed border-panel-border px-3.5 py-3">
        <p className="text-[12px] font-semibold text-foreground">How both could be true</p>
        <p className="mt-1.5 text-[11.5px] leading-snug text-muted-foreground">{s.connect.text}</p>
        <p className="mt-1.5 text-[11px] leading-snug text-amber-800 dark:text-amber-300">
          <span className="font-medium">Not tested. </span>
          {s.connect.untested}
        </p>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="max-w-[520px] text-[10.5px] leading-snug text-muted-foreground">
          Counts come from our verified research files and the two workbooks; no model-written text
          here. For one district&apos;s own comparison, use its “News vs data” button below: it
          opens the district&apos;s sheet on the map.
        </p>
        <AskButton
          label="Ask about this"
          question="Why does child labour show up most in the news about secondary school dropout in Karnataka, while the UIDAI/NITI data shows the medium of instruction (English-medium schools) as the dominant factor? Explain what the news says, what the data says, what the research found, and why they differ."
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
    `${factor} as the dominant factor. Why might the data flag ${factor} here, why do the news and the data differ, and what does each suggest could help?`
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
  const found = d.found.district;

  return (
    <div className="space-y-4">
      <div className="grid gap-2.5 @lg:grid-cols-3">
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
          {(["state", "district"] as const).map((m) => {
            const rows = d.data.filter((f) => f.method === m);
            if (!rows.length) return null;
            return (
              <div key={m}>
                <p className="text-[10px] font-medium tracking-wide uppercase">{m}-level factor</p>
                <p className="mt-0.5 text-foreground/90">{shortFactor(rows[0]!.factor)}</p>
                <p className="tabular-nums">
                  {rows
                    .map(
                      (f) =>
                        `${f.area.toLowerCase() === name.toLowerCase() ? "" : `${f.area} `}${f.value}`,
                    )
                    .join(" · ")}
                </p>
              </div>
            );
          })}
        </Block>
        <Block title="What we found" emoji="🔎">
          <p>
            District-level factor, checked against sources:{" "}
            <span className="text-foreground/90">
              {found.check ? CHECK_TEXT[found.check] : "not checked"}
            </span>
            .
          </p>
          <p>
            “Why is it dominant?” research:{" "}
            <span className="text-foreground/90">
              {found.why.length ? found.why.map((v) => WHY_TEXT[v] ?? v).join(", ") : "none"}
            </span>
            {(found.districtProof > 0 || found.generalProof > 0) &&
              ` (${found.districtProof} proof about ${name}, ${found.generalProof} from elsewhere)`}
            .
          </p>
          <p>
            News reasons that touch this factor:{" "}
            {d.touching.length
              ? d.touching.map((t) => `“${t.factor}” (${t.evidence})`).join("; ")
              : "none"}
            .
          </p>
        </Block>
      </div>

      <div>
        <p className="label-micro mb-2">Why they may differ here</p>
        <ul className="space-y-1.5">
          {d.differ.map((line, i) => (
            <li key={i} className="flex gap-2 text-[11.5px] leading-snug text-muted-foreground">
              <span className="mt-[6px] size-1.5 shrink-0 rounded-full bg-primary/70" aria-hidden />
              {line}
            </li>
          ))}
        </ul>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="max-w-[440px] text-[10px] leading-snug text-muted-foreground">
          Built from this district&apos;s verified research and its UIDAI/NITI rows; no
          model-written text. The Ask button gets a model-written answer from the same research.
        </p>
        <AskButton label={`Ask about ${name}`} question={districtQuestion(name, d)} />
      </div>
    </div>
  );
}
