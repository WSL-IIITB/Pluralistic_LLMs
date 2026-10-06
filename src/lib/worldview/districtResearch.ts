/** In-depth, media-sourced research for one district — GET /api/karnataka/districts/{id}/research. */

import { useEffect, useState } from "react";

import { dataUrl, STATIC_DATA } from "./api";

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

/** Every district's research as it stands now (for embedding into a saved run). */
export function fetchAllDistrictResearch(): Promise<Record<string, DistrictResearch> | null> {
  allInflight ??= fetch(dataUrl("/api/karnataka/districts-research"))
    .then((r) => (r.ok ? (r.json() as Promise<Record<string, DistrictResearch>>) : null))
    .catch(() => null)
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
      cache.set(districtId, all?.[districtId] ? { status: "ready", data: all[districtId] } : { status: "none" });
      listeners.forEach((notify) => notify());
    });
    return;
  }
  fetch(dataUrl(`/api/karnataka/districts/${districtId}/research`))
    .then((r) => (r.ok ? (r.json() as Promise<DistrictResearch>) : null))
    .catch(() => null)
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
