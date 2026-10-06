"""
Write the JSON snapshots the GitHub Pages build reads in place of the backend:

    public/data/districts.json            <- GET /api/karnataka/districts
    public/data/personas.json             <- GET /api/personas
    public/data/districts-research.json   <- GET /api/karnataka/districts-research
    public/data/default-run.json          <- the newest saved run that has both Story-vs-UIDAI/NITI
                                             and persona-similarity results (what the dashboard opens on)

Needs the backend running (default http://localhost:8001):

    python3 scripts/export_static_data.py [--backend http://localhost:8001]

Re-run it and commit public/data/ whenever the research, personas or the chosen run change.
The default run is exported without the research snapshot it may carry -- the static build
always uses the research file next to it.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request

BACKEND = "http://localhost:8001"
if "--backend" in sys.argv:
    BACKEND = sys.argv[sys.argv.index("--backend") + 1].rstrip("/")

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "public", "data")


def get(path: str):
    with urllib.request.urlopen(f"{BACKEND}{path}", timeout=60) as r:
        return json.load(r)


def write(name: str, data) -> None:
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"  {name}: {os.path.getsize(path) // 1024} KB")


def main() -> None:
    print("exporting static data from", BACKEND)
    write("districts.json", get("/api/karnataka/districts"))
    write("personas.json", get("/api/personas"))
    write("districts-research.json", get("/api/karnataka/districts-research"))

    chosen = None
    for summary in get("/api/worldview/runs?limit=60"):  # newest first
        run = get(f"/api/worldview/runs/{summary['id']}")
        if run.get("storyVsOfficial") and run.get("personaSimilarity"):
            chosen = run
            break
    if not chosen:
        print("  ! no saved run has both Story-vs-UIDAI/NITI and persona-similarity results; default-run.json not written")
        return
    chosen.pop("districtResearch", None)
    write("default-run.json", chosen)
    print(f"  default run: {chosen['id']} ({chosen['mode']}, '{chosen['query']}')")


if __name__ == "__main__":
    main()
