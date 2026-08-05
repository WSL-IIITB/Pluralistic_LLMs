import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { regionOptions } from "./mock-data";

export function DeflectionPanel() {
  return (
    <section className="panel-surface pointer-events-auto w-[720px] max-w-[calc(100vw-3rem)] rounded-xl p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xs font-medium tracking-wide text-foreground">Deflection Analysis</h2>
        <span className="rounded-full border border-panel-border px-2 py-0.5 text-[10px] text-muted-foreground">
          level: inter-region
        </span>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-3">
        <RegionSelect label="Region A" defaultValue="North" />
        <RegionSelect label="Region B" defaultValue="South" />
      </div>

      <div className="mt-3 rounded-lg border border-panel-border bg-background/40 p-3">
        <div className="flex items-center gap-3 text-[13px]">
          <span className="flex items-center gap-2">
            <span className="size-2 rounded-full bg-cluster-1" aria-hidden />
            <span className="text-foreground">Rama / Ayodhya</span>
          </span>
          <span className="text-muted-foreground/50">↔</span>
          <span className="flex items-center gap-2">
            <span className="size-2 rounded-full bg-cluster-2" aria-hidden />
            <span className="text-foreground">Krishna / Narakasura</span>
          </span>
        </div>
        <p className="mt-2 text-[12px] leading-relaxed text-muted-foreground">
          <span className="label-micro mr-1">Point of deflection</span>
          which divine figure and which liberation event is being commemorated.
        </p>
      </div>
    </section>
  );
}

function RegionSelect({ label, defaultValue }: { label: string; defaultValue: string }) {
  return (
    <div>
      <p className="label-micro">{label}</p>
      <Select defaultValue={defaultValue}>
        <SelectTrigger className="mt-1.5 h-9 w-full border-panel-border bg-background/40 text-[12px]">
          <SelectValue placeholder={label} />
        </SelectTrigger>
        <SelectContent>
          {regionOptions.map((region) => (
            <SelectItem key={region} value={region} className="text-[12px]">
              {region}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
