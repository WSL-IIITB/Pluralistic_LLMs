import { ChevronDown, ChevronUp, Loader2, Square } from "lucide-react";
import { type FormEvent, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
  extrahigh: "Region clustering, most granular",
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
}: QueryBarProps) {
  const [collapsed, setCollapsed] = useState(false);
  const ticker = useWorldviewStore((s) => s.status.ticker);
  const runState = useWorldviewStore((s) => s.runState);
  const isError = runState === "error";
  const activeHint = REASONING_HINTS[reasoningMode];
  const activeProviderOption = LLM_PROVIDER_OPTIONS.find((opt) => opt.value === provider);
  // extrahigh replaces the usual angle-based research with a dedicated,
  // state-targeted research call per Indian state/UT (~32 of them), on top
  // of its existing region-inference + per-region pipeline (~3x "high"'s LLM
  // call volume by itself) -- combined, this realistically runs 25 min to
  // well over an hour end to end, for EVERY provider, not just local ones
  // (no load test exists yet to narrow that range further). Local providers
  // (capped at 2 concurrent requests internally, see LocalOllamaLLMClient)
  // stretch further still. Surface both up front rather than let a run
  // silently take far longer than basic/medium/high ever would.
  const extrahighWarning =
    reasoningMode === "extrahigh"
      ? LOCAL_PROVIDERS.includes(provider)
        ? " · per-state research chain, can take 40-90+ min with local models"
        : " · per-state research chain, can take 25 min-1 hr+"
      : "";

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (value.trim().length > 0) onSubmit(value);
  };

  if (collapsed) {
    return (
      <button
        type="button"
        onClick={() => setCollapsed(false)}
        aria-label="Show query controls"
        title="Show query controls"
        className="panel-surface pointer-events-auto flex items-center gap-2 rounded-full px-4 py-2 text-[11px] font-semibold tracking-wide text-muted-foreground uppercase transition-colors hover:text-foreground"
      >
        <ChevronDown className="size-3.5 shrink-0" />
        <span className="max-w-[50vw] truncate normal-case">{value || "Query"}</span>
      </button>
    );
  }

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
        <button
          type="button"
          onClick={() => setCollapsed(true)}
          aria-label="Hide query controls, show map only"
          title="Hide query controls, show map only"
          className="flex size-8 shrink-0 items-center justify-center rounded-lg text-muted-foreground/60 transition-colors hover:bg-white/5 hover:text-foreground"
        >
          <ChevronUp className="size-4" />
        </button>
      </form>

      <div className="panel-surface mt-2 flex items-center gap-3 rounded-xl px-3 py-2">
        <span className="label-micro shrink-0">Reasoning</span>
        <ToggleGroup
          type="single"
          value={reasoningMode}
          onValueChange={(v) => v && onReasoningModeChange(v as ResearchMode)}
          disabled={isStreaming}
          aria-label="Reasoning mode — always covers every state; controls source volume and, for Extra High, per-region clustering granularity"
          className="shrink-0 justify-start gap-1"
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
        <span className="min-w-0 text-[11px] text-muted-foreground">
          <span className="text-muted-foreground/50">
            {activeHint} · all states
            {extrahighWarning}
          </span>
        </span>
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
        <p className="min-w-0 flex-1 truncate text-[11px] tracking-wide text-muted-foreground">
          {ticker}
        </p>
      </div>
    </div>
  );
}
