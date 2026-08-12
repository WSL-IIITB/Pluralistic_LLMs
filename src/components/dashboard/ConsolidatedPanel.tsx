import { ChevronDown, ExternalLink } from "lucide-react";
import { useMemo, useState } from "react";

import {
  clusterColor,
  rgbaCss,
  useWorldviewStore,
  type AnswerSegment,
  type ClusterId,
  type QueryType,
  type ResearchDocument,
} from "@/lib/worldview";

interface Bullet {
  region: string;
  text: string;
  clusterId?: ClusterId;
  citations?: number[];
}

interface Prose {
  text: string;
  clusterId?: ClusterId;
  citations?: number[];
  /** Legacy `heading` segments keep their small-caps label styling. */
  isHeading?: boolean;
}

/**
 * The answer is rendered in three fixed zones rather than as a flat segment
 * list: a pinned one-line takeaway, a scannable bullet list, and a collapsed
 * "Full analysis" block. That keeps the panel small by default while leaving
 * the depth one click away.
 *
 * Legacy `heading`/`body` segments (the offline mock still emits them) fold
 * into the inline-prose zone so the mock keeps rendering sensibly.
 */
interface AnswerLayout {
  tldr: string | null;
  inline: Prose[];
  bullets: Bullet[];
  details: Prose[];
}

function layoutSegments(segments: AnswerSegment[]): AnswerLayout {
  const layout: AnswerLayout = { tldr: null, inline: [], bullets: [], details: [] };
  for (const seg of segments) {
    const kind = seg.kind ?? "body";
    const cites = seg.citations && seg.citations.length > 0 ? { citations: seg.citations } : {};
    const cluster = seg.clusterId ? { clusterId: seg.clusterId } : {};

    if (kind === "tldr") {
      // Concatenate if the stream chunked one takeaway across events.
      layout.tldr = layout.tldr ? `${layout.tldr} ${seg.text}` : seg.text;
    } else if (kind === "recommendation") {
      layout.bullets.push({ region: seg.region ?? "", text: seg.text, ...cluster, ...cites });
    } else if (kind === "detail") {
      layout.details.push({ text: seg.text, ...cluster, ...cites });
    } else {
      layout.inline.push({
        text: seg.text,
        ...cluster,
        ...cites,
        ...(kind === "heading" ? { isHeading: true } : {}),
      });
    }
  }
  return layout;
}

/** Superscript `[n]` markers linking to the numbered Sources entries below. */
function CitationMarks({ ids }: { ids: number[] }) {
  if (!ids.length) return null;
  return (
    <>
      {ids.map((n) => (
        <a
          key={n}
          href={`#source-${n}`}
          className="ml-0.5 inline-flex align-super text-[9px] text-primary/80 no-underline transition-colors hover:text-primary"
          aria-label={`Source ${n}`}
        >
          [{n}]
        </a>
      ))}
    </>
  );
}

export function ConsolidatedPanel() {
  const answer = useWorldviewStore((s) => s.answer);
  const queryType = useWorldviewStore((s) => s.queryType);
  const clusters = useWorldviewStore((s) => s.clusters);
  const runState = useWorldviewStore((s) => s.runState);
  const setHoveredCluster = useWorldviewStore((s) => s.setHoveredCluster);
  const researchDocuments = useWorldviewStore((s) => s.researchDocuments);
  const [detailsOpen, setDetailsOpen] = useState(false);

  const { tldr, inline, bullets, details } = useMemo(() => layoutSegments(answer), [answer]);
  const isStreaming = runState === "streaming" || runState === "connecting";
  const hasAnswer = answer.length > 0;

  return (
    <section className="panel-surface pointer-events-auto flex max-h-[calc(100vh-13rem)] w-[380px] flex-col rounded-xl">
      <header className="flex items-center justify-between border-b border-panel-border px-4 py-3">
        <h2 className="text-xs font-medium tracking-wide text-foreground">Consolidated View</h2>
        <ModeBadge queryType={queryType} />
      </header>

      {/* A plain scrolling div, not shadcn's <ScrollArea>: Radix's ScrollArea
          needs its inner Viewport to be `height:100%` of this flex item, but
          a flex item's height comes from `flex: 1 1 0%` rather than a literal
          `height` — percentages can't resolve against that, so the Viewport
          silently grows to fit all content instead of clipping/scrolling.
          Setting `overflow-y-auto` directly on the flex item sidesteps that
          entirely (no percentage-height child involved). */}
      <div className="min-h-0 flex-1 overflow-y-auto [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-border [&::-webkit-scrollbar-track]:bg-transparent">
        <div className="px-4 py-4">
          {!hasAnswer && <EmptyState isStreaming={isStreaming} />}

          {tldr && (
            <p className="text-[13px] leading-relaxed font-medium text-foreground">{tldr}</p>
          )}

          {inline.map((p, i) =>
            p.isHeading ? (
              <p key={`i-${i}`} className="label-micro mt-4 text-foreground/80">
                {p.text}
              </p>
            ) : (
              <p
                key={`i-${i}`}
                className="mt-3 text-[13px] leading-relaxed text-muted-foreground"
                onMouseEnter={
                  p.clusterId ? () => setHoveredCluster(p.clusterId ?? null) : undefined
                }
                onMouseLeave={p.clusterId ? () => setHoveredCluster(null) : undefined}
              >
                {p.text}
                {p.citations && <CitationMarks ids={p.citations} />}
              </p>
            ),
          )}

          {bullets.length > 0 && (
            <ul className="mt-3.5 space-y-2.5">
              {bullets.map((item, i) => {
                const color = item.clusterId ? clusterColor(clusters, item.clusterId) : null;
                return (
                  <li
                    key={`b-${i}`}
                    className="group -mx-1.5 flex cursor-default gap-2.5 rounded-md px-1.5 py-0.5 transition-colors hover:bg-white/5"
                    onMouseEnter={
                      item.clusterId ? () => setHoveredCluster(item.clusterId ?? null) : undefined
                    }
                    onMouseLeave={item.clusterId ? () => setHoveredCluster(null) : undefined}
                    title={
                      item.clusterId ? "Hover highlights this viewpoint on the map" : undefined
                    }
                  >
                    <span
                      className="mt-1.5 size-2 shrink-0 rounded-full ring-0 transition-all group-hover:ring-2 group-hover:ring-white/20"
                      style={{
                        backgroundColor: color ? rgbaCss(color) : "var(--muted-foreground)",
                      }}
                      aria-hidden
                    />
                    <p className="text-[13px] leading-snug text-muted-foreground">
                      {item.region && (
                        <span className="font-medium text-foreground">{item.region}: </span>
                      )}
                      {item.text}
                      {item.citations && <CitationMarks ids={item.citations} />}
                    </p>
                  </li>
                );
              })}
            </ul>
          )}

          {details.length > 0 && (
            <div className="mt-4 border-t border-panel-border pt-3">
              <button
                type="button"
                onClick={() => setDetailsOpen((v) => !v)}
                aria-expanded={detailsOpen}
                className="label-micro flex w-full items-center gap-1.5 transition-colors hover:text-foreground"
              >
                <ChevronDown
                  className={
                    "size-3 transition-transform " + (detailsOpen ? "rotate-0" : "-rotate-90")
                  }
                  aria-hidden
                />
                Full analysis
              </button>
              {detailsOpen && (
                <div className="mt-2.5 space-y-2.5">
                  {details.map((p, i) => (
                    <p
                      key={`d-${i}`}
                      className="text-[12.5px] leading-relaxed text-muted-foreground"
                      onMouseEnter={
                        p.clusterId ? () => setHoveredCluster(p.clusterId ?? null) : undefined
                      }
                      onMouseLeave={p.clusterId ? () => setHoveredCluster(null) : undefined}
                    >
                      {p.text}
                      {p.citations && <CitationMarks ids={p.citations} />}
                    </p>
                  ))}
                </div>
              )}
            </div>
          )}

          {isStreaming && hasAnswer && (
            <span
              className="mt-2 inline-block h-3.5 w-[2px] animate-pulse bg-primary align-middle"
              aria-hidden
            />
          )}

          <SourcesSection documents={researchDocuments} isStreaming={isStreaming} />
        </div>
      </div>
    </section>
  );
}

