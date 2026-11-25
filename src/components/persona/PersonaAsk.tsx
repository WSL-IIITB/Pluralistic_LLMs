/**
 * One question, answered twice on identical evidence: plainly, and as this persona.
 * "What is the reason for dropouts?" vs "What is the reason for dropouts, as <name>?"
 * The persona carries no study data of its own; the district's research is handed to
 * BOTH answers (or to neither), so the only difference between them is the persona.
 */

import { Loader2, Send } from "lucide-react";
import { useEffect, useState } from "react";

import {
  askWithAndWithout,
  LIBRARY_LIVE,
  rgbaCss,
  useExplorerStore,
  type AskResult,
  type LibraryPersona,
  type RGBAColor,
} from "@/lib/worldview";

const EXAMPLES: Record<"dropout" | "stunting", string[]> = {
  dropout: [
    "What is the reason for dropouts?",
    "What should the government do about water?",
    "What makes a good school?",
  ],
  stunting: [
    "Why are so many young children stunted here?",
    "What would help mothers and babies eat better?",
    "What should anganwadis do differently?",
  ],
};

/** What the shared evidence is, per topic. */
const EVIDENCE_LABEL = {
  dropout: "dropout research",
  stunting: "stunting data (NFHS-6, NITI model)",
} as const;

function AnswerCard({
  title,
  subtitle,
  answer,
  highlight,
  color,
}: {
  title: string;
  subtitle: string;
  answer: AskResult["generic"];
  highlight: Set<string>;
  color?: RGBAColor;
}) {
  return (
    <div
      className="flex min-w-0 flex-col rounded-2xl border border-panel-border bg-secondary/30 p-4"
      style={color ? { borderColor: rgbaCss(color, 0.6) } : undefined}
    >
      <p className="label-micro">{title}</p>
      <p className="mt-0.5 text-[11px] text-muted-foreground">{subtitle}</p>
      <p className="mt-3 text-[12.5px] leading-relaxed text-foreground/90">{answer.answer}</p>
      {answer.points.length > 0 && (
        <ul className="mt-3 space-y-1.5 border-t border-panel-border pt-3">
          {answer.points.map((p) => (
            <li key={p} className="flex gap-2 text-[12px] leading-snug text-foreground/85">
              <span
                className="mt-[6px] size-1.5 shrink-0 rounded-full"
                style={{
                  backgroundColor: highlight.has(p)
                    ? color
                      ? rgbaCss(color)
                      : "currentColor"
                    : "var(--muted-foreground)",
                }}
                aria-hidden
              />
              <span className={highlight.has(p) ? "font-medium text-foreground" : ""}>{p}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function PersonaAsk({ persona, color }: { persona: LibraryPersona; color: RGBAColor }) {
  const topic = useExplorerStore((s) => s.topic);
  const examples = EXAMPLES[topic];
  const [question, setQuestion] = useState(examples[0]!);
  // Switching topic swaps the suggested question (unless the user typed their own).
  useEffect(() => {
    setQuestion((q) => (Object.values(EXAMPLES).flat().includes(q) ? EXAMPLES[topic][0]! : q));
  }, [topic]);
  const [useEvidence, setUseEvidence] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AskResult | null>(null);
  const shortName = (persona.card?.name ?? persona.name).replace(/^The /, "the ");

  if (!LIBRARY_LIVE)
    return (
      <p className="rounded-xl border border-dashed border-panel-border px-4 py-3 text-[12px] leading-snug text-muted-foreground">
        Asking a persona needs the analysis backend; this published copy of the dashboard is
        read-only.
      </p>
    );

  async function run(q: string) {
    if (q.trim().length < 3 || busy) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await askWithAndWithout(persona, q.trim(), useEvidence, topic));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const added = new Set(result?.onlyWithPersona ?? []);
  const dropped = new Set(result?.onlyWithout ?? []);

  return (
    <div className="space-y-3">
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void run(question);
        }}
      >
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          maxLength={500}
          placeholder="Ask any question…"
          aria-label="Question"
          className="min-w-0 flex-1 rounded-full border border-panel-border bg-background/60 px-4 py-2 text-[13px] text-foreground outline-none focus:border-foreground/40"
        />
        <button
          type="submit"
          disabled={busy || question.trim().length < 3}
          className="flex items-center gap-1.5 rounded-full px-4 py-2 text-[12px] font-medium text-foreground transition-opacity disabled:opacity-50"
          style={{ backgroundColor: rgbaCss(color, 0.35) }}
        >
          {busy ? (
            <Loader2 className="size-3.5 animate-spin" aria-hidden />
          ) : (
            <Send className="size-3.5" aria-hidden />
          )}
          Ask both
        </button>
      </form>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <div className="flex flex-wrap gap-1.5">
          {examples.map((q) => (
            <button
              key={q}
              type="button"
              onClick={() => {
                setQuestion(q);
                void run(q);
              }}
              className="rounded-full border border-panel-border px-2.5 py-1 text-[11px] text-muted-foreground transition-colors hover:text-foreground"
            >
              {q}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-2 text-[11.5px] text-muted-foreground">
          <input
            type="checkbox"
            checked={useEvidence}
            onChange={(e) => setUseEvidence(e.target.checked)}
            className="accent-current"
          />
          Give both answers {persona.districtName}&apos;s {EVIDENCE_LABEL[topic]} as evidence
        </label>
      </div>

      {error && (
        <p className="rounded-xl border border-destructive/40 px-4 py-2.5 text-[12px] text-destructive">
          {error}
        </p>
      )}
      {busy && !result && (
        <p className="text-[12px] text-muted-foreground">
          Asking the question twice, with and without the persona…
        </p>
      )}

      {result && (
        <div className={busy ? "opacity-60 transition-opacity" : ""}>
          <div className="mb-3 flex flex-wrap items-baseline gap-x-4 gap-y-1">
            <p className="text-[12.5px] text-foreground">“{result.question}”</p>
            {result.similarity != null && (
              <p className="text-[11.5px] text-muted-foreground">
                Answers agree{" "}
                <span className="font-semibold tabular-nums text-foreground">
                  {Math.round(result.similarity * 100)}%
                </span>{" "}
                (semantic similarity) · {result.onlyWithPersona.length} point
                {result.onlyWithPersona.length === 1 ? "" : "s"} only with the persona
              </p>
            )}
          </div>
          <div className="grid gap-3 @2xl:grid-cols-2">
            <AnswerCard
              title="Without a persona"
              subtitle={
                result.evidence.used
                  ? `Evidence: ${result.evidence.district} ${EVIDENCE_LABEL[result.evidence.topic ?? "dropout"]}`
                  : "No evidence supplied"
              }
              answer={result.generic}
              highlight={dropped}
            />
            <AnswerCard
              title={`As ${shortName}`}
              subtitle={`Same evidence · persona ${result.personaVersion}`}
              answer={result.persona}
              highlight={added}
              color={color}
            />
          </div>
          <p className="mt-2 text-[10.5px] leading-snug text-muted-foreground">
            Highlighted points have no close match in the other answer. Both answers come from the
            same model ({result.provider}) with the same instructions and evidence; only the persona
            text differs.
          </p>
        </div>
      )}
    </div>
  );
}
