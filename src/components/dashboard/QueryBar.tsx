import { Loader2, Square } from "lucide-react";
import { type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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
}

/**
 * Every mode always surveys the full set of Indian states/regions — see
 * backend/app/reasoning_modes.py. These labels describe how much SOURCE
 * VOLUME and research effort each mode spends, not geographic coverage --
 * except "extrahigh", which is qualitatively different: it clusters each
 * state's posts independently instead of pooling them into one global pass,
 * so it also changes HOW granular the resulting viewpoints are, not just how
 * many sources feed them. Only reachable by picking it here directly -- "Go
 * deeper" is deliberately capped at "high" (see types.ts's escalateMode).
 */
const REASONING_MODES: { value: ResearchMode; label: string }[] = [
  { value: "basic", label: "Basic" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
  { value: "extrahigh", label: "Extra High" },
];

const REASONING_HINTS: Record<ResearchMode, string> = {
  basic: "Fewer sources, fast",
  medium: "Balanced",
  high: "Most sources, slower",
  extrahigh: "Per-state clustering, most granular",
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
    label: "Gemma",
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
}: QueryBarProps) {
  const ticker = useWorldviewStore((s) => s.status.ticker);
  const runState = useWorldviewStore((s) => s.runState);
  const isError = runState === "error";
  const activeHint = REASONING_HINTS[reasoningMode];
  const activeProviderHint = LLM_PROVIDER_OPTIONS.find((opt) => opt.value === provider)?.hint;
  // extrahigh's per-state pipeline runs ~3x the LLM call volume of "high";
  // against a local provider (capped at 2 concurrent requests internally,
  // see LocalOllamaLLMClient) that can stretch to 15-20 minutes -- surface
  // that up front rather than let a run silently take far longer than
  // basic/medium/high ever would.
  const extrahighLocalWarning =
    reasoningMode === "extrahigh" && LOCAL_PROVIDERS.includes(provider)
      ? " · can take 15-20 min with local models"
      : "";

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (value.trim().length > 0) onSubmit(value);
  };

  return (
    <div className="pointer-events-auto w-[min(720px,calc(100vw-3rem))]">
      <form
        onSubmit={handleSubmit}
        className="panel-surface flex items-center gap-2 rounded-xl p-2"
      >
        <Input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Enter a topic — e.g. Diwali, or 'high-school dropouts: where should government intervene?'"
          className="h-10 border-0 bg-transparent text-sm shadow-none focus-visible:ring-0"
          aria-label="Topic to explore"
        />
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

      <div className="panel-surface mt-2 flex items-center gap-3 rounded-xl px-3 py-2">
        <span className="label-micro shrink-0">Reasoning</span>
        <ToggleGroup
          type="single"
          value={reasoningMode}
          onValueChange={(v) => v && onReasoningModeChange(v as ResearchMode)}
          disabled={isStreaming}
          aria-label="Reasoning mode — always covers every state; controls source volume and, for Extra High, per-state clustering granularity"
          className="justify-start gap-1"
        >
          {REASONING_MODES.map((m) => (
            <ToggleGroupItem
              key={m.value}
              value={m.value}
              className="h-7 px-3 text-[11px] font-semibold tracking-wide uppercase"
            >
              {m.label}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
        <span className="shrink-0 text-[11px] text-muted-foreground">
          <span className="text-muted-foreground/50">
            {activeHint} · all states
            {extrahighLocalWarning}
          </span>
        </span>
      </div>

      <div className="panel-surface mt-2 flex items-center gap-3 rounded-xl px-3 py-2">
        <span className="label-micro shrink-0">Model</span>
        <Select
          value={provider}
          onValueChange={(v) => onProviderChange(v as LlmProvider)}
          disabled={isStreaming}
        >
          <SelectTrigger
            className="h-7 w-auto gap-1.5 border-0 bg-transparent px-2 text-[11px] font-semibold tracking-wide uppercase shadow-none focus:ring-0"
            aria-label="LLM provider"
          >
            <SelectValue />
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
        {activeProviderHint && (
          <span className="shrink-0 text-[11px] text-muted-foreground">
            <span className="text-muted-foreground/50">{activeProviderHint}</span>
          </span>
        )}
      </div>

      <div className="mt-2 flex items-center gap-2 px-2">
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
        <p className="truncate text-[11px] tracking-wide text-muted-foreground">{ticker}</p>
      </div>
    </div>
  );
}
