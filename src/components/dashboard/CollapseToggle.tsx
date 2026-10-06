import { ChevronDown, ChevronUp } from "lucide-react";
import type { ReactNode } from "react";

/**
 * Small icon button shown in an expanded panel's header/row to collapse it
 * down to a pill. Sized to sit next to LegendPanel's existing Minimize2/
 * Maximize2 widen toggle (that button's exact size/hover classes), so the
 * two controls read as one family wherever they appear together. Shared by
 * ProgressBar, ConsolidatedPanel, DeflectionPanel, and LegendPanel.
 */
export function CollapseButton({ onClick, label }: { onClick: () => void; label: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      className="flex size-5 shrink-0 items-center justify-center rounded-md text-muted-foreground/60 transition-colors hover:bg-white/10 hover:text-foreground"
    >
      <ChevronUp className="size-3" />
    </button>
  );
}

/**
 * Replaces a panel's full content once collapsed — mirrors QueryBar.tsx's
 * own (inlined, left as-is) collapsed-state pill markup so every
 * collapsible panel in the dashboard shares one look. Click anywhere to
 * re-expand.
 */
export function CollapsedPill({
  onClick,
  label,
  children,
}: {
  onClick: () => void;
  label: string;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      className="panel-surface pointer-events-auto flex max-w-[50vw] items-center gap-2 rounded-full px-4 py-2 text-[11px] font-semibold tracking-wide text-muted-foreground uppercase transition-colors hover:text-foreground"
    >
      <ChevronDown className="size-3.5 shrink-0" />
      <span className="min-w-0 truncate normal-case">{children}</span>
    </button>
  );
}
