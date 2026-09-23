/**
 * Viewpoint divergence: each Karnataka region answers the query twice — in its
 * persona, and without it (same question, same evidence) — and this view shows
 * how far the two replies diverge: per-region scores, the specific points that
 * differ, a reply-similarity heatmap, and a t-SNE map of every extracted point.
 */

import { ChevronDown, Table2 } from "lucide-react";
import { useState } from "react";

import {
  KARNATAKA_REGIONS,
  regionColor,
  regionShortName,
  rgbaCss,
  useWorldviewStore,
  type DivergenceModels,
  type DivergenceRegion,
  type DivergenceSummary,
  type LlmProvider,
  type RegionId,
} from "@/lib/worldview";
import { TsneScatter } from "./TsneScatter";
import { SimilarityHeatmap } from "./SimilarityHeatmap";

function fmt(v: number | undefined, digits = 2): string {
  return v === undefined ? "—" : v.toFixed(digits);
}

/** How many times more the persona moved the reply than sampling noise does. */
function effectRatio(d: DivergenceRegion): number | null {
  if (d.semanticSimilarity === undefined || d.noiseFloor === undefined) return null;
  const noise = 1 - d.noiseFloor;
  if (noise < 0.005) return null;
  return (1 - d.semanticSimilarity) / noise;
}

const MODEL_LABEL: Record<LlmProvider, string> = {
  azure_anthropic: "Claude",
  openai: "OpenAI",
  gemma_local: "Gemma (local)",
  mistral_local: "Mistral (local)",
  gemma_remote: "Gemma",
};

