"""
Saved-run history: stores a completed run's fully-rendered frontend state
(districts/clusters/deflections/answer/etc., exactly as the dashboard last
displayed it) so it can be reopened later, in this browser or another.

Deliberately opaque: this module doesn't know or care about the internal
shape of the JSON blob it stores -- that's the frontend's `SavedRunData`
type (src/lib/worldview/store.ts), not this module's concern. By the time a
run finishes, the frontend already holds fully-transformed, UI-ready data
(districts with assigned colors, ordered clusters, a resolved answer) --
storing that directly avoids re-deriving it from the backend's own
`PipelineState`, which holds pre-transformation raw dicts in a different
shape and is discarded once a run completes anyway (see main.py's stream()).

Same stdlib-sqlite3 pattern as research_cache.py: a fresh connection per
call, `CREATE TABLE IF NOT EXISTS` at the top of every connection, no new
dependency, no ORM.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from .config import DATA_DIR

_DB_PATH = f"{DATA_DIR}/run_history.db"


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS saved_runs (
            id TEXT PRIMARY KEY,
            query TEXT NOT NULL,
            query_type TEXT NOT NULL,
            mode TEXT NOT NULL,
            provider TEXT NOT NULL,
            created_at TEXT NOT NULL,
            districts_count INTEGER NOT NULL,
            clusters_count INTEGER NOT NULL,
            deflections_count INTEGER NOT NULL,
            data TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_saved_runs_created_at ON saved_runs(created_at)")
    # Runs saved before the Karnataka pivot are India-wide, district-level.
    columns = {row[1] for row in conn.execute("PRAGMA table_info(saved_runs)")}
    if "scope" not in columns:
        conn.execute("ALTER TABLE saved_runs ADD COLUMN scope TEXT NOT NULL DEFAULT 'india-districts'")
    return conn


def save_run(payload: dict) -> dict:
    """Persist one completed run. `payload` is the frontend's SavedRunData
    dict, verbatim -- stored as an opaque JSON blob (`data`), with a few
    scalar fields pulled out into real columns purely so `list_runs` can stay
    a cheap flat SELECT with no JSON parsing. `created_at` is stamped here
    (server clock), never trusted from the client -- same reasoning as
    research_cache.py's own timestamps."""
    run_id = payload["id"]
    created_at = datetime.now(timezone.utc).isoformat()
    conn = _get_db()
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO saved_runs
                (id, query, query_type, mode, provider, created_at,
                 districts_count, clusters_count, deflections_count, data, scope)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                payload["query"],
                payload["queryType"],
                payload["mode"],
                payload["provider"],
                created_at,
                len(payload.get("regionStats") or payload.get("districts") or {}),
                len(payload.get("clusters") or {}),
                len(payload.get("deflections") or []),
                json.dumps(payload),
                "karnataka-regions" if "regionStats" in payload else "india-districts",
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return {"id": run_id, "createdAt": created_at}


def list_runs(limit: int = 50) -> list[dict]:
    """Lightweight summaries only (no `data` column) -- ordered newest first."""
    conn = _get_db()
    try:
        rows = conn.execute(
            """
            SELECT id, query, query_type, mode, provider, created_at,
                   districts_count, clusters_count, deflections_count, scope
            FROM saved_runs ORDER BY created_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "id": r[0],
            "query": r[1],
            "queryType": r[2],
            "mode": r[3],
            "provider": r[4],
            "createdAt": r[5],
            "areasCount": r[6],
            "clustersCount": r[7],
            "deflectionsCount": r[8],
            "scope": r[9],
        }
        for r in rows
    ]


def get_run(run_id: str) -> dict | None:
    """The full SavedRunData dict for one run, or None if it doesn't exist."""
    conn = _get_db()
    try:
        row = conn.execute("SELECT data FROM saved_runs WHERE id = ?", (run_id,)).fetchone()
    finally:
        conn.close()
    return json.loads(row[0]) if row else None


def delete_run(run_id: str) -> bool:
    """True if a row was actually deleted, False if `run_id` didn't exist."""
    conn = _get_db()
    try:
        cur = conn.execute("DELETE FROM saved_runs WHERE id = ?", (run_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()
