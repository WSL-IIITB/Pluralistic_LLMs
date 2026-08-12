import { createFileRoute } from "@tanstack/react-router";
import { RotateCw } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { ConsolidatedPanel } from "@/components/dashboard/ConsolidatedPanel";
import { DeflectionPanel } from "@/components/dashboard/DeflectionPanel";
import { DistrictInfoPanel } from "@/components/dashboard/DistrictInfoPanel";
import { LegendPanel } from "@/components/dashboard/LegendPanel";
import { WorldviewMap } from "@/components/dashboard/map/WorldviewMap";
import { ProgressBar } from "@/components/dashboard/ProgressBar";
import { QueryBar } from "@/components/dashboard/QueryBar";
import { TopBar, type DashboardTab } from "@/components/dashboard/TopBar";
import { Button } from "@/components/ui/button";
import { STREAM_SOURCE, useQueryStream, useWorldviewStore } from "@/lib/worldview";
import type { LlmProvider, ResearchMode } from "@/lib/worldview/types";

const TITLE = "Pluralistic India — Worldview Explorer";
const DESCRIPTION =
  "A dark cartographic dashboard exploring how regions of India hold different viewpoints on shared topics.";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: TITLE },
      { name: "description", content: DESCRIPTION },
      { property: "og:title", content: TITLE },
      { property: "og:description", content: DESCRIPTION },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Index,
});

function Index() {
  const [activeTab, setActiveTab] = useState<DashboardTab>("Map");
  const [query, setQuery] = useState("Diwali");
  const [reasoningMode, setReasoningMode] = useState<ResearchMode>("medium");
  const [provider, setProvider] = useState<LlmProvider>("azure_anthropic");

  const { run, cancel, retry, isStreaming, runState, error } = useQueryStream();
  const storeQuery = useWorldviewStore((s) => s.query);
  const selection = useWorldviewStore((s) => s.selection);

  // Auto-play the offline Diwali demo once on mount (mock source only).
  const startedRef = useRef(false);
  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;
    if (STREAM_SOURCE === "mock") run("Diwali");
  }, [run]);

  const handleExplore = (q: string) => {
    setQuery(q);
    run(q, { initialMode: reasoningMode, initialProvider: provider });
  };
  const handleGoDeeper = () => {
    const q = storeQuery ?? query;
    if (q) run(q, { deeper: true });
  };

  return (
    <main className="relative h-screen w-screen overflow-hidden bg-background">
      <WorldviewMap />

      <TopBar activeTab={activeTab} onTabChange={setActiveTab} />

      {/* Floating panel layer */}
      <div className="pointer-events-none absolute inset-0 top-14 z-30">
        <div className="absolute top-4 left-1/2 flex -translate-x-1/2 flex-col items-center gap-2">
          <QueryBar
            value={query}
            onChange={setQuery}
            onSubmit={handleExplore}
            onStop={cancel}
            isStreaming={isStreaming}
            reasoningMode={reasoningMode}
            onReasoningModeChange={setReasoningMode}
            provider={provider}
            onProviderChange={setProvider}
          />
          {runState === "error" && <ErrorCard message={error} onRetry={retry} />}
          {runState === "empty" && <NoResultsCard />}
        </div>

        {(activeTab === "Map" || activeTab === "Answer") && (
          <div className="absolute top-28 left-5">
            <ConsolidatedPanel />
          </div>
        )}

        {activeTab === "Map" && (
          <div className="absolute top-28 right-5">
            <LegendPanel />
          </div>
        )}

        {activeTab === "About" && <AboutPanel />}

        <div className="absolute bottom-6 left-1/2 flex w-max -translate-x-1/2 flex-col items-center gap-3">
          {activeTab === "Map" && selection.kind && <DistrictInfoPanel />}
          {activeTab === "Deflections" && <DeflectionPanel />}
          <ProgressBar onGoDeeper={handleGoDeeper} />
        </div>
      </div>
    </main>
  );
}

function ErrorCard({ message, onRetry }: { message: string | null; onRetry: () => void }) {
  return (
    <div className="panel-surface pointer-events-auto flex w-[min(720px,calc(100vw-3rem))] items-center gap-3 rounded-xl border-destructive/40 px-4 py-2.5">
      <p className="flex-1 truncate text-[12px] text-muted-foreground">
        {message ?? "The analysis stream failed."}
      </p>
      <Button variant="outline" size="sm" className="h-7 gap-1.5 text-[11px]" onClick={onRetry}>
        <RotateCw className="size-3" />
        Retry
      </Button>
    </div>
  );
}

/**
 * Shown when a run finished without resolving any district. Two very different
 * situations land here, so they get different copy: if the research stage DID
 * find web sources, the run genuinely succeeded — there just wasn't enough
 * India-specific social-media chatter to map, which is normal for niche policy
 * topics. Calling that "no results" (as this card used to) reads as a failure
 * when the answer panel is in fact full of cited findings.
 */
function NoResultsCard() {
  const sourceCount = useWorldviewStore((s) => s.researchDocuments.length);

  if (sourceCount > 0) {
    return (
      <div className="panel-surface pointer-events-auto w-[min(720px,calc(100vw-3rem))] rounded-xl px-4 py-2.5">
        <p className="text-[12px] text-muted-foreground">
          <span className="text-foreground">Research-only result.</span> Too little India-specific
          social-media discussion on this topic to map by district — the answer is built from{" "}
          {sourceCount} web source{sourceCount === 1 ? "" : "s"} instead.
        </p>
      </div>
    );
  }

  return (
    <div className="panel-surface pointer-events-auto w-[min(720px,calc(100vw-3rem))] rounded-xl px-4 py-2.5">
      <p className="text-[12px] text-muted-foreground">
        No posts resolved for this topic. Try a broader or more current query.
      </p>
    </div>
  );
}

function AboutPanel() {
  return (
    <div className="absolute top-28 left-1/2 w-[520px] max-w-[calc(100vw-3rem)] -translate-x-1/2">
      <section className="panel-surface pointer-events-auto rounded-xl p-5">
        <p className="label-micro">About</p>
        <p className="mt-3 text-[13px] leading-relaxed text-muted-foreground">
          Worldview Explorer samples public conversation on a topic across Reddit and YouTube,
          resolves each post to an Indian district, and clusters the underlying viewpoints so that
          regional differences become legible on the map. For each pair of co-occurring viewpoints
          it extracts the <span className="text-foreground">point of deflection</span> — the single
          proposition they fork on — and synthesizes an all-views-inclusive answer.
        </p>
        <p className="mt-3 text-[13px] leading-relaxed text-muted-foreground">
          The map builds progressively as the agent graph streams results. District colour is the
          dominant viewpoint; column height is post volume; dimmed areas fell back to their parent
          state. This build ships an offline demo run — point it at a live backend in{" "}
          <code className="rounded bg-white/5 px-1 py-0.5 text-[11px]">stream/config.ts</code>.
        </p>
      </section>
    </div>
  );
}
