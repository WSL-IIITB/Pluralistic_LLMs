"""
Write the stunting study's lens on each of the 12 researched (curated) personas -- the counterpart of their dropout
study lens -- into src/lib/worldview/personaCards/stuntingLens/<region>.json. Kept OUT of the persona card.

    cd backend && .venv/bin/python ../scripts/build_stunting_lenses.py

For each persona: its district's top three prescribed factors in the NITI stunting model (default 20% target), and
Claude's reading of how each could reach THIS household, built only from facts on the persona's card and written
conditionally (most of these households have no child under five). Labelled in the UI as an interpretation.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from app.config import get_settings  # noqa: E402
from app.connectors.llm import get_llm_client  # noqa: E402
from app.persona_library import CURATED_DISTRICTS  # noqa: E402
from app.stunting import model  # noqa: E402

CARDS = os.path.join(ROOT, "src", "lib", "worldview", "personaCards")
OUT = os.path.join(CARDS, "stuntingLens")

SYSTEM = (
    "You write the stunting study's reading of ONE composite persona's household, for a dashboard section labelled "
    "as an interpretation. Use ONLY facts on the persona card; never invent family members, ages, numbers or places. "
    "Most households here have no child under five: then say so plainly and write about how the factor could reach "
    "the household's young relatives, a future pregnancy, or neighbours' children, conditionally ('if...'). No numbers "
    "except those on the card. Plain text.\n"
    'Respond with JSON: {"underFive": str (<= 25 words: whether the card shows a child under five in this household), '
    '"effects": [{"factor": str (exact factor name given), "effect": str (<= 35 words)}] (one per factor, same order)}'
)


async def main() -> None:
    llm = get_llm_client(get_settings(), "azure_anthropic")
    m = model()
    info = {f["name"]: f for f in m["factors"]}
    os.makedirs(OUT, exist_ok=True)
    by_region: dict[str, dict] = {}

    async def one(region_id: str, gender: str, district_id: str) -> None:
        with open(os.path.join(CARDS, f"{region_id}.json"), encoding="utf-8") as fh:
            card = json.load(fh)[gender]
        d = m["districts"].get(district_id) or {}
        if d.get("stunting") is None:
            by_region.setdefault(region_id, {})[gender] = {"districtId": district_id, "noData": True}
            return
        top = d["factors"][:3]
        facts = {k: card[k] for k in ("name", "ageLabel", "role", "place", "community", "household", "vitals", "dayInLife", "worries")}
        user = {"card": facts, "district": d["area"], "district_stunting_pct": d["stunting"],
                "factors": [{"name": f["name"], "short": info[f["name"]]["short"], "measures": info[f["name"]]["measures"],
                             "district_value_pct": f["value"], "model_needs_pct": f["prescribed"]} for f in top]}
        out = await llm._chat_json(SYSTEM, json.dumps(user, ensure_ascii=False), timeout=120.0)
        effects = {e.get("factor"): str(e.get("effect", "")) for e in out.get("effects") or [] if isinstance(e, dict)}
        by_region.setdefault(region_id, {})[gender] = {
            "districtId": district_id,
            "underFive": str(out.get("underFive", "")),
            "changes": [{"factor": f["name"], "effect": effects.get(f["name"], "")} for f in top],
        }
        print(f"  {region_id}/{gender}: {[c['effect'][:50] for c in by_region[region_id][gender]['changes']]}", flush=True)

    await asyncio.gather(*(one(r, g, d) for (r, g), d in CURATED_DISTRICTS.items()))
    for region_id, lenses in by_region.items():
        with open(os.path.join(OUT, f"{region_id}.json"), "w", encoding="utf-8") as fh:
            json.dump(dict(sorted(lenses.items(), key=lambda kv: kv[0] != "male")), fh, ensure_ascii=False, indent=2)
            fh.write("\n")
    print("wrote", len(by_region), "files to", os.path.relpath(OUT, ROOT))


if __name__ == "__main__":
    asyncio.run(main())
