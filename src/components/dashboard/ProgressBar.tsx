import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";

const COLLECTION_PROGRESS = 70;

export function ProgressBar() {
  return (
    <section className="panel-surface pointer-events-auto flex w-[560px] max-w-[calc(100vw-3rem)] items-center gap-4 rounded-xl px-4 py-3">
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between">
          <p className="label-micro">Live collection</p>
          <span className="text-[11px] tabular-nums text-muted-foreground">
            {COLLECTION_PROGRESS}%
          </span>
        </div>
        <Progress value={COLLECTION_PROGRESS} className="mt-2 h-1.5 bg-secondary" />
      </div>

      <div className="flex shrink-0 items-center gap-3">
        <Button variant="outline" size="sm" className="h-8 text-[11px]">
          Go deeper
        </Button>
        <p className="w-[110px] text-[10px] leading-tight text-muted-foreground/70">
          sampling bounded — extend for more coverage
        </p>
      </div>
    </section>
  );
}
