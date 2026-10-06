import { ChevronDown, ChevronRight, Minimize2, Maximize2 } from "lucide-react";
import { useMemo, useState } from "react";

import { CollapseButton, CollapsedPill } from "@/components/dashboard/CollapseToggle";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { useCollapsible } from "@/hooks/use-collapsible";
import {
  legendClusters,
  legendGroupsByRegion,
  regionColor,
  rgbaCss,
  useWorldviewStore,
  type ClusterDatum,
  type ClusterId,
  type LayerToggles,
} from "@/lib/worldview";

interface Group {
  key: string;
  label: string;
  clusters: ClusterDatum[];
  totalPostCount: number;
}

const LAYER_ITEMS: { id: keyof LayerToggles; label: string }[] = [
  { id: "columns", label: "Show 3D columns" },
  { id: "links", label: "Show deflection links" },
  { id: "splitRegions", label: "Highlight split regions" },
];

function ClusterRow({
  cluster,
  onHover,
}: {
  cluster: ClusterDatum;
  onHover: (id: ClusterId | null) => void;
}) {
  return (
    <li
      className="flex cursor-default items-start gap-2.5 rounded-md px-1 py-1 -mx-1 transition-colors hover:bg-white/5"
      onMouseEnter={() => onHover(cluster.id)}
      onMouseLeave={() => onHover(null)}
    >
      <span
        className="mt-[3px] size-2.5 shrink-0 rounded-[3px]"
        style={{ backgroundColor: rgbaCss(cluster.color) }}
        aria-hidden
      />
      <span className="flex-1 text-[12px] leading-snug text-muted-foreground" title={cluster.label}>
        {cluster.label}
      </span>
      {cluster.postCount > 0 && (
        <span className="mt-[1px] shrink-0 text-[10px] tabular-nums text-muted-foreground/50">
          {cluster.postCount.toLocaleString("en-IN")}
        </span>
      )}
    </li>
  );
}

/** Cluster list grouped by Karnataka region, collapsible per region. */
function GroupedClusterList({
  groups,
  activeGroupKey,
  filterPlaceholder,
  onHover,
}: {
  groups: Group[];
  activeGroupKey: string | null;
  filterPlaceholder: string;
  onHover: (id: ClusterId | null) => void;
}) {
  const [manualExpanded, setManualExpanded] = useState<Record<string, boolean>>({});
  const [filterText, setFilterText] = useState("");

  // Whichever group (region or state) the user is currently focused on via
  // hover or map selection defaults to expanded, so drilling into the map
  // doesn't require also manually expanding the matching legend section.
  const isExpanded = (key: string): boolean => manualExpanded[key] ?? key === activeGroupKey;
  const toggle = (key: string) =>
    setManualExpanded((prev) => ({ ...prev, [key]: !isExpanded(key) }));

  const filter = filterText.trim().toLowerCase();
  const visibleGroups = filter
    ? groups.filter((g) => {
        if (g.label.toLowerCase().includes(filter)) return true;
        return g.clusters.some((c) => c.label.toLowerCase().includes(filter));
      })
    : groups;

  return (
    <>
      <Input
        value={filterText}
        onChange={(e) => setFilterText(e.target.value)}
        placeholder={filterPlaceholder}
        className="mt-3 h-7 text-[12px]"
      />
      <ul className="mt-3 space-y-1">
        {visibleGroups.map((group) => {
          const expanded = isExpanded(group.key);
          return (
            <li key={group.key}>
              <button
                type="button"
                onClick={() => toggle(group.key)}
                className="flex w-full cursor-pointer items-start gap-1.5 rounded-md px-1 py-1 -mx-1 text-left transition-colors hover:bg-white/5"
              >
                {expanded ? (
                  <ChevronDown className="mt-[3px] size-3 shrink-0 text-muted-foreground/60" />
                ) : (
                  <ChevronRight className="mt-[3px] size-3 shrink-0 text-muted-foreground/60" />
                )}
                <span
                  className="mt-[3px] size-2.5 shrink-0 rounded-[3px]"
                  style={{ backgroundColor: rgbaCss(regionColor(group.key)) }}
                  aria-hidden
                />
                <span
                  className="flex-1 text-[12px] leading-snug font-medium text-foreground/90"
                  title={group.label}
                >
                  {group.label}
                </span>
                <span className="mt-[1px] shrink-0 text-[10px] tabular-nums text-muted-foreground/50">
                  {group.clusters.length} · {group.totalPostCount.toLocaleString("en-IN")}
                </span>
              </button>
              {expanded && (
                <ul className="mt-1 space-y-2 pl-[18px]">
                  {group.clusters.map((cluster) => (
                    <ClusterRow key={cluster.id} cluster={cluster} onHover={onHover} />
                  ))}
                </ul>
              )}
            </li>
          );
        })}
      </ul>
    </>
  );
}

