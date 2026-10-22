/** In-depth, media-sourced research for one district — GET /api/karnataka/districts/{id}/research. */

import { useEffect, useState } from "react";

import { assetUrl, dataUrl, STATIC_DATA } from "./api";

export type ReasonCategory =
  | "economic"
  | "migration"
  | "school-infrastructure"
  | "social-norms"
  | "gender"
  | "health"
  | "governance"
  | "other";

export interface ResearchSource {
  id: number;
  url: string;
  title: string;
  outlet: string;
  date: string;
  type: "news" | "government" | "ngo" | "research" | "data";
}

/** One proof item for a dominant factor: "district" proof comes from a page about this district, "general" from research elsewhere. */
export interface FactorWhyProof {
  scope: "district" | "general";
  claim: string;
  quote: string;
  /** ids into DominantFactorWhy.sources (not the district's main sources) */
  sources: number[];
}

export interface FactorWhyEntry {
  factor: string;
  method: "state" | "district";
  area: string;
  verdict: "supported" | "partly" | "not-supported" | "no-evidence";
  why: string;
  /** Causal route in general terms — not local evidence. */
  mechanism: string;
  proof: FactorWhyProof[];
}

/** Deep-research answer to "why is this factor dominant here?", verified against the cited pages. */
export interface DominantFactorWhy {
  researchedOn: string;
  entries: FactorWhyEntry[];
  sources: ResearchSource[];
  gaps: string;
  /** What was dropped or downgraded during verification. */
  notes: string[];
}

export interface DistrictResearch {
  districtId: string;
  name: string;
  regionId: string;
  researchedOn: string;
  headline: string;
  summary: string;
  reasons: {
    factor: string;
    category: ReasonCategory;
    detail: string;
    sources: number[];
    evidence: "strong" | "moderate" | "thin";
  }[];
  keyFacts: { label: string; value: string; sources: number[] }[];
  headlines: { title: string; outlet: string; date: string; url: string; takeaway: string }[];
  responses: { text: string; sources: number[] }[];
  sources: ResearchSource[];
  /** The deep-research verdict on each UIDAI/NITI factor row: does local evidence bear it out? */
  officialFactorCheck?: {
    factor: string;
    method: "state" | "district";
    verdict: "supports" | "contradicts" | "unclear" | "no-evidence";
    note: string;
    sources: number[];
  }[];
  /** Why each UIDAI/NITI dominant factor would drive dropout here, with verified proof (absent until researched). */
  dominantFactorWhy?: DominantFactorWhy;
  coverage: "rich" | "moderate" | "thin";
  gaps: string;
  /** What was dropped or corrected when the report was checked against its cited pages. */
  verificationNotes?: string;
}

type Entry =
  { status: "loading" } | { status: "none" } | { status: "ready"; data: DistrictResearch };

const cache = new Map<string, Entry>();
const listeners = new Set<() => void>();

/** When a saved run is open, the research it was saved with replaces the live files. */
let snapshot: Record<string, DistrictResearch> | null = null;

export function setResearchSnapshot(next: Record<string, DistrictResearch> | null): void {
  snapshot = next;
  listeners.forEach((notify) => notify());
}

/** True while the research on screen is a saved run's snapshot rather than the live files. */
export function researchSnapshotActive(): boolean {
  return snapshot !== null;
}

let allInflight: Promise<Record<string, DistrictResearch> | null> | null = null;

type ResearchMap = Record<string, DistrictResearch>;

const readJson = <T>(url: string): Promise<T | null> =>
  fetch(url)
    .then((r) => (r.ok ? (r.json() as Promise<T>) : null))
    .catch(() => null);

/**
 * Every district's research as it stands now (for embedding into a saved run). If the backend is
 * unreachable, the bundled snapshot in /data stands in, so the dashboard is never left empty.
 */
export function fetchAllDistrictResearch(): Promise<ResearchMap | null> {
  allInflight ??= readJson<ResearchMap>(dataUrl("/api/karnataka/districts-research"))
    .then(
      (live) =>
        live ??
        (STATIC_DATA ? null : readJson<ResearchMap>(assetUrl("data/districts-research.json"))),
    )
    .finally(() => {
      allInflight = null; // always re-read: the files can change between runs
    });
  return allInflight;
}

function load(districtId: string): void {
  if (cache.has(districtId)) return;
  cache.set(districtId, { status: "loading" });
  if (STATIC_DATA) {
    // No per-district endpoint in a static build: read it out of the bulk snapshot.
    void fetchAllDistrictResearch().then((all) => {
      cache.set(
        districtId,
        all?.[districtId] ? { status: "ready", data: all[districtId] } : { status: "none" },
      );
      listeners.forEach((notify) => notify());
    });
    return;
  }
  readJson<DistrictResearch>(dataUrl(`/api/karnataka/districts/${districtId}/research`))
    .then((live) => live ?? fetchAllDistrictResearch().then((all) => all?.[districtId] ?? null))
    .then((data) => {
      cache.set(districtId, data ? { status: "ready", data } : { status: "none" });
      listeners.forEach((notify) => notify());
    });
}

/** Research for one district; `none` when there is no file for it (or the backend is unreachable). */
export function useDistrictResearch(districtId: string | null): Entry {
  const [, bump] = useState(0);

  // Subscribe to the module-level state so a fetch that finishes while this
  // component is remounting (React strict mode), or a saved run being opened,
  // still re-renders it.
  useEffect(() => {
    const notify = () => bump((n) => n + 1);
    listeners.add(notify);
    return () => {
      listeners.delete(notify);
    };
  }, []);

  useEffect(() => {
    if (districtId && !snapshot) load(districtId);
  }, [districtId]);

  if (!districtId) return { status: "none" };
  if (snapshot) {
    const data = snapshot[districtId];
    return data ? { status: "ready", data } : { status: "none" };
  }
  return cache.get(districtId) ?? { status: "loading" };
}
