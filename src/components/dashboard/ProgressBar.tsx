import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { useWorldviewStore } from "@/lib/worldview";

interface ProgressBarProps {
  onGoDeeper: () => void;
}

export function ProgressBar({ onGoDeeper }: ProgressBarProps) {
  const progress = useWorldviewStore((s) => s.status.progress);
  const runState = useWorldviewStore((s) => s.runState);
  const mode = useWorldviewStore((s) => s.mode);
  const query = useWorldviewStore((s) => s.query);

  const isStreaming = runState === "streaming" || runState === "connecting";
  const pct = Math.round(progress * 100);
  const canGoDeeper = !isStreaming && !!query && (runState === "done" || runState === "empty");

  return (
    <section className="panel-surface pointer-events-auto flex w-[560px] max-w-[calc(100vw-3rem)] items-center gap-4 rounded-xl px-4 py-3">
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between">
          <p className="label-micro">Live collection{mode !== "medium" ? ` · ${mode}` : ""}</p>
          <span className="text-[11px] tabular-nums text-muted-foreground">{pct}%</span>
        </div>
        <Progress value={pct} className="mt-2 h-1.5 bg-secondary" />
      </div>

      <div className="flex shrink-0 items-center gap-3">
        <Button
          variant="outline"
          size="sm"
          className="h-8 text-[11px]"
          onClick={onGoDeeper}
          disabled={!canGoDeeper}
        >
          Go deeper
        </Button>
        <p className="w-[110px] text-[10px] leading-tight text-muted-foreground/70">
          {isStreaming ? "collecting…" : "escalate mode for more sources"}
        </p>
      </div>
    </section>
  );
}
