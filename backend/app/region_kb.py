"""
Persistent region knowledge base: an append-only snapshot log of every region
graph/nodes/infer_regions.py has ever produced, plus hybrid retrieval so a
later query's region-conditioned synthesis (see `condition_answer_for_region`,
a later phase) can draw on a PAST run's inferred worldview/priorities for a
similar chunk of India, without recomputing it from scratch.

Deliberately append-only, NOT identity-merge across runs -- unlike a fixed
administrative unit (a state code never changes), an agent-inferred region's
exact district membership genuinely differs run to run (different sourced
posts, different query framing, a different silhouette-sweep k). Trying to
maintain "this run's region == that run's region" identity would be the same
brittle-heuristic trap research_cache.py's own design already avoids for a
structurally identical problem (see that module's docstring) -- so instead,
every run's region output persists as its own immutable row, and retrieval
does the matching work at READ time via a hybrid signal instead of at WRITE
time via identity.

Two stores, linked by one uuid per snapshot (same linking pattern
research_cache.py already uses):
  - SQLite (`{DATA_DIR}/region_kb.db`): the region_snapshots table --
    district_ids/state_codes/worldview_text/confidence/provenance for every
    inferred region, ever. Answers "what did we learn about this district
    set / worldview before."
  - Chroma (`{DATA_DIR}/chroma_region_kb`, "region_worldviews" collection):
    bring-your-own-embeddings (embedding_function=None, same reasoning as
    research_cache.py) of each snapshot's `worldview_text`, embedded via the
    same local sentence-transformers model (`_local_semantic_embed`) used
    everywhere else in this codebase for embeddings -- kept independent of
    whichever provider answered the run that produced the snapshot.

Retrieval is HYBRID, not semantic-only: candidates are the union of
  (a) the top-N snapshots by deterministic Jaccard overlap of district_id
      sets (cheap, exact-geography signal, no embedding/network involved),
  (b) the top-N snapshots by semantic similarity of worldview_text to
      "{region_name}: {query}" (catches "differently-worded query, genuinely
      same underlying region" that pure district overlap would miss).
Every surviving candidate then goes to an LLM judgment call (mirroring
research_cache.py's `_judge_reusable`, but via the CALLING run's own
LLMClient -- see LLMClient.judge_text_relevance -- rather than a hardcoded
local Ollama model, since callers here already have `llm` in hand) deciding
whether that PAST region's worldview would meaningfully condition reasoning
about THIS new region/query. Every judge-approved candidate's text is
blended into one digest -- unlike research_cache.py's single-best-hit model,
MULTIPLE past snapshots may condition one synthesis call.

No hard TTL cutoff (a region's cultural/political worldview is far more
evergreen than research_cache.py's news/stats findings, which use a 30-day
guard) -- recency is left as an available ranking signal (`created_at` is
stored on every row) rather than a hard expiry that would silently discard a
still-useful old snapshot.

Every failure mode here (embedding error, Chroma unreachable/empty, judge
error, malformed row) degrades `get_region_conditioning` to returning `None`
-- exactly research_cache.py's own stated principle: this is a quality
enhancement, never a correctness dependency for the pipeline stage that
consumes it.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import TypedDict

from .config import DATA_DIR
from .connectors.base import LLMClient
from .connectors.llm import _local_semantic_embed

_CHROMA_PATH = f"{DATA_DIR}/chroma_region_kb"
_COLLECTION_NAME = "region_worldviews"
_DB_PATH = f"{DATA_DIR}/region_kb.db"

# How many candidates each retrieval pass contributes before the union is
# handed to the judge -- small on purpose, this is a conditioning digest for
# one synthesis call, not an exhaustive literature review.
_JACCARD_CANDIDATE_COUNT = 3
_SEMANTIC_CANDIDATE_COUNT = 3
# Deterministic overlap pass scans at most this many of the most-recent rows
# in Python (no district-set index in SQLite) -- bounds the scan cost as the
# kb grows without needing a second index structure for a check this cheap.
_JACCARD_SCAN_LIMIT = 500
# Below this, two district sets barely overlap -- not worth a judge call
# (the semantic pass is the right signal for that case, if anything is).
_MIN_JACCARD_TO_CONSIDER = 0.1

_collection = None  # lazily-created chromadb collection handle, module-level singleton


def _get_collection():
    global _collection
    if _collection is None:
        import chromadb  # local import: keep this optional dep lazy, same pattern as research_cache.py

        client = chromadb.PersistentClient(path=_CHROMA_PATH)
        _collection = client.get_or_create_collection(name=_COLLECTION_NAME, embedding_function=None)
    return _collection


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS region_snapshots (
            id TEXT PRIMARY KEY,
            query_run_id TEXT NOT NULL,
            source_query TEXT NOT NULL,
            region_name TEXT NOT NULL,
            district_ids_json TEXT NOT NULL,
            state_codes_json TEXT NOT NULL,
            worldview_text TEXT NOT NULL,
            confidence TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_region_snapshots_created_at ON region_snapshots(created_at)"
    )
    return conn


class RegionConditioning(TypedDict):
    """Returned by get_region_conditioning(). `digest` is ready to hand
    directly to condition_answer_for_region's `past_worldview` parameter
    (a later phase); `source_snapshot_ids`/`source_queries` are provenance,
    useful for logging/debugging which past runs contributed."""

    digest: str
    source_snapshot_ids: list[str]
    source_queries: list[str]


def _row_to_dict(row: tuple) -> dict:
    (
        id_, query_run_id, source_query, region_name,
        district_ids_json, state_codes_json, worldview_text, confidence, created_at,
    ) = row
    return {
        "id": id_,
        "query_run_id": query_run_id,
        "source_query": source_query,
        "region_name": region_name,
        "district_ids": json.loads(district_ids_json),
        "state_codes": json.loads(state_codes_json),
        "worldview_text": worldview_text,
        "confidence": confidence,
        "created_at": created_at,
    }


async def persist_region_snapshot(
    query_run_id: str,
    source_query: str,
    region_name: str,
    district_ids: list[str],
    state_codes: list[str],
    worldview_text: str,
    confidence: str,
) -> None:
    """Append one immutable snapshot. Best-effort: any failure is logged and
    swallowed -- losing one snapshot write is not a correctness problem for
    the run that produced it (see module docstring)."""
    if not worldview_text or not worldview_text.strip():
        return  # nothing worth persisting -- an empty digest can't condition anything later

    snapshot_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()

    try:
        embedding = (await _local_semantic_embed([worldview_text]))[0]
    except Exception as exc:  # noqa: BLE001
        print(f"[region_kb] embedding failed, skipping snapshot persist: {exc}", flush=True)
        return

    try:
        conn = _get_db()
        try:
            conn.execute(
                "INSERT INTO region_snapshots (id, query_run_id, source_query, region_name, "
                "district_ids_json, state_codes_json, worldview_text, confidence, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    snapshot_id,
                    query_run_id,
                    source_query,
                    region_name,
                    json.dumps(district_ids),
                    json.dumps(state_codes),
                    worldview_text,
                    confidence,
                    created_at,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        _get_collection().add(
            ids=[snapshot_id],
            embeddings=[embedding],
            metadatas=[
                {
                    "region_name": region_name,
                    "source_query": source_query,
                    "created_at": created_at,
                }
            ],
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[region_kb] failed to persist region snapshot: {exc}", flush=True)


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    intersection = len(a & b)
    if intersection == 0:
        return 0.0
    return intersection / len(a | b)


def _jaccard_candidates(district_ids: list[str], exclude_query_run_id: str | None) -> list[dict]:
    """Deterministic overlap pass over the most recent snapshots -- cheap,
    exact-geography signal, no embedding/network involved."""
    query_set = set(district_ids)
    if not query_set:
        return []
    try:
        conn = _get_db()
        try:
            rows = conn.execute(
                "SELECT id, query_run_id, source_query, region_name, district_ids_json, "
                "state_codes_json, worldview_text, confidence, created_at "
                "FROM region_snapshots ORDER BY created_at DESC LIMIT ?",
                (_JACCARD_SCAN_LIMIT,),
            ).fetchall()
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        print(f"[region_kb] Jaccard scan failed, skipping overlap candidates: {exc}", flush=True)
        return []

    scored: list[tuple[float, dict]] = []
    for row in rows:
        snap = _row_to_dict(row)
        if exclude_query_run_id and snap["query_run_id"] == exclude_query_run_id:
            continue
        score = _jaccard(query_set, set(snap["district_ids"]))
        if score >= _MIN_JACCARD_TO_CONSIDER:
            scored.append((score, snap))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [snap for _, snap in scored[:_JACCARD_CANDIDATE_COUNT]]


def _semantic_candidates(query_embedding: list[float], exclude_query_run_id: str | None) -> list[dict]:
    try:
        collection = _get_collection()
        count = collection.count()
        if count == 0:
            return []
        # Over-fetch a little past _SEMANTIC_CANDIDATE_COUNT since some
        # nearest neighbors may belong to the excluded run and get filtered
        # out below.
        result = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(_SEMANTIC_CANDIDATE_COUNT + 3, count),
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[region_kb] Chroma query failed, skipping semantic candidates: {exc}", flush=True)
        return []

    ids = (result.get("ids") or [[]])[0]
    if not ids:
        return []

    try:
        conn = _get_db()
        try:
            candidates: list[dict] = []
            for snapshot_id in ids:
                row = conn.execute(
                    "SELECT id, query_run_id, source_query, region_name, district_ids_json, "
                    "state_codes_json, worldview_text, confidence, created_at "
                    "FROM region_snapshots WHERE id = ?",
                    (snapshot_id,),
                ).fetchone()
                if row is None:
                    continue
                snap = _row_to_dict(row)
                if exclude_query_run_id and snap["query_run_id"] == exclude_query_run_id:
                    continue
                candidates.append(snap)
                if len(candidates) >= _SEMANTIC_CANDIDATE_COUNT:
                    break
            return candidates
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        print(f"[region_kb] semantic candidate lookup failed: {exc}", flush=True)
        return []


async def get_region_conditioning(
    llm: LLMClient,
    region_name: str,
    district_ids: list[str],
    query: str,
    exclude_query_run_id: str | None = None,
) -> RegionConditioning | None:
    """Returns a blended conditioning digest from every past snapshot judged
    still-relevant to this new region/query, or None if nothing qualifies or
    any step fails. `exclude_query_run_id` lets a caller mid-run avoid
    matching against snapshots this SAME run already wrote -- relevant once
    a later phase wires this live, since persist-then-immediately-read
    within one run would otherwise trivially "match" itself."""
    jaccard_hits = _jaccard_candidates(district_ids, exclude_query_run_id)

    semantic_hits: list[dict] = []
    try:
        query_embedding = (await _local_semantic_embed([f"{region_name}: {query}"]))[0]
        semantic_hits = _semantic_candidates(query_embedding, exclude_query_run_id)
    except Exception as exc:  # noqa: BLE001
        print(f"[region_kb] embedding failed, skipping semantic candidates: {exc}", flush=True)

    seen_ids: set[str] = set()
    candidates: list[dict] = []
    for snap in (*jaccard_hits, *semantic_hits):
        if snap["id"] in seen_ids:
            continue
        seen_ids.add(snap["id"])
        candidates.append(snap)

    if not candidates:
        return None

    approved: list[dict] = []
    for snap in candidates:
        question = (
            f'A past run inferred a region "{snap["region_name"]}" (query at the time: '
            f'"{snap["source_query"]}") with this worldview/priorities digest: '
            f'"{snap["worldview_text"]}"\n\n'
            f'Would this meaningfully help condition reasoning about a NEW region, '
            f'"{region_name}", for the current query "{query}"? Answer "yes" only if the '
            "district overlap or thematic content genuinely carries over, not just superficially "
            "similar wording."
        )
        try:
            if await llm.judge_text_relevance(question):
                approved.append(snap)
        except Exception as exc:  # noqa: BLE001
            print(f"[region_kb] judge call failed for snapshot {snap['id']}: {exc}", flush=True)

    if not approved:
        return None

    digest_parts = [
        f'From a past run on "{snap["source_query"]}" (region "{snap["region_name"]}"): '
        f'{snap["worldview_text"]}'
        for snap in approved
    ]
    return RegionConditioning(
        digest="\n\n".join(digest_parts),
        source_snapshot_ids=[snap["id"] for snap in approved],
        source_queries=[snap["source_query"] for snap in approved],
    )