export function DivergenceView() {
  const divergence = useWorldviewStore((s) => s.divergence);
  const summaries = useWorldviewStore((s) => s.divergenceSummary);
  const crossModel = useWorldviewStore((s) => s.divergenceModels);
  const runState = useWorldviewStore((s) => s.runState);
  const query = useWorldviewStore((s) => s.query);
  const runProvider = useWorldviewStore((s) => s.provider);
  const models = Object.keys(divergence) as LlmProvider[];
  models.sort((a, b) => (a === runProvider ? -1 : b === runProvider ? 1 : a.localeCompare(b)));
  const [pickedModel, setPickedModel] = useState<LlmProvider | null>(null);
  const model = pickedModel && divergence[pickedModel] ? pickedModel : models[0];
  const byRegion = model ? (divergence[model] ?? {}) : {};
  const summary = model ? summaries[model] : undefined;
  const measured = KARNATAKA_REGIONS.map((r) => byRegion[r.id]).filter(
    (d): d is DivergenceRegion => !!d,
  );
  const [selected, setSelected] = useState<RegionId | null>(null);
  const active =
    measured.find((d) => d.regionId === selected) ?? measured.find((d) => d.status === "ok");
  const isStreaming = runState === "streaming" || runState === "connecting";

  return (
    <div className="absolute inset-x-5 top-40 bottom-24 flex justify-center">
      <section className="panel-surface pointer-events-auto flex w-full max-w-[1240px] flex-col overflow-hidden rounded-xl">
        <header className="border-b border-panel-border px-5 py-3.5">
          <h2 className="text-sm font-medium text-foreground">Viewpoint divergence</h2>
          <p className="mt-1 max-w-[900px] text-[12px] leading-relaxed text-muted-foreground">
            Each region answered {query ? <>“{query}”</> : "the query"} twice with the same question
            and the same collected evidence — once as its persona, once with the persona removed.
            Semantic similarity is the primary indicator (cosine of sentence-embedding means,
            all-MiniLM-L6-v2): lower means the persona changed the reply more. The noise floor is
            the similarity of two persona-free samples — the run-to-run variation a persona effect
            has to exceed. Every model gets the same prompt and evidence; points are extracted and
            embedded with the same tools for all of them.
          </p>
          {models.length > 1 && (
            <div className="mt-3 flex items-center gap-1" role="tablist" aria-label="Model">
              {models.map((m) => (
                <button
                  key={m}
                  type="button"
                  role="tab"
                  aria-selected={m === model}
                  onClick={() => setPickedModel(m)}
                  className={
                    "rounded-full px-3 py-1 text-[11px] font-medium transition-colors " +
                    (m === model
                      ? "bg-secondary text-foreground"
                      : "text-muted-foreground hover:text-foreground")
                  }
                >
                  {MODEL_LABEL[m] ?? m}
                  {m === runProvider ? " · ran this query" : ""}
                </button>
              ))}
            </div>
          )}
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4 [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-border">
          {measured.length === 0 ? (
            <p className="py-10 text-center text-[13px] text-muted-foreground/70">
              {isStreaming
                ? "Divergence is measured at the end of a run, once every region's persona reply is written…"
                : "Run a query to compare each region's persona reply with its persona-free reply."}
            </p>
          ) : (
            <>
              <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                {measured.map((d) => (
                  <ScoreTile
                    key={d.regionId}
                    d={d}
                    active={active?.regionId === d.regionId}
                    onClick={() => setSelected(d.regionId)}
                  />
                ))}
              </div>

              {crossModel && crossModel.agreements.length > 0 && <CrossModel data={crossModel} />}

              {summary && <CrossRegion summary={summary} />}

              {active && active.status === "ok" && <RegionDetail d={active} />}
            </>
          )}
        </div>
      </section>
    </div>
  );
}

function ScoreTile({
  d,
  active,
  onClick,
}: {
  d: DivergenceRegion;
  active: boolean;
  onClick: () => void;
}) {
  const ratio = effectRatio(d);
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={
        "rounded-lg border px-3.5 py-3 text-left transition-colors " +
        (active
          ? "border-foreground/40 bg-white/[0.04]"
          : "border-panel-border hover:bg-white/[0.03]")
      }
    >
      <div className="flex items-center gap-2">
        <span
          className="size-2.5 shrink-0 rounded-[3px]"
          style={{ backgroundColor: rgbaCss(regionColor(d.regionId)) }}
          aria-hidden
        />
        <span className="text-[12px] font-medium text-foreground">{d.regionName}</span>
      </div>
      {d.status === "failed" ? (
        <p className="mt-2 text-[12px] leading-snug text-muted-foreground">
          Couldn't be measured this run{d.error ? `: ${d.error}` : "."}
        </p>
      ) : (
        <>
          <p className="mt-2 text-[11px] text-muted-foreground">Semantic similarity</p>
          <p className="text-[26px] leading-tight font-semibold text-foreground">
            {fmt(d.semanticSimilarity)}
          </p>
          <p className="mt-1 text-[11px] text-muted-foreground">
            divergence {fmt(d.divergence)} · noise floor {fmt(d.noiseFloor)}
          </p>
          <p className="text-[11px] text-muted-foreground">
            point alignment {fmt(d.pointAlignment)}
          </p>
          <p className="mt-1.5 text-[11px] leading-snug text-foreground/80">
            {ratio === null
              ? "No noise-floor sample this run."
              : ratio >= 1.5
                ? `Persona moves the reply ${ratio.toFixed(1)}× more than sampling noise.`
                : "Persona effect is within sampling noise."}
          </p>
        </>
      )}
    </button>
  );
}

