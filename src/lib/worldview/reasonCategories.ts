/** Display names and icons for the reason categories used in the district research files. */

import type { ReasonCategory } from "./districtResearch";

export const CATEGORY_LABEL: Record<ReasonCategory, string> = {
  economic: "Poverty & child labour",
  migration: "Migration",
  "school-infrastructure": "School infrastructure & staffing",
  "social-norms": "Social norms & customs",
  gender: "Child marriage & girls' exits",
  health: "Health",
  governance: "Governance, tracking & exams",
  other: "Other",
};

export const CATEGORY_EMOJI: Record<string, string> = {
  economic: "💰",
  migration: "🧳",
  "school-infrastructure": "🏫",
  "social-norms": "🏘️",
  gender: "👧",
  health: "🩺",
  governance: "🏛️",
  other: "📌",
};
