/**
 * Media and official-source research on under-5 stunting, one file per district (GET /api/stunting/research, or
 * public/data/stunting-research.json on the static site). Collected by web search, compiled by Claude and verified
 * against every cited page by scripts/research_stunting_districts.py -- the stunting counterpart of the dropout
 * district research.
 */

import { useEffect, useState } from "react";

import { cachedJson } from "./api";
import type { ResearchSource } from "./districtResearch";

export type StuntingCategory =
  | "nutrition-diet"
  | "maternal-health"
  | "health-services"
  | "water-sanitation"
  | "economic"
  | "social-norms"
  | "governance"
  | "other";

export const STUNTING_CATEGORY_LABEL: Record<StuntingCategory, string> = {
  "nutrition-diet": "Diet & food security",
  "maternal-health": "Mothers' health & anaemia",
  "health-services": "Health services & anganwadis",
  "water-sanitation": "Water & sanitation",
  economic: "Poverty & livelihoods",
  "social-norms": "Child marriage & social norms",
  governance: "Schemes & governance",
  other: "Other",
};

export const STUNTING_CATEGORY_EMOJI: Record<StuntingCategory, string> = {
  "nutrition-diet": "🍚",
  "maternal-health": "🤰",
  "health-services": "🏥",
  "water-sanitation": "🚰",
  economic: "💰",
  "social-norms": "👧",
  governance: "🏛️",
  other: "📌",
};

export interface ModelFactorWhy {
  factor: string;
  verdict: "supported" | "partly" | "no-evidence";
  why: string;
  mechanism: string;
  proof: { claim: string; sources: number[] }[];
}

export interface StuntingResearch {
  districtId: string;
  name: string;
  regionId: string;
  topic: "stunting";
  researchedOn: string;
  method: string;
  headline: string;
  summary: string;
  reasons: {
    factor: string;
    category: StuntingCategory;
    detail: string;
    sources: number[];
    evidence: "strong" | "moderate" | "thin";
  }[];
  keyFacts: { label: string; value: string; sources: number[] }[];
  headlines: { title: string; outlet: string; date: string; url: string; takeaway: string }[];
  responses: { text: string; sources: number[] }[];
  sources: ResearchSource[];
  /** For each factor the NITI stunting model prescribes most change for: local evidence for why it matters here. */
  modelFactorWhy: ModelFactorWhy[];
  coverage: "rich" | "moderate" | "thin";
  gaps: string;
  /** What verification dropped (claims whose numbers were not on the cited page, etc.). */
  verificationNotes: string[];
  searched?: number;
  candidatePages?: number;
}

const load = cachedJson<Record<string, StuntingResearch>>("/api/stunting/research");

/** Every district's stunting research; undefined while loading, null if unavailable. */
export function useAllStuntingResearch(): Record<string, StuntingResearch> | null | undefined {
  const [data, setData] = useState<Record<string, StuntingResearch> | null | undefined>(undefined);
  useEffect(() => {
    let alive = true;
    void load().then((d) => alive && setData(d));
    return () => {
      alive = false;
    };
  }, []);
  return data;
}