function CrossModel({ data }: { data: DivergenceModels }) {
  const label = (m: LlmProvider) => data.models.find((x) => x.id === m)?.label ?? m;
  const pair = data.agreements[0];
  if (!pair) return null;
  return (
    <div className="mt-4 rounded-lg border border-panel-border px-3.5 py-3">
      <p className="text-[12px] font-medium text-foreground">Across models</p>
      <p className="mt-0.5 text-[11px] leading-snug text-muted-foreground">
        Same persona, same evidence, different model. “Models agree” is the similarity between the
        two models' replies; divergence is how far each model's persona reply moved from its own
        persona-free reply.
      </p>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full border-collapse text-[11.5px]">
          <thead>
            <tr className="text-left text-muted-foreground">
              <th className="py-1.5 pr-3 font-normal">Region</th>
              <th className="py-1.5 pr-3 font-normal">Models agree · with persona</th>
              <th className="py-1.5 pr-3 font-normal">Models agree · without</th>
              <th className="py-1.5 pr-3 font-normal">Divergence · {label(pair.modelA)}</th>
              <th className="py-1.5 pr-3 font-normal">Divergence · {label(pair.modelB)}</th>
            </tr>
          </thead>
          <tbody>
            {data.agreements.map((a) => (
              <tr
                key={`${a.regionId}-${a.modelA}-${a.modelB}`}
                className="border-t border-panel-border"
              >
                <td className="py-1.5 pr-3 text-foreground">
                  <span className="inline-flex items-center gap-1.5">
                    <span
                      className="size-2 rounded-[2px]"
                      style={{ backgroundColor: rgbaCss(regionColor(a.regionId)) }}
                      aria-hidden
                    />
                    {regionShortName(a.regionId)}
                  </span>
                </td>
                <td className="py-1.5 pr-3 tabular-nums text-foreground/85">
                  {a.persona.toFixed(2)}
                </td>
                <td className="py-1.5 pr-3 tabular-nums text-foreground/85">
                  {a.baseline.toFixed(2)}
                </td>
                <td className="py-1.5 pr-3 tabular-nums text-foreground/85">
                  {a.divergenceA.toFixed(2)}
                </td>
                <td className="py-1.5 pr-3 tabular-nums text-foreground/85">
                  {a.divergenceB.toFixed(2)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function CrossRegion({ summary }: { summary: DivergenceSummary }) {
  const [showTable, setShowTable] = useState(false);
  const p = summary.personaCrossRegionSimilarity;
  const b = summary.baselineCrossRegionSimilarity;
  return (
    <div className="mt-4 grid gap-3 lg:grid-cols-[1.35fr_1fr]">
      <div className="rounded-lg border border-panel-border px-3.5 py-3">
        <p className="text-[12px] font-medium text-foreground">Every extracted point, t-SNE</p>
        <p className="mt-0.5 text-[11px] leading-snug text-muted-foreground">
          Filled = with persona, hollow = without. t-SNE keeps neighbourhoods, not distances — read
          groupings here and magnitudes from the heatmap and scores.
        </p>
        <TsneScatter points={summary.points} />
      </div>
      <div className="rounded-lg border border-panel-border px-3.5 py-3">
        <div className="flex items-start justify-between gap-2">
          <div>
            <p className="text-[12px] font-medium text-foreground">Reply similarity</p>
            <p className="mt-0.5 text-[11px] leading-snug text-muted-foreground">
              Cosine similarity between whole replies. Across regions, replies are {fmt(p)} alike
              with personas vs {fmt(b)} without
              {p !== undefined && b !== undefined
                ? p < b
                  ? " — personas make the regions' answers more distinct."
                  : " — personas don't make the regions' answers more distinct."
                : "."}
            </p>
          </div>
          <button
            type="button"
            onClick={() => setShowTable((v) => !v)}
            aria-pressed={showTable}
            className="flex shrink-0 items-center gap-1 rounded-md border border-panel-border px-2 py-1 text-[10px] text-muted-foreground hover:text-foreground"
          >
            <Table2 className="size-3" /> {showTable ? "Heatmap" : "Table"}
          </button>
        </div>
        {showTable ? <MatrixTable summary={summary} /> : <SimilarityHeatmap summary={summary} />}
      </div>
    </div>
  );
}

function MatrixTable({ summary }: { summary: DivergenceSummary }) {
  const label = (i: number) => {
    const l = summary.labels[i];
    return l ? `${l.regionName} · ${l.condition === "persona" ? "persona" : "no persona"}` : "";
  };
  return (
    <div className="mt-3 overflow-x-auto">
      <table className="w-full border-collapse text-[10.5px]">
        <thead>
          <tr>
            <th />
            {summary.labels.map((_, j) => (
              <th key={j} className="px-1 py-1 text-left font-normal text-muted-foreground">
                {label(j)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {summary.matrix.map((row, i) => (
            <tr key={i} className="border-t border-panel-border">
              <th className="px-1 py-1 text-left font-normal whitespace-nowrap text-muted-foreground">
                {label(i)}
              </th>
              {row.map((v, j) => (
                <td key={j} className="px-1 py-1 tabular-nums text-foreground/85">
                  {v.toFixed(2)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PointList({ title, hint, points }: { title: string; hint: string; points: string[] }) {
  return (
    <div className="rounded-lg border border-panel-border px-3.5 py-3">
      <p className="text-[12px] font-medium text-foreground">
        {title} <span className="font-normal text-muted-foreground">· {points.length}</span>
      </p>
      <p className="mt-0.5 text-[11px] text-muted-foreground">{hint}</p>
      {points.length === 0 ? (
        <p className="mt-2 text-[12px] text-muted-foreground/60">None.</p>
      ) : (
        <ul className="mt-2 space-y-1.5">
          {points.map((p, i) => (
            <li key={i} className="text-[12px] leading-snug text-muted-foreground">
              <span className="mr-1.5 text-muted-foreground/40">•</span>
              {p}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function RegionDetail({ d }: { d: DivergenceRegion }) {
  const [showReplies, setShowReplies] = useState(false);
  const [showShared, setShowShared] = useState(false);
  const reframed = d.reframed ?? [];
  const shared = d.shared ?? [];
  const name = regionShortName(d.regionId);

  return (
    <div className="mt-5">
      <div className="flex items-baseline gap-2">
        <span
          className="size-2.5 shrink-0 rounded-[3px]"
          style={{ backgroundColor: rgbaCss(regionColor(d.regionId)) }}
          aria-hidden
        />
        <h3 className="text-[13px] font-medium text-foreground">What changed in {name}</h3>
        {d.personaVersion && (
          <span className="text-[10px] text-muted-foreground/60">persona {d.personaVersion}</span>
        )}
      </div>
      <p className="mt-1 text-[11px] text-muted-foreground">
        Points are matched to their closest counterpart in the other reply: shared ≥ 0.75, reframed
        0.55–0.75, otherwise unique to one reply.
      </p>

      <div className="mt-3 grid gap-3 lg:grid-cols-3">
        <PointList
          title="Only with the persona"
          hint="Points the persona reply makes that the persona-free reply doesn't."
          points={d.personaOnly ?? []}
        />
        <div className="rounded-lg border border-panel-border px-3.5 py-3">
          <p className="text-[12px] font-medium text-foreground">
            Reframed <span className="font-normal text-muted-foreground">· {reframed.length}</span>
          </p>
          <p className="mt-0.5 text-[11px] text-muted-foreground">Same topic, said differently.</p>
          {reframed.length === 0 ? (
            <p className="mt-2 text-[12px] text-muted-foreground/60">None.</p>
          ) : (
            <ul className="mt-2 space-y-2.5">
              {reframed.map((m, i) => (
                <li key={i} className="text-[12px] leading-snug">
                  <p className="text-foreground/85">{m.persona}</p>
                  <p className="mt-0.5 text-muted-foreground">
                    <span className="text-muted-foreground/60">without persona: </span>
                    {m.baseline}
                  </p>
                  <p className="text-[10px] text-muted-foreground/60">
                    similarity {m.similarity.toFixed(2)}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </div>
        <PointList
          title="Only without the persona"
          hint="Points the persona reply dropped."
          points={d.baselineOnly ?? []}
        />
      </div>

      <Toggle
        open={showShared}
        onClick={() => setShowShared((v) => !v)}
        label={`Shared points · ${shared.length}`}
      />
      {showShared && (
        <ul className="mt-2 space-y-1.5">
          {shared.map((m, i) => (
            <li key={i} className="text-[12px] leading-snug text-muted-foreground">
              {m.persona}{" "}
              <span className="text-[10px] text-muted-foreground/60">
                ({m.similarity.toFixed(2)})
              </span>
            </li>
          ))}
        </ul>
      )}

      <Toggle
        open={showReplies}
        onClick={() => setShowReplies((v) => !v)}
        label="Full replies side by side"
      />
      {showReplies && (
        <div className="mt-2 grid gap-3 lg:grid-cols-2">
          <ReplyCard title="With persona" text={d.personaReply ?? ""} />
          <ReplyCard title="Without persona" text={d.baselineReply ?? ""} />
        </div>
      )}
    </div>
  );
}

function Toggle({ open, onClick, label }: { open: boolean; onClick: () => void; label: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-expanded={open}
      className="label-micro mt-4 flex items-center gap-1.5 transition-colors hover:text-foreground"
    >
      <ChevronDown
        className={"size-3 transition-transform " + (open ? "" : "-rotate-90")}
        aria-hidden
      />
      {label}
    </button>
  );
}

function ReplyCard({ title, text }: { title: string; text: string }) {
  return (
    <div className="rounded-lg border border-panel-border bg-background/30 px-3.5 py-3">
      <p className="label-micro">{title}</p>
      <p className="mt-2 text-[12px] leading-relaxed whitespace-pre-line text-muted-foreground">
        {text}
      </p>
    </div>
  );
}
