import { Loader2, Lock, Square } from "lucide-react";
import type { FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Select, SelectContent, SelectItem, SelectTrigger } from "@/components/ui/select";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useWorldviewStore } from "@/lib/worldview";
import type { LlmProvider, ResearchMode } from "@/lib/worldview/types";

interface QueryBarProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (value: string) => void;
  onStop: () => void;
  isStreaming: boolean;
  reasoningMode: ResearchMode;
  onReasoningModeChange: (mode: ResearchMode) => void;
  provider: LlmProvider;
  onProviderChange: (provider: LlmProvider) => void;
  /** Show the topic but disable editing — the study is built around one fixed question. */
  locked?: boolean;
  /** Re-run the current query one reasoning mode higher. */
  onGoDeeper: () => void;
}

/**
 * Every mode covers all six Karnataka persona regions (see
 * backend/app/reasoning_modes.py); mode scales how many targeted searches run
 * per region and how many posts each keeps.
 */
const REASONING_MODES: { value: ResearchMode; label: string }[] = [
  { value: "basic", label: "Basic" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
  { value: "extrahigh", label: "Extra High" },
];

const REASONING_HINTS: Record<ResearchMode, string> = {
  basic: "1 search per region, fast",
  medium: "2 searches per region",
  high: "3 searches per region, slower",
  extrahigh: "4 searches per region, most sources",
};

const LOCAL_PROVIDERS: readonly LlmProvider[] = ["gemma_local", "mistral_local"];

/**
 * Accent-colour dots stand in for real provider logos for now (see
 * QueryBar.tsx history — logos were attempted but descoped to avoid shipping
 * unlicensed brand marks; swap in `src/assets/logos/*.svg` here if real
 * assets land later). Colours echo brand identity loosely: Anthropic
 * terracotta, OpenAI teal, Gemma's Google blue, Mistral's orange.
 */
const LLM_PROVIDER_OPTIONS: {
  value: LlmProvider;
  label: string;
  hint: string;
  dotClassName: string;
  disabled?: boolean;
}[] = [
  {
    value: "gemma_remote",
    label: "Gemma",
    hint: "Self-hosted · free",
    dotClassName: "bg-[#4285f4]",
  },
  {
    value: "azure_anthropic",
    label: "Claude",
    hint: "Hosted · Anthropic",
    dotClassName: "bg-[#da7756]",
  },
  {
    value: "openai",
    label: "OpenAI",
    hint: "Out of credits",
    dotClassName: "bg-[#10a37f]",
    disabled: true,
  },
  {
    value: "gemma_local",
    label: "Gemma (local)",
    hint: "Local · free · Ollama",
    dotClassName: "bg-[#4285f4]",
  },
  {
    value: "mistral_local",
    label: "Mistral",
    hint: "Local · free · Ollama",
    dotClassName: "bg-[#fa500f]",
  },
];

export function QueryBar({
  value,
  onChange,
  onSubmit,
  onStop,
  isStreaming,
  reasoningMode,
  onReasoningModeChange,
  provider,
  onProviderChange,
  onGoDeeper,
  locked = false,
}: QueryBarProps) {
  const ticker = useWorldviewStore((s) => s.status.ticker);
  const progress = useWorldviewStore((s) => s.status.progress);
  const runState = useWorldviewStore((s) => s.runState);
  const storedQuery = useWorldviewStore((s) => s.query);
  const isError = runState === "error";
  const pct = Math.round(progress * 100);
  const canGoDeeper =
    !isStreaming && !!storedQuery && (runState === "done" || runState === "empty");
  const activeHint = REASONING_HINTS[reasoningMode];
  const activeProviderOption = LLM_PROVIDER_OPTIONS.find((opt) => opt.value === provider);
  const localWarning =
    LOCAL_PROVIDERS.includes(provider) &&
    (reasoningMode === "high" || reasoningMode === "extrahigh")
      ? " · slow with local models"
      : "";

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (value.trim().length > 0) onSubmit(value);
  };

  return (
    <section className="panel-surface pointer-events-auto w-full shrink-0 rounded-xl">
      {/* Row 1 — the question */}
      <form onSubmit={handleSubmit} className="flex items-center gap-2 p-2.5">
        <div className="relative min-w-0 flex-1">
          <Input
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder="Enter a topic"
            aria-label={locked ? "Topic (fixed for this study)" : "Topic to explore"}
            title={locked ? "The topic is fixed for this study" : undefined}
            className="h-10 w-full border-0 bg-transparent px-2 pr-8 text-[14px] shadow-none focus-visible:ring-0 disabled:cursor-not-allowed disabled:opacity-100 disabled:text-foreground/80"
            disabled={isStreaming || locked}
          />
          {locked && (
            <Lock
              className="pointer-events-none absolute top-1/2 right-2 size-3.5 -translate-y-1/2 text-muted-foreground/60"
              aria-hidden
            />
          )}
        </div>
        <Select
          value={provider}
          onValueChange={(v) => onProviderChange(v as LlmProvider)}
          disabled={isStreaming}
        >
          <SelectTrigger
            className="h-8 w-8 shrink-0 justify-center gap-0 border-0 bg-transparent p-0 shadow-none focus:ring-0 [&>svg]:ml-0 [&>svg]:size-3 [&>svg]:opacity-50"
            aria-label={`LLM provider: ${activeProviderOption?.label ?? provider}`}
            title={
              activeProviderOption
                ? `Model: ${activeProviderOption.label} — ${activeProviderOption.hint}`
                : "Model"
            }
          >
            <span
              className={`size-2.5 shrink-0 rounded-full ${activeProviderOption?.dotClassName ?? "bg-muted-foreground"}`}
              aria-hidden
            />
          </SelectTrigger>
          <SelectContent>
            {LLM_PROVIDER_OPTIONS.map((opt) => (
              <SelectItem key={opt.value} value={opt.value} disabled={opt.disabled ?? false}>
                <span className="flex items-center gap-2">
                  <span className={`size-2 shrink-0 rounded-full ${opt.dotClassName}`} />
                  {opt.label}
                </span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {isStreaming ? (
          <Button
            type="button"
            onClick={onStop}
            variant="secondary"
            className="h-10 shrink-0 gap-1.5 px-4 text-xs font-semibold tracking-wide uppercase"
          >
            <Square className="size-3.5 fill-current" />
            Stop
          </Button>
        ) : (
          <Button
            type="submit"
            className="h-10 shrink-0 px-5 text-xs font-semibold tracking-wide uppercase"
          >
            Explore
          </Button>
        )}
      </form>

      {/* Row 2 — how deep to go */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-panel-border px-3.5 py-2">
        <span className="label-micro shrink-0">Reasoning</span>
        <ToggleGroup
          type="single"
          value={reasoningMode}
          onValueChange={(v) => v && onReasoningModeChange(v as ResearchMode)}
          disabled={isStreaming}
          aria-label="Reasoning mode — always covers all six Karnataka regions; controls how many sources are gathered per region"
          className="shrink-0 justify-start gap-1"
        >
          {REASONING_MODES.map((m) => (
            <ToggleGroupItem
              key={m.value}
              value={m.value}
              className="h-7 px-2.5 text-[11px] font-semibold tracking-wide uppercase"
            >
              {m.label}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
        <span className="min-w-0 truncate text-[11px] text-muted-foreground/70">
          {activeHint}
          {localWarning}
        </span>
      </div>

      {/* Row 3 — live status */}
      <div className="border-t border-panel-border px-3.5 py-2.5">
        <div className="flex items-center gap-2">
          <span className="relative flex size-1.5 shrink-0">
            {isStreaming && (
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-primary opacity-70" />
            )}
            <span
              className={
                "relative inline-flex size-1.5 rounded-full " +
                (isError ? "bg-destructive" : isStreaming ? "bg-primary" : "bg-muted-foreground/50")
              }
            />
          </span>
          {isStreaming && (
            <Loader2 className="size-3 shrink-0 animate-spin text-muted-foreground/70" />
          )}
          <p className="min-w-0 flex-1 truncate text-[11px] text-muted-foreground">{ticker}</p>
          <span className="shrink-0 text-[11px] tabular-nums text-muted-foreground">{pct}%</span>
          <Button
            variant="ghost"
            size="sm"
            className="h-6 shrink-0 px-2 text-[11px]"
            onClick={onGoDeeper}
            disabled={!canGoDeeper}
            title="Re-run this query one reasoning mode higher for more sources"
          >
            Go deeper
          </Button>
        </div>
        <Progress value={pct} className="mt-2 h-1 bg-secondary" />
      </div>
    </section>
  );
}
