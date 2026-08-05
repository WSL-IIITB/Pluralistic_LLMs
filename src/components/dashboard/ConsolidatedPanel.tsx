import { ScrollArea } from "@/components/ui/scroll-area";
import { consolidatedParagraphs, regionalViewpoints } from "./mock-data";

export function ConsolidatedPanel() {
  return (
    <section className="panel-surface pointer-events-auto flex max-h-[calc(100vh-13rem)] w-[380px] flex-col rounded-xl">
      <header className="flex items-center justify-between border-b border-panel-border px-4 py-3">
        <h2 className="text-xs font-medium tracking-wide text-foreground">Consolidated View</h2>
        <div className="flex items-center gap-1 rounded-full border border-panel-border p-0.5">
          <span className="rounded-full bg-secondary px-2 py-0.5 text-[10px] text-foreground">
            descriptive
          </span>
          <span className="px-2 py-0.5 text-[10px] text-muted-foreground">policy</span>
        </div>
      </header>

      <ScrollArea className="min-h-0 flex-1">
        <div className="space-y-3 px-4 py-4">
          {consolidatedParagraphs.map((paragraph) => (
            <p key={paragraph.slice(0, 24)} className="text-[13px] leading-relaxed text-muted-foreground">
              {paragraph}
            </p>
          ))}

          <div className="pt-2">
            <p className="label-micro">Regional viewpoints</p>
            <ul className="mt-3 space-y-2.5">
              {regionalViewpoints.map((viewpoint) => (
                <li key={viewpoint.region} className="flex gap-2.5">
                  <span
                    className={`mt-1.5 size-2 shrink-0 rounded-full ${viewpoint.swatchClass}`}
                    aria-hidden
                  />
                  <p className="text-[13px] leading-snug text-muted-foreground">
                    <span className="font-medium text-foreground">{viewpoint.region}:</span>{" "}
                    {viewpoint.detail}
                  </p>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </ScrollArea>
    </section>
  );
}
