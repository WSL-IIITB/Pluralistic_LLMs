import type { DistrictResearch, FactorWhyEntry } from "@/lib/worldview";

/** Pill colours for how well each researched reason is evidenced. */
export const EVIDENCE_STYLE: Record<DistrictResearch["reasons"][number]["evidence"], string> = {
  strong: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
  moderate: "bg-amber-500/15 text-amber-800 dark:text-amber-300",
  thin: "bg-secondary text-muted-foreground",
};

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

/** Pill label + colours for the earlier check of each factor row against local evidence (officialFactorCheck). */
export const CHECK_STYLE: Record<
  NonNullable<DistrictResearch["officialFactorCheck"]>[number]["verdict"],
  { label: string; className: string }
> = {
  supports: {
    label: "Local evidence supports",
    className: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
  },
  contradicts: {
    label: "Local evidence contradicts",
    className: "bg-red-500/15 text-red-700 dark:text-red-300",
  },
  unclear: { label: "Unclear", className: "bg-amber-500/15 text-amber-800 dark:text-amber-300" },
  "no-evidence": {
    label: "No local evidence found",
    className: "bg-secondary text-muted-foreground",
  },
};
