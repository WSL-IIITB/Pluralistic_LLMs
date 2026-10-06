/**
 * Data View REST wrappers — the interactive-recompute half of the hybrid API
 * (see the plan's "Architecture decisions": SSE for the one-time bootstrap
 * load, plain synchronous REST for every slider/select tick).
 *
 * Base URL is derived from `DATAVIEW_API_URL` by stripping the trailing
 * `/stream`, so REST calls share the same host/port as the SSE bootstrap
 * without a second env var (mirrors `worldview/runHistory.ts`'s
 * `RUNS_URL = WORLDVIEW_API_URL.replace(/\/stream$/, "/runs")` trick).
 *
 * Error convention: unlike `worldview/runHistory.ts` (fail-soft — logs and
 * returns a safe empty value, since a saved-run fetch failing shouldn't break
 * the live dashboard), every function here THROWS on a non-2xx response, with
 * a message including the status and response body text. These calls back
 * interactive sliders that need to surface a failed recompute to the user,
 * not silently no-op it.
 */

import { DATAVIEW_API_URL } from "./stream/config";
import type {
  BucketId,
  BudgetAllocationResult,
  DistrictId,
  DistrictProfile,
  PrescriptionResult,
  PriorityLevel,
  StateCode,
  VerdictAreaKind,
  VerdictResult,
} from "./types";

/** A real gemma_remote (or other provider) call for the verdict narrative
 * can legitimately take 15-40+ real seconds (see backend router.py's own
 * header comment) — this is a generous ceiling against a genuine indefinite
 * hang, NOT a tight fast-fail budget. Mirrors the backend's own
 * `generate_verdict` timeout (150s) rather than picking an unrelated,
 * shorter number. */
const VERDICT_TIMEOUT_MS = 150_000;

/** Same origin as the SSE stream endpoint, swapping off the path's tail. */
const BASE_URL = DATAVIEW_API_URL.replace(/\/stream$/, "");

async function parseOrThrow<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`Data View API request failed (${res.status}): ${body}`);
  }
  return (await res.json()) as T;
}

/** `bucket_priority_*` query params, one per bucket, matching the backend's flat param names. */
function bucketPriorityParams(
  bucketPriorities: Record<BucketId, PriorityLevel>,
): Record<string, string> {
  return {
    bucket_priority_infrastructure: bucketPriorities.infrastructure,
    bucket_priority_digital_ict: bucketPriorities.digital_ict,
    bucket_priority_teacher_profile: bucketPriorities.teacher_profile,
    bucket_priority_socio_economic: bucketPriorities.socio_economic,
  };
}

export async function getDistrictProfile(districtId: DistrictId): Promise<DistrictProfile> {
  const res = await fetch(`${BASE_URL}/district/${encodeURIComponent(districtId)}/profile`);
  return parseOrThrow<DistrictProfile>(res);
}

export async function getDistrictPrescription(
  districtId: DistrictId,
  targetReduction: number,
  bucketPriorities: Record<BucketId, PriorityLevel>,
): Promise<PrescriptionResult> {
  const params = new URLSearchParams({
    target_reduction: String(targetReduction),
    ...bucketPriorityParams(bucketPriorities),
  });
  const res = await fetch(
    `${BASE_URL}/district/${encodeURIComponent(districtId)}/prescription?${params.toString()}`,
  );
  return parseOrThrow<PrescriptionResult>(res);
}

export async function postBudgetAllocation(
  stateCode: StateCode,
  totalBudget: number,
  bucketPriorities?: Record<BucketId, PriorityLevel>,
): Promise<BudgetAllocationResult> {
  const res = await fetch(`${BASE_URL}/state/${encodeURIComponent(stateCode)}/budget`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      totalBudget,
      ...(bucketPriorities ? { bucketPriorities } : {}),
    }),
  });
  return parseOrThrow<BudgetAllocationResult>(res);
}

/**
 * The real LLM-backed verdict narrative for one district or state. Unlike
 * every other call in this file (typically well under a second — pure
 * numeric recompute on an already-fitted model), this one goes through the
 * backend's `generate_verdict` LLM call and can genuinely take 15-40+
 * seconds — callers MUST show a visible loading state while this is in
 * flight (see `DataViewVerdict.tsx`), not just leave the UI looking stuck.
 * `AbortSignal.timeout` here is a generous ceiling against a genuine
 * indefinite hang, not a fast-fail budget — see `VERDICT_TIMEOUT_MS` above.
 */
export async function getVerdict(
  areaKind: VerdictAreaKind,
  id: DistrictId | StateCode,
): Promise<VerdictResult> {
  const path =
    areaKind === "district"
      ? `/district/${encodeURIComponent(id)}/verdict`
      : `/state/${encodeURIComponent(id)}/verdict`;
  const res = await fetch(`${BASE_URL}${path}`, {
    signal: AbortSignal.timeout(VERDICT_TIMEOUT_MS),
  });
  return parseOrThrow<VerdictResult>(res);
}
