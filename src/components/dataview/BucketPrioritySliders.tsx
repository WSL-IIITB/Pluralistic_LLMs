/**
 * BucketPrioritySliders — shared control for setting a Nil/Low/Medium/High/
 * Critical priority per factor bucket (Infrastructure / Digital and ICT /
 * Teacher Profile / Socio-Economic).
 *
 * Reused by both the District Prescription panel and the Budget Allocation
 * panel (Phase 4/5 — built by other agents), so this stays presentational and
 * fully controlled: it owns no state of its own, just `priorities` in,
 * `onChange` out. Built from this codebase's existing Toggle Group primitive
 * (see QueryBar.tsx's reasoning-mode picker for the pattern this mirrors),
 * not a new control.
 */

import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import type { BucketId, PriorityLevel } from "@/lib/dataview/types";

const BUCKET_ORDER: readonly BucketId[] = [
  "infrastructure",
  "digital_ict",
  "teacher_profile",
  "socio_economic",
];

const BUCKET_LABELS: Record<BucketId, string> = {
  infrastructure: "Infrastructure",
  digital_ict: "Digital and ICT",
  teacher_profile: "Teacher Profile",
  socio_economic: "Socio-Economic",
};

const PRIORITY_OPTIONS: readonly { value: PriorityLevel; label: string }[] = [
  { value: "nil", label: "Nil" },
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
  { value: "critical", label: "Critical" },
];

export interface BucketPrioritySlidersProps {
  priorities: Record<BucketId, PriorityLevel>;
  onChange: (bucket: BucketId, level: PriorityLevel) => void;
}

export function BucketPrioritySliders({ priorities, onChange }: BucketPrioritySlidersProps) {
  return (
    <div className="flex flex-col gap-3">
      {BUCKET_ORDER.map((bucket) => (
        // Label sits on its own line above its button row (rather than
        // label-left/buttons-right on one line) so the 5-option row gets the
        // panel's full inner width to work with — at 340px (the narrowest
        // panel that reuses this control, BudgetAllocationPanel) a
        // label-left layout leaves too little room and clips the
        // right-most "Critical" button. `flex-wrap` is a safety net on top
        // of that so the row degrades to two lines instead of clipping or
        // silently overflowing even if a future panel is narrower still.
        <div key={bucket} className="flex flex-col gap-1.5">
          <span className="label-micro">{BUCKET_LABELS[bucket]}</span>
          <ToggleGroup
            type="single"
            value={priorities[bucket]}
            onValueChange={(v) => {
              if (v) onChange(bucket, v as PriorityLevel);
            }}
            aria-label={`${BUCKET_LABELS[bucket]} priority`}
            className="flex-wrap justify-start gap-1"
          >
            {PRIORITY_OPTIONS.map((opt) => (
              <ToggleGroupItem
                key={opt.value}
                value={opt.value}
                className="h-7 px-2 text-[11px] font-semibold tracking-wide uppercase"
              >
                {opt.label}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        </div>
      ))}
    </div>
  );
}
