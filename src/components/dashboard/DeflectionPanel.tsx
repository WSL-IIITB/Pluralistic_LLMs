import { useEffect } from "react";

import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  clusterColor,
  legendClusters,
  legendGroups,
  rgbaCss,
  useWorldviewStore,
  type ClusterDatum,
  type ClusterId,
  type LegendGroup,
} from "@/lib/worldview";
import { useDistrictGeo } from "./map/useDistrictGeo";

export function DeflectionPanel() {
  const clusters = useWorldviewStore((s) => s.clusters);
  const order = useWorldviewStore((s) => s.clusterOrder);
  const deflections = useWorldviewStore((s) => s.deflections);
  const pair = useWorldviewStore((s) => s.deflectionPair);
  const setDeflectionPair = useWorldviewStore((s) => s.setDeflectionPair);
  const setHoveredCluster = useWorldviewStore((s) => s.setHoveredCluster);
  const { geo } = useDistrictGeo();

  const items = legendClusters(clusters, order);
  // Data-driven, not mode-driven — see LegendPanel.tsx's identical check.
  const isGrouped = items.some((c) => c.stateCode != null);
  const groups = isGrouped ? legendGroups(clusters, order) : [];

  // Preselect the first discovered deflection so the panel + arc show something.
  useEffect(() => {
    if (deflections.length > 0 && (!pair.a || !pair.b)) {
      const first = deflections[0];
      if (first) setDeflectionPair(first.clusterA, first.clusterB);
    }
  }, [deflections, pair.a, pair.b, setDeflectionPair]);

  const matched = deflections.find(
    (d) =>
      (d.clusterA === pair.a && d.clusterB === pair.b) ||
      (d.clusterA === pair.b && d.clusterB === pair.a),
  );

  const disabled = items.length < 2;

  return (
    <section
      className="panel-surface pointer-events-auto w-[720px] max-w-[calc(100vw-3rem)] rounded-xl p-4"
      onMouseLeave={() => setHoveredCluster(null)}
    >
      <div className="flex items-center justify-between">
        <h2 className="text-xs font-medium tracking-wide text-foreground">Deflection Analysis</h2>
        <span className="rounded-full border border-panel-border px-2 py-0.5 text-[10px] text-muted-foreground">
          level: {matched?.level ?? "—"}
        </span>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-3">
        <ClusterSelect
          label="Viewpoint A"
          value={pair.a}
          items={items}
          groups={groups}
          isGrouped={isGrouped}
          stateNameFor={(code) => geo?.states[code]?.stateName ?? code}
          disabled={disabled}
          onChange={(id) => setDeflectionPair(id, pair.b)}
        />
        <ClusterSelect
          label="Viewpoint B"
          value={pair.b}
          items={items}
          groups={groups}
          isGrouped={isGrouped}
          stateNameFor={(code) => geo?.states[code]?.stateName ?? code}
          disabled={disabled}
          onChange={(id) => setDeflectionPair(pair.a, id)}
        />
      </div>

      <div className="mt-3 rounded-lg border border-panel-border bg-background/40 p-3">
        {disabled ? (
          <p className="text-[12px] text-muted-foreground/70">
            Run a query — once two or more viewpoints are found, pick a pair to see where they fork.
          </p>
        ) : matched ? (
          <>
            <div className="flex flex-wrap items-center gap-3 text-[13px]">
              <ClusterChip
                cluster={clusters[matched.clusterA]}
                id={matched.clusterA}
                unit={matched.unitA}
              />
              <span className="text-muted-foreground/50">↔</span>
              <ClusterChip
                cluster={clusters[matched.clusterB]}
                id={matched.clusterB}
                unit={matched.unitB}
              />
            </div>
            <p className="mt-2 text-[12px] leading-relaxed text-muted-foreground">
              <span className="label-micro mr-1">Point of deflection</span>
              {matched.point}
            </p>
          </>
        ) : (
          <p className="text-[12px] text-muted-foreground/70">
            No point of deflection recorded between these two viewpoints. Try another pair.
          </p>
        )}
      </div>
    </section>
  );
}

function ClusterChip({
  cluster,
  id,
  unit,
}: {
  cluster: ClusterDatum | undefined;
  id: ClusterId;
  unit: string;
}) {
  const label = cluster?.label ?? id;
  const color = cluster?.color ?? [130, 130, 140];
  return (
    <span className="flex items-center gap-2">
      <span
        className="size-2 rounded-full"
        style={{ backgroundColor: rgbaCss(color) }}
        aria-hidden
      />
      <span className="text-foreground">{label}</span>
      {unit && <span className="text-[11px] text-muted-foreground/60">· {unit}</span>}
    </span>
  );
}

/** A cluster's swatch + label, with an optional `· {qualifier}` suffix so two
 * same-labeled clusters from different states stay distinguishable — needed
 * in BOTH the open dropdown list and the collapsed trigger, since Radix
 * projects the selected item's full row content into the trigger, where a
 * `SelectGroup`'s own header is no longer visible. */
function ClusterOptionRow({ cluster, qualifier }: { cluster: ClusterDatum; qualifier?: string }) {
  return (
    <span className="flex min-w-0 items-center gap-2">
      <span
        className="size-2 shrink-0 rounded-full"
        style={{ backgroundColor: rgbaCss(cluster.color) }}
        aria-hidden
      />
      <span className="truncate">{cluster.label}</span>
      {qualifier && (
        <span className="shrink-0 text-[10px] text-muted-foreground/60">· {qualifier}</span>
      )}
    </span>
  );
}

function ClusterSelect({
  label,
  value,
  items,
  groups,
  isGrouped,
  stateNameFor,
  disabled,
  onChange,
}: {
  label: string;
  value: ClusterId | null;
  items: ClusterDatum[];
  groups: LegendGroup[];
  isGrouped: boolean;
  stateNameFor: (stateCode: string) => string;
  disabled: boolean;
  onChange: (id: ClusterId) => void;
}) {
  return (
    <div>
      <p className="label-micro">{label}</p>
      <Select {...(value ? { value } : {})} onValueChange={onChange} disabled={disabled}>
        <SelectTrigger className="mt-1.5 h-9 w-full border-panel-border bg-background/40 text-[12px]">
          <SelectValue placeholder="Select a viewpoint" />
        </SelectTrigger>
        <SelectContent>
          {isGrouped
            ? groups.map((group, i) => (
                <SelectGroup key={group.stateCode}>
                  {i > 0 && <SelectSeparator />}
                  <SelectLabel className="px-2 py-1 text-[11px] font-normal text-muted-foreground/70">
                    {stateNameFor(group.stateCode)}
                  </SelectLabel>
                  {group.clusters.map((cluster) => (
                    <SelectItem key={cluster.id} value={cluster.id} className="text-[12px]">
                      <ClusterOptionRow cluster={cluster} qualifier={group.stateCode} />
                    </SelectItem>
                  ))}
                </SelectGroup>
              ))
            : items.map((cluster) => (
                <SelectItem key={cluster.id} value={cluster.id} className="text-[12px]">
                  <ClusterOptionRow cluster={cluster} />
                </SelectItem>
              ))}
        </SelectContent>
      </Select>
    </div>
  );
}
