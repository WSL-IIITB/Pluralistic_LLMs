import { ExternalLink, X } from "lucide-react";

import {
  clusterColor,
  personaVariantLabel,
  regionColor,
  regionEntropy,
  regionMeta,
  regionShortName,
  rgbaCss,
  useWorldviewStore,
  type ClusterDatum,
  type ClusterId,
  type ConfidenceTier,
  type RegionStatsDatum,
  type ResolutionMethod,
  type SamplePost,
} from "@/lib/worldview";

const METHOD_LABEL: Record<ResolutionMethod, string> = {
  city_subreddit: "city subreddit",
  place_ner: "place mention",
  script_language: "script / language",
  llm_geolocation: "LLM geolocation",
  state_fallback: "statewide fallback",
  search_context: "search context",
  unresolved: "unresolved",
};

const CONFIDENCE_STYLE: Record<ConfidenceTier, string> = {
  high: "text-emerald-300/90 border-emerald-400/30",
  medium: "text-amber-300/90 border-amber-400/30",
  low: "text-muted-foreground border-panel-border",
};

export function RegionInfoPanel() {
  const selection = useWorldviewStore((s) => s.selection);
  const regionStats = useWorldviewStore((s) => s.regionStats);
  const clusters = useWorldviewStore((s) => s.clusters);
  const regions = useWorldviewStore((s) => s.regions);
  const answer = useWorldviewStore((s) => s.answer);
  const clearSelection = useWorldviewStore((s) => s.clearSelection);

  if (selection.kind !== "region") return null;
  const regionId = selection.id;
  const stats = regionStats[regionId];
  const personaTldrs = answer.filter((a) => a.regionId === regionId && a.kind === "tldr");

  return (
    <section className="panel-surface pointer-events-auto flex max-h-[46vh] w-[360px] flex-col rounded-xl">
      <header className="flex items-start justify-between gap-2 border-b border-panel-border px-4 py-3">
        <div className="min-w-0">
          <p className="label-micro">Persona region</p>
          <h2 className="flex items-center gap-2 text-sm leading-snug font-medium text-foreground">
            <span
              className="size-2.5 shrink-0 rounded-[3px]"
              style={{ backgroundColor: rgbaCss(regionColor(regionId)) }}
              aria-hidden
            />
            {regionMeta(regionId)?.name ?? regionShortName(regionId)}
          </h2>
          {regions[regionId]?.districtIds && (
            <p className="text-[11px] text-muted-foreground/70">
              {regions[regionId]?.districtIds.length} districts
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

      <div className="min-h-0 flex-1 overflow-y-auto [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-border [&::-webkit-scrollbar-track]:bg-transparent">
        <div className="space-y-3 px-4 py-4">
          {personaTldrs.length > 0 && (
            <div className="space-y-2">
              {personaTldrs.map((seg, i) => (
                <div key={seg.personaId ?? i}>
                  <p className="label-micro">
                    {personaVariantLabel(regionId, seg.personaId) || "Persona reply"}
                  </p>
                  <p className="mt-1 text-[12.5px] leading-relaxed text-foreground">{seg.text}</p>
                </div>
              ))}
            </div>
          )}
          {stats ? (
            <RegionBody stats={stats} clusters={clusters} />
          ) : (
            <p className="text-[13px] text-muted-foreground/70">No posts have resolved here yet.</p>
          )}
        </div>
      </div>
    </section>
  );
}

function RegionBody({
  stats,
  clusters,
}: {
  stats: RegionStatsDatum;
  clusters: Record<ClusterId, ClusterDatum>;
}) {
  const dominant = stats.clusterId ? clusters[stats.clusterId] : undefined;
  const mix = Object.entries(stats.clusterVolumes).sort((a, b) => b[1] - a[1]);
  const split = regionEntropy(stats) >= 0.5 && mix.length >= 2;

  return (
    <>
      {dominant && (
        <div>
          <p className="label-micro">Dominant viewpoint</p>
          <div className="mt-1.5 flex items-center gap-2">
            <span
              className="size-2.5 rounded-[3px]"
              style={{ backgroundColor: rgbaCss(dominant.color) }}
              aria-hidden
            />
            <span className="text-[13px] font-medium text-foreground">{dominant.label}</span>
          </div>
          {dominant.summary && (
            <p className="mt-1.5 text-[12px] leading-relaxed text-muted-foreground">
              {dominant.summary}
            </p>
          )}
        </div>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={
            "rounded-full border px-2 py-0.5 text-[10px] " + CONFIDENCE_STYLE[stats.confidence]
          }
        >
          {stats.confidence} confidence
        </span>
        <MetaTag>{stats.volume.toLocaleString("en-IN")} posts</MetaTag>
        <MetaTag>{mix.length} viewpoints</MetaTag>
        <MetaTag>mostly {METHOD_LABEL[stats.method]}</MetaTag>
        {split && (
          <span className="rounded-full border border-primary/40 bg-primary/10 px-2 py-0.5 text-[10px] text-primary">
            split region
          </span>
        )}
      </div>

      <div>
        <p className="label-micro">Viewpoint mix</p>
        <ul className="mt-2 space-y-1.5">
          {mix.map(([id, vol]) => (
            <li key={id} className="flex items-start gap-2">
              <span
                className="mt-[5px] size-2 shrink-0 rounded-full"
                style={{ backgroundColor: rgbaCss(clusterColor(clusters, id)) }}
                aria-hidden
              />
              <span className="flex-1 text-[12px] leading-snug text-muted-foreground">
                {clusters[id]?.label ?? id}
              </span>
              <span className="mt-[2px] text-[11px] tabular-nums text-muted-foreground/60">
                {stats.volume > 0 ? Math.round((vol / stats.volume) * 100) : 0}%
              </span>
            </li>
          ))}
        </ul>
      </div>
      <SamplePosts posts={stats.samplePosts} clusters={clusters} />
    </>
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
  clusters: Record<ClusterId, ClusterDatum>;
}) {
  if (posts.length === 0) return null;
  return (
    <div>
      <p className="label-micro">Sample posts (paraphrased)</p>
      <ul className="mt-2 space-y-2">
        {posts.slice(0, 4).map((post) => (
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
              <span className="text-[10px] tracking-wide text-muted-foreground/60 uppercase">
                {post.platform === "research" ? "news / official" : post.platform}
              </span>
              {post.url && (
                <a
                  href={post.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  aria-label="View source"
                  title="View source"
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
