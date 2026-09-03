import { ExternalLink, X } from "lucide-react";
import { useMemo } from "react";

import {
  clusterColor,
  computeStateDiversity,
  rgbaCss,
  splitStateCodes,
  useWorldviewStore,
  type ClusterId,
  type ConfidenceTier,
  type ResolutionMethod,
  type SamplePost,
} from "@/lib/worldview";
import { useDistrictGeo } from "./map/useDistrictGeo";

const METHOD_LABEL: Record<ResolutionMethod, string> = {
  city_subreddit: "city subreddit",
  place_ner: "place mention (NER)",
  script_language: "script / language",
  llm_geolocation: "LLM geolocation",
  state_fallback: "state fallback",
  unresolved: "unresolved",
};

const CONFIDENCE_STYLE: Record<ConfidenceTier, string> = {
  high: "text-emerald-300/90 border-emerald-400/30",
  medium: "text-amber-300/90 border-amber-400/30",
  low: "text-muted-foreground border-panel-border",
};

export function DistrictInfoPanel() {
  const selection = useWorldviewStore((s) => s.selection);
  const districts = useWorldviewStore((s) => s.districts);
  const clusters = useWorldviewStore((s) => s.clusters);
  const regions = useWorldviewStore((s) => s.regions);
  const clearSelection = useWorldviewStore((s) => s.clearSelection);
  const { geo } = useDistrictGeo();

  const diversity = useMemo(() => computeStateDiversity(districts), [districts]);
  const splitStates = useMemo(() => splitStateCodes(diversity), [diversity]);

  if (!selection.kind) return null;

  const selectedRegionId =
    selection.kind === "district" ? districts[selection.id]?.regionId : undefined;
  const selectedRegionName = selectedRegionId ? regions[selectedRegionId]?.name : undefined;

  return (
    <section className="panel-surface pointer-events-auto flex max-h-[46vh] w-[340px] flex-col rounded-xl">
      <header className="flex items-start justify-between gap-2 border-b border-panel-border px-4 py-3">
        <div className="min-w-0">
          <p className="label-micro">{selection.kind === "district" ? "District" : "State"}</p>
          <h2 className="text-sm leading-snug font-medium text-foreground">
            {selection.kind === "district"
              ? (geo?.districts[selection.id]?.name ?? selection.id)
              : (geo?.states[selection.id]?.stateName ?? selection.id)}
          </h2>
          {selection.kind === "district" && (
            <p className="text-[11px] text-muted-foreground/70">
              {geo?.districts[selection.id]?.stateName ?? ""}
              {selectedRegionName ? ` · ${selectedRegionName}` : ""}
            </p>
          )}
        </div>
        <button
          type="button"
          aria-label="Close"
          onClick={clearSelection}
          className="flex size-6 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:text-foreground"
        >
          <X className="size-4" />
        </button>
      </header>

      {/* A plain scrolling div, not shadcn's <ScrollArea>: Radix's ScrollArea
          Viewport wraps its child in an internal `display: table` element to
          measure scrollable content, which sizes that wrapper to its content's
          natural (unwrapped) width instead of the panel's — long labels then
          overflow past `w-[340px]` and get hard-clipped by the ancestor's
          `overflow-hidden`, with no ellipsis. Plain `overflow-y-auto` has no
          such wrapper, so text wraps normally. See ConsolidatedPanel.tsx for
          the same fix (that one's for a different, height-related bug, but
          the "skip ScrollArea" remedy is identical). */}
      <div className="min-h-0 flex-1 overflow-y-auto [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-border [&::-webkit-scrollbar-track]:bg-transparent">
        <div className="space-y-3 px-4 py-4">
          {selection.kind === "district" ? (
            <DistrictBody districtId={selection.id} clusters={clusters} districts={districts} />
          ) : (
            <StateBody
              stateCode={selection.id}
              clusters={clusters}
              diversity={diversity}
              isSplit={splitStates.has(selection.id)}
            />
          )}
        </div>
      </div>
    </section>
  );
}

function DistrictBody({
  districtId,
  clusters,
  districts,
}: {
  districtId: string;
  clusters: ReturnType<typeof useWorldviewStore.getState>["clusters"];
  districts: ReturnType<typeof useWorldviewStore.getState>["districts"];
}) {
  const d = districts[districtId];
  if (!d || !d.clusterId) {
    return <p className="text-[13px] text-muted-foreground/70">No posts have resolved here yet.</p>;
  }
  const cluster = clusters[d.clusterId];
  const posts: SamplePost[] =
    d.samplePosts && d.samplePosts.length > 0
      ? d.samplePosts
      : (cluster?.representativePosts ?? []);

  return (
    <>
      <Frame
        clusterId={d.clusterId}
        label={cluster?.label ?? d.clusterId}
        summary={cluster?.summary}
      />
      <div className="flex flex-wrap items-center gap-2">
        <ConfidenceBadge tier={d.confidence} />
        <MetaTag>{d.volume.toLocaleString("en-IN")} posts</MetaTag>
        <MetaTag>{METHOD_LABEL[d.method]}</MetaTag>
        {d.isStateFallback && <MetaTag>state fallback</MetaTag>}
      </div>
      <SamplePosts posts={posts} clusters={clusters} />
    </>
  );
}

