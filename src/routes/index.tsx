import { createFileRoute } from "@tanstack/react-router";
import { RotateCw } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { WorldviewMap } from "@/components/dashboard/map/WorldviewMap";
import { PersonasPanel } from "@/components/persona/PersonasPanel";
import { DataViewPanels } from "@/components/dataview/DataViewPanels";
import { DivergenceView } from "@/components/divergence/DivergenceView";
import { HistoryPanel } from "@/components/dashboard/HistoryPanel";
import { OverviewPanel } from "@/components/dashboard/OverviewPanel";
import { QueryBar } from "@/components/dashboard/QueryBar";
import { SplitHandle, useSplit } from "@/components/dashboard/SplitHandle";
import { TopBar } from "@/components/dashboard/TopBar";
import { Button } from "@/components/ui/button";
import {
  FIXED_QUERY,
  loadDefaultRun,
  STATIC_DATA,
  STREAM_SOURCE,
  useExplorerStore,
  useQueryStream,
  useWorldviewStore,
} from "@/lib/worldview";
import { DEMO_QUERY } from "@/lib/worldview/stream/mockStream";
import type { LlmProvider, ResearchMode } from "@/lib/worldview/types";

/** Show the query card (Explore / reasoning mode / Go deeper). Off: the dashboard opens on a finished analysis. */
const SHOW_QUERY_CONTROLS = false;

const TITLE = "Pluralistic Karnataka — Worldview Explorer";
const DESCRIPTION =
  "How Karnataka's six regions — Old Mysuru, Bayaluseeme, Karavali, Malnad, Kitturu Karnataka and Kalyana Karnataka — hold different viewpoints on shared topics, answered by a male and a female persona from each region.";

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
  const activeTab = useExplorerStore((s) => s.tab);
  const setActiveTab = useExplorerStore((s) => s.setTab);
  const [query, setQuery] = useState(FIXED_QUERY);
  const [reasoningMode, setReasoningMode] = useState<ResearchMode>("medium");
  const [provider, setProvider] = useState<LlmProvider>("gemma_remote");

  const { run, cancel, retry, isStreaming, runState, error } = useQueryStream();
  const storeQuery = useWorldviewStore((s) => s.query);
  const legacyRun = useWorldviewStore((s) => s.legacyRun);

  // Auto-play the offline demo (a replayed real run) once on mount — mock source only.
  const startedRef = useRef(false);
  // Open on a finished analysis (newest saved run with Divergence + persona-similarity results).
  useEffect(() => {
    if (STREAM_SOURCE === "sse" || STATIC_DATA) void loadDefaultRun();
  }, []);

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;
    if (STREAM_SOURCE === "mock" && !STATIC_DATA) {
      setQuery(DEMO_QUERY);
      run(DEMO_QUERY);
    }
  }, [run]);

  const { split, setSplit, dragging, setDragging } = useSplit();
  // The study's topic is fixed and its results already exist, so the query card is hidden
  // (kept in the code, not deleted): flip this to bring Explore / Go deeper back.
  const showQuery =
    SHOW_QUERY_CONTROLS &&
    (activeTab === "Map" || activeTab === "Divergence" || activeTab === "Data");

  const handleExplore = (q: string) => {
    setQuery(q);
    run(q, { initialMode: reasoningMode, initialProvider: provider });
  };
  const handleGoDeeper = () => {
    const q = storeQuery ?? query;
    if (q) run(q, { deeper: true });
  };

  return (
    <main
      className={
        "relative h-screen w-screen overflow-hidden bg-background " +
        (dragging ? "select-none" : "")
      }
    >
      <TopBar activeTab={activeTab} onTabChange={setActiveTab} />

      {/* Left column: query controls, progress, and the active tab's content. */}
      <div
        className="absolute inset-y-0 left-0 z-30 flex flex-col gap-3 pr-4 pl-5 pt-[4.5rem] pb-5"
        style={{ width: `${split * 100}%` }}
      >
        {showQuery && (
          <>
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
              locked
              onGoDeeper={handleGoDeeper}
            />
            {runState === "error" && <ErrorCard message={error} onRetry={retry} />}
            {runState === "empty" && !legacyRun && <NoResultsCard />}
            {legacyRun && (
              <div className="panel-surface pointer-events-auto w-full rounded-xl px-4 py-2.5">
                <p className="text-[12px] text-muted-foreground">
                  <span className="text-foreground">Legacy run.</span> Saved by an earlier version —
                  its answer and sources are shown, but it has no Karnataka region map or
                  Story-vs-UIDAI/NITI comparison.
                </p>
              </div>
            )}
          </>
        )}

        {activeTab === "Map" && !SHOW_QUERY_CONTROLS && <OverviewPanel />}
        {activeTab === "Personas" && <PersonasPanel />}
        {activeTab === "Divergence" && <DivergenceView />}
        {activeTab === "Data" && <DataViewPanels />}
        {activeTab === "History" && <HistoryPanel onOpenRun={() => setActiveTab("Map")} />}
      </div>

      {/* Right: the static Karnataka map. */}
      <div
        className={"absolute inset-y-0 right-0 pt-14 " + (dragging ? "pointer-events-none" : "")}
        style={{ left: `${split * 100}%` }}
      >
        <div className="relative h-full w-full">
          <WorldviewMap />
        </div>
      </div>

      <SplitHandle
        split={split}
        setSplit={setSplit}
        dragging={dragging}
        setDragging={setDragging}
      />
    </main>
  );
}

function ErrorCard({ message, onRetry }: { message: string | null; onRetry: () => void }) {
  return (
    <div className="panel-surface pointer-events-auto flex w-full items-center gap-3 rounded-xl border-destructive/40 px-4 py-2.5">
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
      <div className="panel-surface pointer-events-auto w-full rounded-xl px-4 py-2.5">
        <p className="text-[12px] text-muted-foreground">
          <span className="text-foreground">Research-only result.</span> Too little
          Karnataka-specific discussion on this topic to map by region — the answer is built from{" "}
          {sourceCount} web source{sourceCount === 1 ? "" : "s"} instead.
        </p>
      </div>
    );
  }

  return (
    <div className="panel-surface pointer-events-auto w-full rounded-xl px-4 py-2.5">
      <p className="text-[12px] text-muted-foreground">
        No posts resolved for this topic. Try a broader or more current query.
      </p>
    </div>
  );
}
