"""
Separate the curated persona cards from the dropout study.

    cd backend && .venv/bin/python ../scripts/split_persona_cards.py [--provider azure_anthropic]

1. Moves the study fields (`schoolPressures`, `factorEffects`, `dataLens`) out of
   src/lib/worldview/personaCards/<region>.json into personaCards/studyLens/<region>.json.
   The card keeps only the person; the Personas tab shows the study lens as its own,
   clearly separate section.
2. Drops dropout-rate `stat`s and dropout "worries" chips from the cards.
3. Re-distils any card topic whose headline or points still frame school dropout, from
   the (already neutralised) persona text in backend/app/data/personas/.
"""

from __future__ import annotations

import argparse
import asyncio
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from app.config import get_settings  # noqa: E402
from app.connectors.llm import get_llm_client  # noqa: E402
from app.karnataka import load_persona  # noqa: E402

CARDS = os.path.join(ROOT, "src", "lib", "worldview", "personaCards")
LENS = os.path.join(CARDS, "studyLens")
STUDY_FIELDS = ("schoolPressures", "factorEffects", "dataLens")
DROPOUT = re.compile(r"drop[- ]?out|dropping out|leaving school|tip into leaving|out of school", re.I)

SYSTEM = (
    "Distil ONE topic of a persona profile into a display-card entry. Use only facts in the text; "
    "never invent names or numbers. Do not mention school dropout or dropout rates. Plain text.\n"
    'Respond with JSON: {"headline": str (<= 12 words), "points": [str, str, str] (each <= 20 words), '
    '"stat": {"value": str, "label": str} (OPTIONAL -- only a number stated in the text, never a dropout rate)}'
)


def card_text(t: dict) -> list[str]:
    return [t["headline"], *t["points"], (t.get("stat") or {}).get("label", "")]


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="azure_anthropic")
    args = ap.parse_args()
    llm = get_llm_client(get_settings(), args.provider)
    os.makedirs(LENS, exist_ok=True)

    for path in sorted(glob.glob(os.path.join(CARDS, "*.json"))):
        region_id = os.path.basename(path)[:-5]
        with open(path, encoding="utf-8") as fh:
            cards = json.load(fh)
        lens_path = os.path.join(LENS, f"{region_id}.json")
        lens = {}
        if os.path.isfile(lens_path):
            with open(lens_path, encoding="utf-8") as fh:
                lens = json.load(fh)

        for gender, card in cards.items():
            moved = {k: card.pop(k) for k in STUDY_FIELDS if k in card}
            if moved:
                lens[gender] = {**lens.get(gender, {}), **moved}
            card["worries"] = [w for w in card.get("worries", []) if not DROPOUT.search(w)]
            profile = {k: t for k, t in load_persona(region_id, gender)["topics"].items()}
            for t in card["topics"]:
                if t.get("stat") and DROPOUT.search(t["stat"].get("label", "")):
                    t.pop("stat")
                if not any(DROPOUT.search(s) for s in card_text(t)):
                    continue
                source = (profile.get(t["key"]) or {}).get("regional_profile") or ""
                data = await llm._chat_json(SYSTEM, source, timeout=120.0)
                t["headline"] = str(data.get("headline") or t["headline"]).strip()
                pts = [str(p).strip() for p in data.get("points") or [] if str(p).strip()]
                if len(pts) >= 3:
                    t["points"] = pts[:3]
                stat = data.get("stat")
                if isinstance(stat, dict) and stat.get("value") and not DROPOUT.search(str(stat.get("label", ""))):
                    t["stat"] = {"value": str(stat["value"]), "label": str(stat.get("label") or "")}
                print(f"  {region_id}/{gender} {t['key']}: {t['headline']}")

        with open(path, "w", encoding="utf-8") as fh:
            json.dump(cards, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        with open(lens_path, "w", encoding="utf-8") as fh:
            json.dump(lens, fh, ensure_ascii=False, indent=2)
            fh.write("\n")


if __name__ == "__main__":
    asyncio.run(main())
