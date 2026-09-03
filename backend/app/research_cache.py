"""
Research-sources cache: an LLM-judged semantic cache so a near-duplicate
query reuses previously-gathered ResearchDocuments instead of re-running the
full `LLMClient.research()` fan-out from scratch.

Two stores, linked by one uuid per cached query:
  - Chroma (`{DATA_DIR}/chroma_cache`, "research_queries" collection):
    bring-your-own-embeddings (embedding_function=None -- we always pass
    embeddings computed via the SAME local sentence-transformers model
    already used for clustering, connectors.llm._local_semantic_embed, so
    there's no second onnxruntime-based embedding stack). Answers "which
    past queries are semantically closest to this one."
  - SQLite (`{DATA_DIR}/research_cache.db`): the findings text and
    ResearchDocument rows for each cached query. Answers "what were the
    actual sources for that one."

Cache-hit decision is an LLM judgment call, not a fixed similarity cutoff --
same reasoning as graph/build.py's `_filter_by_relevance`: a threshold could
not cleanly separate "close enough to reuse" from "similar wording, different
intent" in testing there, so this asks the actual question in words. The
judge runs through the run's OWN LLMClient (llm.judge_text_relevance),
same as the relevance filter and for the same reason -- see that function's
own docstring in graph/build.py for why this used to hardcode a separate
local model and no longer does.

Wraps `llm.research()` rather than changing the LLMClient protocol -- cache
logic lives in one place regardless of which provider is active. Every
failure mode here (embedding error, Chroma unreachable/empty, judge error,
malformed cache row) degrades to a plain `llm.research()` call, exactly
today's behavior -- caching is a speed/cost optimization, never a
correctness dependency.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

from .config import DATA_DIR
from .connectors.base import LLMClient
from .connectors.llm import _local_semantic_embed
from .reasoning_modes import ResearchMode

_CHROMA_PATH = f"{DATA_DIR}/chroma_cache"
_COLLECTION_NAME = "research_queries"
_DB_PATH = f"{DATA_DIR}/research_cache.db"

# Cultural/evergreen topics don't go stale, but policy/stats topics do, and
# the LLM judge has no way to know the underlying facts changed since last
# time -- staleness is a different axis than topical similarity, so this
# stays a fixed guard rather than something the judge weighs in on.
_CACHE_TTL_DAYS = 30
_CANDIDATE_COUNT = 3
# A cache hit still runs a small top-up search (not zero) to catch anything
# new since the cached run, at a fraction of the full per-mode breadth.
_TOPUP_BREADTH = 2

_collection = None  # lazily-created chromadb collection handle, module-level singleton


def _get_collection():
    global _collection
    if _collection is None:
        import chromadb  # local import: keep this optional dep lazy, same pattern as other connectors

        client = chromadb.PersistentClient(path=_CHROMA_PATH)
        _collection = client.get_or_create_collection(name=_COLLECTION_NAME, embedding_function=None)
    return _collection


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cached_queries (
            id TEXT PRIMARY KEY,
            query_text TEXT NOT NULL,
            findings TEXT NOT NULL,
            mode TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cached_documents (
            row_id INTEGER PRIMARY KEY AUTOINCREMENT,
            query_id TEXT NOT NULL,
            url TEXT NOT NULL,
            title TEXT,
            domain TEXT,
            snippet TEXT
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cached_documents_query_id ON cached_documents(query_id)")
    # Added after the table shipped, so existing databases need the column
    # backfilled rather than just a widened CREATE above. `geo_text` is the
    # longer body text used for geography extraction (see connectors/llm.py's
    # _GEO_TEXT_CHARS) -- without persisting it, a cache HIT would silently
    # lose it and every cached document would fall back to its short display
    # snippet, which is exactly the too-little-text problem it exists to fix.
    existing_columns = {row[1] for row in conn.execute("PRAGMA table_info(cached_documents)")}
    if "geo_text" not in existing_columns:
        conn.execute("ALTER TABLE cached_documents ADD COLUMN geo_text TEXT")
        conn.commit()
    return conn


async def _judge_reusable(llm: LLMClient, new_query: str, candidate_query: str) -> bool:
    """Would sources already gathered for `candidate_query` still usefully
    answer `new_query`? Routed through the run's own LLMClient
    (llm.judge_text_relevance) rather than a separately-hardcoded local
    model -- see graph/build.py's _filter_by_relevance for the identical
    reasoning (a hardcoded model tag not being pulled locally silently broke
    this gate in practice). Fails CLOSED (treated as not reusable) on any
    error, per judge_text_relevance's own documented contract -- the opposite
    of _filter_by_relevance's fail-open, because a false "hit" here would
    silently serve stale/wrong sources, whereas a false miss just costs one
    ordinary `research()` call (today's default behavior anyway)."""
    question = (
        f'Query A (new): "{new_query}"\n'
        f'Query B (already researched): "{candidate_query}"\n\n'
        "Would web sources already gathered for query B still usefully and accurately "
        "answer query A? Answer \"yes\" only if B's sources would substantively cover "
        "A's actual topic/intent, not just similar wording."
    )
    return await llm.judge_text_relevance(question)


def _doc_rows(query_id: str, documents: list[dict]) -> list[tuple]:
    return [
        (query_id, d["url"], d.get("title", ""), d.get("domain", ""), d.get("snippet", ""), d.get("geo_text", ""))
        for d in documents
        if d.get("url")
    ]


def _persist_new(query_id: str, query_text: str, mode: ResearchMode, findings: str, documents: list[dict]) -> None:
    conn = _get_db()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO cached_queries (id, query_text, findings, mode, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (query_id, query_text, findings, mode, datetime.now(timezone.utc).isoformat()),
        )
        conn.executemany(
            "INSERT INTO cached_documents (query_id, url, title, domain, snippet, geo_text) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            _doc_rows(query_id, documents),
        )
        conn.commit()
    finally:
        conn.close()


def _append_documents(query_id: str, documents: list[dict]) -> None:
    rows = _doc_rows(query_id, documents)
    if not rows:
        return
    conn = _get_db()
    try:
        conn.executemany(
            "INSERT INTO cached_documents (query_id, url, title, domain, snippet, geo_text) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def _load_cached(query_id: str) -> tuple[str, list[dict]] | None:
    conn = _get_db()
    try:
        row = conn.execute("SELECT findings FROM cached_queries WHERE id = ?", (query_id,)).fetchone()
        if row is None:
            return None
        doc_rows = conn.execute(
            "SELECT url, title, domain, snippet, geo_text FROM cached_documents WHERE query_id = ?",
            (query_id,),
        ).fetchall()
        documents = [
            {"url": u, "title": t, "domain": d, "snippet": s, "geo_text": g or ""}
            for u, t, d, s, g in doc_rows
        ]
        return row[0], documents
    finally:
        conn.close()


def _merge_documents(cached: list[dict], fresh: list[dict]) -> list[dict]:
    """Dedupe by URL (cached first -- the top-up call only contributes NEW
    urls), renumbering to 1-based order-of-first-appearance, matching the
    id-assignment convention every LLMClient.research() implementation
    already uses for its own AnswerSegment.citations."""
    merged: list[dict] = []
    seen: set[str] = set()
    for d in (*cached, *fresh):
        url = d.get("url")
        if not url or url in seen:
            continue
        seen.add(url)
        merged.append(dict(d))
    for i, d in enumerate(merged, 1):
        d["id"] = i
    return merged


def _nearest_fresh_candidate(collection, query_embedding: list[float]) -> tuple[str, str] | None:
    """Query Chroma for the closest surviving (non-TTL-expired) candidate.
    Candidates come back nearest-first, so the first one that clears the TTL
    guard is the one worth asking the judge about."""
    try:
        count = collection.count()
        if count == 0:
            return None
        result = collection.query(
            query_embeddings=[query_embedding], n_results=min(_CANDIDATE_COUNT, count)
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[research_cache] Chroma query failed, skipping cache: {exc}", flush=True)
        return None

    ids = (result.get("ids") or [[]])[0]
    metadatas = (result.get("metadatas") or [[]])[0]
    cutoff = datetime.now(timezone.utc) - timedelta(days=_CACHE_TTL_DAYS)
    for cand_id, metadata in zip(ids, metadatas):
        metadata = metadata or {}
        try:
            created_dt = datetime.fromisoformat(metadata.get("created_at", ""))
        except ValueError:
            continue
        if created_dt < cutoff:
            continue
        return cand_id, metadata.get("query_text", "")
    return None


async def get_research(
    llm: LLMClient,
    query: str,
    known_framings: list[str],
    breadth: int,
    mode: ResearchMode,
) -> tuple[str, list[dict]]:
    """Drop-in replacement for `llm.research(...)`. On a cache hit, runs a
    small top-up search and merges it with cached sources instead of the
    full breadth-N fan-out; on a miss, runs the full research call and
    persists it for future reuse."""
    try:
        query_embedding = (await _local_semantic_embed([query]))[0]
    except Exception as exc:  # noqa: BLE001
        print(f"[research_cache] embedding failed, skipping cache: {exc}", flush=True)
        return await llm.research(query, known_framings, breadth, mode)

    collection = _get_collection()
    candidate = _nearest_fresh_candidate(collection, query_embedding)

    if candidate is not None:
        candidate_id, candidate_query_text = candidate
        if await _judge_reusable(llm, query, candidate_query_text):
            cached = _load_cached(candidate_id)
            if cached is not None:
                cached_findings, cached_documents = cached
                print(
                    f"[research_cache] cache HIT for {query!r} (~= {candidate_query_text!r}); "
                    f"running a breadth={_TOPUP_BREADTH} top-up instead of full research",
                    flush=True,
                )
                fresh_findings, fresh_documents = await llm.research(
                    query, known_framings, _TOPUP_BREADTH, mode
                )
                merged_documents = _merge_documents(cached_documents, fresh_documents)
                merged_findings = "\n\n".join(p for p in (cached_findings, fresh_findings) if p).strip()
                try:
                    _append_documents(candidate_id, fresh_documents)
                except Exception as exc:  # noqa: BLE001
                    print(f"[research_cache] failed to append top-up docs to cache: {exc}", flush=True)
                return merged_findings, merged_documents

    # Miss: no candidates, all TTL-expired, or the judge said no.
    findings, documents = await llm.research(query, known_framings, breadth, mode)
    try:
        query_id = str(uuid.uuid4())
        collection.add(
            ids=[query_id],
            embeddings=[query_embedding],
            metadatas=[
                {
                    "query_text": query,
                    "framings_json": json.dumps(known_framings),
                    "mode": mode,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            ],
        )
        _persist_new(query_id, query, mode, findings, documents)
    except Exception as exc:  # noqa: BLE001
        print(f"[research_cache] failed to persist new cache entry: {exc}", flush=True)
    return findings, documents
