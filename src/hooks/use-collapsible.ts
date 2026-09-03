import { useState } from "react";

/**
 * Local, independent expand/collapse state for a floating dashboard panel
 * that can shrink down to a small pill — shared by ProgressBar,
 * ConsolidatedPanel, DeflectionPanel, and LegendPanel so each gets the same
 * affordance QueryBar already had (see QueryBar.tsx's own inlined
 * `useState(false)` collapse toggle, left as-is since it's the reference
 * pattern this hook generalizes). Each caller holds its own state —
 * collapsing one panel never affects another.
 *
 * Defaults to expanded: this is a "get it out of my way" affordance for
 * when the map needs more room, not a default-hidden panel.
 */
export function useCollapsible(defaultCollapsed = false) {
  const [collapsed, setCollapsed] = useState(defaultCollapsed);
  return {
    collapsed,
    expand: () => setCollapsed(false),
    collapse: () => setCollapsed(true),
  };
}
