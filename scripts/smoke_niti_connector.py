"""Smoke-test the NitiCsvConnector against the REAL /niti CSVs (no network).
Run: scripts/.smoke-venv/Scripts/python scripts/smoke_niti_connector.py  (from repo root)
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.config import get_settings  # noqa: E402
from app.connectors.sources import get_niti_connector, NitiCsvConnector  # noqa: E402


async def main() -> None:
    settings = get_settings()
    print(f"has_niti_csv={settings.has_niti_csv}  dir={settings.niti_csv_dir()}")
    csv = get_niti_connector(settings)
    print(f"connector={type(csv).__name__}")

    cases = [
        ("dropout rate in kerala", 20),
        ("high school dropouts", 40),
        ("internet access", 15),
        ("gangtok sikkim", 10),
        ("sanitation", 10),
        ("diwali", 10),  # expect zero: no row token matches
        ("girls 10+ years schooling", 12),
    ]
    for query, limit in cases:
        posts = await csv.search(query, limit)
        n = len(posts)
        states = sorted({p["text"].split(", ")[-1].split(" — ")[0] for p in posts})
        print(f"\n### {query!r} -> {n} posts, {len(states)} states")
        for p in posts[:5]:
            print(f"  [{p['platform']}] {p['id']}  {p['text'][:110]}")
        if states:
            print("  states:", ", ".join(states[:12]))
        if n:
            assert all(p["platform"] == "niti" for p in posts), "platform must be niti"
            assert all(p["id"].startswith("niti_") for p in posts), "id prefix niti_"
            # no duplicate (state,district) within one search's first limit
            keys = [p["text"].split(" — ")[0] for p in posts]
            assert len(keys) == len(set(keys)), f"duplicate rows within one search: {keys}"

    # determinism: same query, same results
    a = await csv.search("dropout rate in kerala", 20)
    b = await csv.search("dropout rate in kerala", 20)
    assert [p["id"] for p in a] == [p["id"] for p in b], "nondeterministic results"
    print("\nOK: connector smoke test passed")


if __name__ == "__main__":
    asyncio.run(main())