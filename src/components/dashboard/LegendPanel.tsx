import { Checkbox } from "@/components/ui/checkbox";
import { layerToggles, viewpointClusters } from "./mock-data";

export function LegendPanel() {
  return (
    <aside className="panel-surface pointer-events-auto w-[260px] rounded-xl">
      <div className="border-b border-panel-border px-4 py-3">
        <p className="label-micro">Viewpoint Clusters</p>
        <ul className="mt-3 space-y-2">
          {viewpointClusters.map((cluster) => (
            <li key={cluster.id} className="flex items-center gap-2.5">
              <span className={`size-2.5 rounded-[3px] ${cluster.swatchClass}`} aria-hidden />
              <span className="text-[12px] text-muted-foreground">{cluster.label}</span>
            </li>
          ))}
        </ul>
      </div>

      <div className="border-b border-panel-border px-4 py-3">
        <p className="label-micro">Data Confidence</p>
        <ul className="mt-3 space-y-2">
          <li className="flex items-center gap-2.5">
            <span className="size-2.5 rounded-[3px] bg-cluster-2" aria-hidden />
            <span className="text-[12px] text-muted-foreground">High</span>
          </li>
          <li className="flex items-center gap-2.5">
            <span className="size-2.5 rounded-[3px] bg-cluster-2/30" aria-hidden />
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
          {layerToggles.map((layer) => (
            <li key={layer.id} className="flex items-center gap-2.5">
              <Checkbox id={`layer-${layer.id}`} defaultChecked className="size-3.5" />
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
