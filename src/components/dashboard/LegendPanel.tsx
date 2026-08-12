import { ChevronDown, ChevronRight } from "lucide-react";
import { useMemo, useState } from "react";

import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import {
  legendClusters,
  legendGroups,
  rgbaCss,
  useWorldviewStore,
  type ClusterDatum,
  type ClusterId,
  type LayerToggles,
  type StateCode,
} from "@/lib/worldview";
import { useDistrictGeo } from "./map/useDistrictGeo";

const LAYER_ITEMS: { id: keyof LayerToggles; label: string }[] = [
  { id: "columns", label: "Show 3D columns" },
  { id: "links", label: "Show deflection links" },
  { id: "splitStates", label: "Highlight split states" },
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
      className="flex cursor-default items-center gap-2.5 rounded-md px-1 py-0.5 -mx-1 transition-colors hover:bg-white/5"
      onMouseEnter={() => onHover(cluster.id)}
      onMouseLeave={() => onHover(null)}
    >
      <span
        className="size-2.5 shrink-0 rounded-[3px]"
        style={{ backgroundColor: rgbaCss(cluster.color) }}
        aria-hidden
      />
      <span className="flex-1 truncate text-[12px] text-muted-foreground">{cluster.label}</span>
      {cluster.postCount > 0 && (
        <span className="shrink-0 text-[10px] tabular-nums text-muted-foreground/50">
          {cluster.postCount.toLocaleString("en-IN")}
        </span>
      )}
    </li>
  );
}

/**
 * extrahigh mode's cluster list: grouped by state, collapsible (60-190 total
 * entries would otherwise overflow the panel as a flat list). basic/medium/
 * high never reach this — see the `isGrouped` branch in `LegendPanel` below,
 * which renders today's exact flat markup unchanged for them.
 */
function GroupedClusterList({ onHover }: { onHover: (id: ClusterId | null) => void }) {
  const clusters = useWorldviewStore((s) => s.clusters);
  const order = useWorldviewStore((s) => s.clusterOrder);
  const districts = useWorldviewStore((s) => s.districts);
  const selection = useWorldviewStore((s) => s.selection);
  const hoveredClusterId = useWorldviewStore((s) => s.hoveredClusterId);
  const { geo } = useDistrictGeo();

  const [manualExpanded, setManualExpanded] = useState<Record<StateCode, boolean>>({});
  const [filterText, setFilterText] = useState("");

  const groups = useMemo(() => legendGroups(clusters, order), [clusters, order]);

  // Which state (if any) the user is currently focused on via hover or map
  // selection — that state defaults to expanded so drilling into the map
  // doesn't require also manually expanding the matching legend section.
  const activeStateCode = useMemo<StateCode | null>(() => {
    if (hoveredClusterId) return clusters[hoveredClusterId]?.stateCode ?? null;
    if (selection.kind === "state") return selection.id;
    if (selection.kind === "district") return districts[selection.id]?.stateCode ?? null;
    return null;
  }, [hoveredClusterId, selection, clusters, districts]);

  const isExpanded = (stateCode: StateCode): boolean =>
    manualExpanded[stateCode] ?? stateCode === activeStateCode;

  const toggle = (stateCode: StateCode) =>
    setManualExpanded((prev) => ({ ...prev, [stateCode]: !isExpanded(stateCode) }));

  const filter = filterText.trim().toLowerCase();
  const visibleGroups = filter
    ? groups.filter((g) => {
        const stateName = geo?.states[g.stateCode]?.stateName ?? g.stateCode;
        if (stateName.toLowerCase().includes(filter)) return true;
        return g.clusters.some((c) => c.label.toLowerCase().includes(filter));
      })
    : groups;

  return (
    <>
      <Input
        value={filterText}
        onChange={(e) => setFilterText(e.target.value)}
        placeholder="Filter states or viewpoints…"
        className="mt-3 h-7 text-[12px]"
      />
      <ul className="mt-3 space-y-1">
        {visibleGroups.map((group) => {
          const stateName = geo?.states[group.stateCode]?.stateName ?? group.stateCode;
          const expanded = isExpanded(group.stateCode);
          return (
            <li key={group.stateCode}>
              <button
                type="button"
                onClick={() => toggle(group.stateCode)}
                className="flex w-full cursor-pointer items-center gap-1.5 rounded-md px-1 py-1 -mx-1 text-left transition-colors hover:bg-white/5"
              >
                {expanded ? (
                  <ChevronDown className="size-3 shrink-0 text-muted-foreground/60" />
                ) : (
                  <ChevronRight className="size-3 shrink-0 text-muted-foreground/60" />
                )}
                <span className="flex-1 truncate text-[12px] font-medium text-foreground/90">
                  {stateName}
                </span>
                <span className="shrink-0 text-[10px] tabular-nums text-muted-foreground/50">
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

export function LegendPanel() {
  const clusters = useWorldviewStore((s) => s.clusters);
  const order = useWorldviewStore((s) => s.clusterOrder);
  const layers = useWorldviewStore((s) => s.layers);
  const setLayer = useWorldviewStore((s) => s.setLayer);
  const setHoveredCluster = useWorldviewStore((s) => s.setHoveredCluster);

  const items = legendClusters(clusters, order);
  // Data-driven, not mode-driven: basic/medium/high's clusters never carry a
  // stateCode, so this is false for every mode except extrahigh with zero
  // extra state to thread through.
  const isGrouped = items.some((c) => c.stateCode != null);

  return (
    <aside
      className={
        isGrouped
          ? "panel-surface pointer-events-auto flex max-h-[calc(100vh-10rem)] w-[280px] flex-col rounded-xl"
          : "panel-surface pointer-events-auto w-[260px] rounded-xl"
      }
    >
      {isGrouped ? (
        <div className="min-h-0 flex-1 overflow-y-auto border-b border-panel-border px-4 py-3">
          <p className="label-micro">Viewpoint Clusters</p>
          <GroupedClusterList onHover={setHoveredCluster} />
        </div>
      ) : (
        <div className="border-b border-panel-border px-4 py-3">
          <p className="label-micro">Viewpoint Clusters</p>
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
            <span className="text-[12px] text-muted-foreground">No data → state fallback</span>
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
