import type { FactorWhyEntry } from "@/lib/worldview";

/** Pill label + colours for the "why is this factor dominant here?" verdicts. */
export const WHY_STYLE: Record<FactorWhyEntry["verdict"], { label: string; className: string }> = {
  supported: {
    label: "Supported locally",
    className: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
  },
  partly: {
    label: "Partly supported",
    className: "bg-amber-500/15 text-amber-800 dark:text-amber-300",
  },
  "not-supported": {
    label: "Not supported",
    className: "bg-red-500/15 text-red-700 dark:text-red-300",
  },
  "no-evidence": { label: "No evidence found", className: "bg-secondary text-muted-foreground" },
};