function SourcesSection({
  documents,
  isStreaming,
}: {
  documents: ResearchDocument[];
  isStreaming: boolean;
}) {
  if (documents.length === 0) {
    if (!isStreaming) return null;
    return (
      <div className="mt-4 border-t border-panel-border pt-3">
        <p className="label-micro">Sources</p>
        <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground/60">
          Gathering sources from the open web…
        </p>
      </div>
    );
  }
  return (
    <div className="mt-4 border-t border-panel-border pt-3">
      <p className="label-micro">Sources · {documents.length}</p>
      <ol className="mt-2 space-y-1.5">
        {documents.map((doc) => (
          <li key={doc.id} id={`source-${doc.id}`} className="flex gap-2 text-[12px] leading-snug">
            <span className="w-4 shrink-0 tabular-nums text-muted-foreground/60">{doc.id}.</span>
            <a
              href={doc.url}
              target="_blank"
              rel="noopener noreferrer"
              className="group min-w-0 flex-1 text-muted-foreground transition-colors hover:text-foreground"
              title={doc.url}
            >
              <span className="line-clamp-2 group-hover:underline">{doc.title}</span>
              <span className="mt-0.5 flex items-center gap-1 text-[10px] text-muted-foreground/60">
                <ExternalLink className="size-2.5 shrink-0" />
                <span className="truncate">{doc.domain}</span>
              </span>
            </a>
          </li>
        ))}
      </ol>
    </div>
  );
}

function ModeBadge({ queryType }: { queryType: QueryType }) {
  const pill = (mode: QueryType, label: string) => (
    <span
      className={
        "rounded-full px-2 py-0.5 text-[10px] " +
        (queryType === mode ? "bg-secondary text-foreground" : "text-muted-foreground")
      }
    >
      {label}
    </span>
  );
  return (
    <div
      className="flex items-center gap-1 rounded-full border border-panel-border p-0.5"
      title="Answer mode is set by the query type"
    >
      {pill("descriptive", "descriptive")}
      {pill("policy", "policy")}
    </div>
  );
}

function EmptyState({ isStreaming }: { isStreaming: boolean }) {
  if (isStreaming) {
    return (
      <div className="space-y-2.5 py-1" aria-live="polite">
        <p className="text-[13px] text-muted-foreground/70">
          Synthesizing the consolidated answer…
        </p>
        <div className="space-y-2">
          <div className="h-2.5 w-[92%] animate-pulse rounded bg-white/5" />
          <div className="h-2.5 w-[78%] animate-pulse rounded bg-white/5" />
          <div className="h-2.5 w-[85%] animate-pulse rounded bg-white/5" />
        </div>
      </div>
    );
  }
  return (
    <p className="text-[13px] leading-relaxed text-muted-foreground/70">
      Enter a topic and press <span className="text-foreground">Explore</span>. As posts are sourced
      and clustered, an all-views-inclusive answer is synthesized here — each viewpoint traceable to
      the region it came from, with citations to the sources used.
    </p>
  );
}