function PanelHeader({
  isWide,
  onToggleWide,
  onCollapse,
}: {
  isWide: boolean;
  onToggleWide: () => void;
  onCollapse: () => void;
}) {
  return (
    <div className="flex items-center justify-between gap-2">
      <p className="label-micro">Viewpoint Clusters</p>
      <div className="flex shrink-0 items-center gap-1">
        <button
          type="button"
          onClick={onToggleWide}
          aria-label={isWide ? "Narrow this panel" : "Widen this panel so labels aren't cut off"}
          title={isWide ? "Narrow panel" : "Widen panel"}
          className="flex size-5 shrink-0 items-center justify-center rounded-md text-muted-foreground/60 transition-colors hover:bg-white/10 hover:text-foreground"
        >
          {isWide ? <Minimize2 className="size-3" /> : <Maximize2 className="size-3" />}
        </button>
        <CollapseButton onClick={onCollapse} label="Collapse legend" />
      </div>
    </div>
  );
}

export function LegendPanel() {
  const clusters = useWorldviewStore((s) => s.clusters);
  const order = useWorldviewStore((s) => s.clusterOrder);
  const regions = useWorldviewStore((s) => s.regions);
  const selection = useWorldviewStore((s) => s.selection);
  const hoveredClusterId = useWorldviewStore((s) => s.hoveredClusterId);
  const layers = useWorldviewStore((s) => s.layers);
  const setLayer = useWorldviewStore((s) => s.setLayer);
  const setHoveredCluster = useWorldviewStore((s) => s.setHoveredCluster);
  const [isWide, setIsWide] = useState(false);
  const { collapsed, expand, collapse } = useCollapsible();

  const items = legendClusters(clusters, order);
  const isGrouped = items.some((c) => c.regionId != null);

  const groups = useMemo<Group[]>(
    () =>
      isGrouped
        ? legendGroupsByRegion(clusters, order, regions).map((g) => ({
            key: g.regionId,
            label: g.regionName,
            clusters: g.clusters,
            totalPostCount: g.totalPostCount,
          }))
        : [],
    [isGrouped, clusters, order, regions],
  );

  const activeGroupKey = useMemo<string | null>(() => {
    if (hoveredClusterId) return clusters[hoveredClusterId]?.regionId ?? null;
    if (selection.kind === "region") return selection.id;
    return null;
  }, [hoveredClusterId, selection, clusters]);

  if (collapsed) {
    return (
      <CollapsedPill onClick={expand} label="Show legend">
        Viewpoint Clusters
      </CollapsedPill>
    );
  }

  return (
    <aside
      className={
        isGrouped
          ? `panel-surface pointer-events-auto flex max-h-[calc(100vh-10rem)] flex-col rounded-xl transition-[width] duration-150 ${isWide ? "w-[420px]" : "w-[280px]"}`
          : `panel-surface pointer-events-auto rounded-xl transition-[width] duration-150 ${isWide ? "w-[400px]" : "w-[260px]"}`
      }
    >
      {isGrouped ? (
        <div className="min-h-0 flex-1 overflow-y-auto border-b border-panel-border px-4 py-3">
          <PanelHeader
            isWide={isWide}
            onToggleWide={() => setIsWide((v) => !v)}
            onCollapse={collapse}
          />
          <GroupedClusterList
            groups={groups}
            activeGroupKey={activeGroupKey}
            filterPlaceholder="Filter regions or viewpoints…"
            onHover={setHoveredCluster}
          />
        </div>
      ) : (
        <div className="border-b border-panel-border px-4 py-3">
          <PanelHeader
            isWide={isWide}
            onToggleWide={() => setIsWide((v) => !v)}
            onCollapse={collapse}
          />
          {items.length === 0 ? (
            <p className="mt-3 text-[12px] leading-snug text-muted-foreground/70">
              Clusters appear here as distinct viewpoints are found.
            </p>
          ) : (
            <ul className="mt-3 space-y-2">
              {items.map((cluster) => (
                <ClusterRow key={cluster.id} cluster={cluster} onHover={setHoveredCluster} />
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="border-b border-panel-border px-4 py-3">
        <p className="label-micro">Data Confidence</p>
        <ul className="mt-3 space-y-2">
          <li className="flex items-center gap-2.5">
            <span className="size-2.5 rounded-[3px] bg-cluster-2" aria-hidden />
            <span className="text-[12px] text-muted-foreground">High</span>
          </li>
          <li className="flex items-center gap-2.5">
            <span className="size-2.5 rounded-[3px] bg-cluster-2/40" aria-hidden />
            <span className="text-[12px] text-muted-foreground">Low</span>
          </li>
          <li className="flex items-center gap-2.5">
            <span className="hatched size-2.5 rounded-[3px] bg-muted" aria-hidden />
            <span className="text-[12px] text-muted-foreground">Statewide only (no region)</span>
          </li>
        </ul>
      </div>

      <div className="px-4 py-3">
        <p className="label-micro">Layers</p>
        <ul className="mt-3 space-y-2.5">
          {LAYER_ITEMS.map((layer) => (
            <li key={layer.id} className="flex items-center gap-2.5">
              <Checkbox
                id={`layer-${layer.id}`}
                checked={layers[layer.id]}
                onCheckedChange={(checked) => setLayer(layer.id, checked === true)}
                className="size-3.5"
              />
              <label
                htmlFor={`layer-${layer.id}`}
                className="text-[12px] text-muted-foreground select-none"
              >
                {layer.label}
              </label>
            </li>
          ))}
        </ul>
      </div>
    </aside>
  );
}