function StateBody({
  stateCode,
  clusters,
  diversity,
  isSplit,
}: {
  stateCode: string;
  clusters: ReturnType<typeof useWorldviewStore.getState>["clusters"];
  diversity: ReturnType<typeof computeStateDiversity>;
  isSplit: boolean;
}) {
  const div = diversity[stateCode];
  if (!div || !div.dominantClusterId) {
    return (
      <p className="text-[13px] text-muted-foreground/70">
        No posts have resolved in this state yet.
      </p>
    );
  }
  const dominant = clusters[div.dominantClusterId];
  const mix = Object.keys(div.clusterVolumes)
    .map((id) => ({ id, vol: div.clusterVolumes[id] ?? 0 }))
    .sort((a, b) => b.vol - a.vol)
    .slice(0, 4);

  return (
    <>
      <Frame
        clusterId={div.dominantClusterId}
        label={dominant?.label ?? div.dominantClusterId}
        summary={dominant?.summary}
      />
      <div className="flex flex-wrap items-center gap-2">
        {isSplit && (
          <span className="rounded-full border border-primary/40 bg-primary/10 px-2 py-0.5 text-[10px] text-primary">
            split state
          </span>
        )}
        <MetaTag>{div.totalVolume.toLocaleString("en-IN")} posts</MetaTag>
        <MetaTag>{div.clustersPresent} viewpoints</MetaTag>
      </div>

      <div>
        <p className="label-micro">Viewpoint mix</p>
        <ul className="mt-2 space-y-1.5">
          {mix.map(({ id, vol }) => {
            const share = div.totalVolume > 0 ? Math.round((vol / div.totalVolume) * 100) : 0;
            return (
              <li key={id} className="flex items-start gap-2">
                <span
                  className="mt-[5px] size-2 shrink-0 rounded-full"
                  style={{ backgroundColor: rgbaCss(clusterColor(clusters, id)) }}
                  aria-hidden
                />
                <span
                  className="flex-1 text-[12px] leading-snug text-muted-foreground"
                  title={clusters[id]?.label ?? id}
                >
                  {clusters[id]?.label ?? id}
                </span>
                <span className="mt-[2px] text-[11px] tabular-nums text-muted-foreground/60">
                  {share}%
                </span>
              </li>
            );
          })}
        </ul>
      </div>
      <p className="text-[11px] leading-relaxed text-muted-foreground/60">
        Click a district to drill in.
      </p>
    </>
  );
}

function Frame({
  clusterId,
  label,
  summary,
}: {
  clusterId: ClusterId;
  label: string;
  summary?: string | undefined;
}) {
  const clusters = useWorldviewStore((s) => s.clusters);
  return (
    <div>
      <p className="label-micro">Dominant frame</p>
      <div className="mt-1.5 flex items-center gap-2">
        <span
          className="size-2.5 rounded-[3px]"
          style={{ backgroundColor: rgbaCss(clusterColor(clusters, clusterId)) }}
          aria-hidden
        />
        <span className="text-[13px] font-medium text-foreground">{label}</span>
      </div>
      {summary && (
        <p className="mt-1.5 text-[12px] leading-relaxed text-muted-foreground">{summary}</p>
      )}
    </div>
  );
}

function ConfidenceBadge({ tier }: { tier: ConfidenceTier }) {
  return (
    <span className={"rounded-full border px-2 py-0.5 text-[10px] " + CONFIDENCE_STYLE[tier]}>
      {tier} confidence
    </span>
  );
}

function MetaTag({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-full border border-panel-border px-2 py-0.5 text-[10px] text-muted-foreground">
      {children}
    </span>
  );
}

function SamplePosts({
  posts,
  clusters,
}: {
  posts: SamplePost[];
  clusters: ReturnType<typeof useWorldviewStore.getState>["clusters"];
}) {
  if (posts.length === 0) return null;
  return (
    <div>
      <p className="label-micro">Sample posts (paraphrased)</p>
      <ul className="mt-2 space-y-2">
        {posts.slice(0, 3).map((post) => (
          <li
            key={post.id}
            className="rounded-lg border border-panel-border bg-background/40 p-2.5"
          >
            <div className="mb-1 flex items-center gap-1.5">
              <span
                className="size-1.5 rounded-full"
                style={{ backgroundColor: rgbaCss(clusterColor(clusters, post.clusterId)) }}
                aria-hidden
              />
              <span className="text-[10px] uppercase tracking-wide text-muted-foreground/60">
                {post.platform}
              </span>
              {post.url && (
                <a
                  href={post.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  aria-label="View source post"
                  title="View source post"
                  className="ml-auto text-muted-foreground/50 transition-colors hover:text-foreground"
                >
                  <ExternalLink className="size-3" />
                </a>
              )}
            </div>
            <p className="text-[12px] leading-snug text-muted-foreground">{post.paraphrase}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
