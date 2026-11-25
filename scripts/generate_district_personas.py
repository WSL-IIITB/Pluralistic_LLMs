"""
Generate the district persona library's missing slots -- a man and a woman per district.

    cd backend
    .venv/bin/python ../scripts/generate_district_personas.py --district 29-577     # one district (pilot)
    .venv/bin/python ../scripts/generate_district_personas.py --all                 # every empty slot
    .venv/bin/python ../scripts/generate_district_personas.py --all --dry-run       # list what would be made

Slots held by a researched (curated) persona are skipped, and so are slots already generated
unless --overwrite. Each persona is written to backend/app/data/persona_library/generated/
<districtId>-<gender>.json. Two LLM calls per persona (profile text, then its card).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from app import persona_library as lib  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.connectors.llm import get_llm_client  # noqa: E402


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--district", action="append", default=[], help="district id, e.g. 29-577 (repeatable)")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--gender", choices=lib.GENDERS)
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--provider", default="azure_anthropic")
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument("--diversify", action="store_true",
                    help="regenerate generated personas that repeat a name, overuse an occupation or sit in the wrong district")
    args = ap.parse_args()

    if args.diversify:
        return await diversify(args)
    districts = [d["districtId"] for d in lib.districts()] if args.all else args.district
    if not districts:
        ap.error("pass --district <id> or --all")
    known = {d["districtId"] for d in lib.districts()}
    bad = [d for d in districts if d not in known]
    if bad:
        ap.error(f"unknown district(s): {bad}")

    existing = {(p["districtId"], p["gender"]): p["source"] for p in lib.all_personas() if p["source"] != "custom"}
    jobs = []
    for did in districts:
        for g in [args.gender] if args.gender else lib.GENDERS:
            src = existing.get((did, g))
            if src == "curated" or (src == "generated" and not args.overwrite):
                continue
            jobs.append((did, g))
    names = lib.district_by_id()
    print(f"{len(jobs)} persona(s) to generate: " + ", ".join(f"{names[d]['name']}/{g}" for d, g in jobs))
    if args.dry_run or not jobs:
        return

    llm = get_llm_client(get_settings(), args.provider)
    sem = asyncio.Semaphore(args.concurrency)
    failed = []

    async def one(did: str, g: str) -> None:
        async with sem:
            for attempt in range(2):
                try:
                    draft = await lib.generate(llm, district_id=did, gender=g, provider=args.provider)
                    saved = lib.save_generated(draft)
                    card = saved.get("card") or {}
                    print(f"  ok   {names[did]['name']}/{g}: {card.get('name')} -- {card.get('role')}, {card.get('place')}", flush=True)
                    return
                except Exception as exc:  # noqa: BLE001
                    print(f"  fail {names[did]['name']}/{g} (attempt {attempt + 1}): {exc}", flush=True)
            failed.append(f"{did}-{g}")

    await asyncio.gather(*(one(d, g) for d, g in jobs))
    if failed:
        print("failed:", ", ".join(failed))
        sys.exit(1)


FAMILIES = {  # occupation families capped at 2 generated personas each (anganwadi at 3)
    "anganwadi": ("anganwadi",), "sericulture": ("silk", "cocoon", "reel", "sericulture", "mulberry"),
    "pepper": ("pepper",), "oil mill": ("oil mill", "oil press"), "coconut": ("coconut", "copra"),
    "dal mill": ("dal mill",), "tomato": ("tomato",), "cashew": ("cashew",), "stone": ("stone", "quarry"),
}


def full_families(exclude: str | None = None) -> list[str]:
    """Occupation words of every family already at its cap among generated personas (other than `exclude`)."""
    used: dict[str, int] = {}
    for r in lib.all_personas():
        if r["source"] != "generated" or r["id"] == exclude:
            continue
        role = ((r.get("card") or {}).get("role") or "").lower()
        for fam, words in FAMILIES.items():
            if any(w in role for w in words):
                used[fam] = used.get(fam, 0) + 1
    return [w for fam, words in FAMILIES.items() if used.get(fam, 0) >= (3 if fam == "anganwadi" else 2) for w in words]


def repeats() -> list[dict]:
    """Generated personas to redo: every repeat of a first name after the first, anganwadi workers
    after the first three, and anyone placed outside their district. Curated personas are kept."""
    recs = lib.all_personas()
    seen_names = {(r.get("card") or {}).get("name") for r in recs if r["source"] == "curated"}
    families = FAMILIES
    _ = {  # (kept for reference; see FAMILIES)
        "anganwadi": ("anganwadi",), "sericulture": ("silk", "cocoon", "reel", "sericulture", "mulberry"),
        "pepper": ("pepper",), "oil mill": ("oil mill", "oil press"), "coconut": ("coconut", "copra"),
        "dal mill": ("dal mill",), "tomato": ("tomato",), "cashew": ("cashew",), "stone": ("stone", "quarry"),
    }
    used: dict[str, int] = {}
    redo = []
    for r in sorted((r for r in recs if r["source"] == "generated"), key=lambda r: r["id"]):
        card = r.get("card") or {}
        name, role = card.get("name"), (card.get("role") or "").lower()
        bad = name in seen_names or lib._misplaced(r) is not None
        for fam, words in families.items():
            if any(w in role for w in words):
                used[fam] = used.get(fam, 0) + 1
                bad = bad or used[fam] > (3 if fam == "anganwadi" else 2)
        if bad:
            redo.append(r)
        else:
            seen_names.add(name)
    return redo


async def diversify(args) -> None:
    redo = repeats()
    print(f"{len(redo)} persona(s) to regenerate: " + ", ".join(f"{r['id']} ({(r.get('card') or {}).get('name')}, {(r.get('card') or {}).get('role')})" for r in redo))
    if args.dry_run or not redo:
        return
    llm = get_llm_client(get_settings(), args.provider)
    failed = []
    # One at a time, so each new persona sees the names and jobs the previous one took.
    for r in redo:
        banned = full_families(exclude=r["id"])
        for attempt in range(3):
            try:
                draft = await lib.generate(llm, district_id=r["districtId"], gender=r["gender"], provider=args.provider,
                                           replacing=r["id"], banned_occupations=banned)
                saved = lib.save_generated(draft)
                card = saved.get("card") or {}
                print(f"  ok   {r['districtName']}/{r['gender']}: {card.get('name')} -- {card.get('role')}, {card.get('place')}", flush=True)
                break
            except Exception as exc:  # noqa: BLE001
                print(f"  fail {r['id']} (attempt {attempt + 1}): {exc}", flush=True)
        else:
            failed.append(r["id"])
    if failed:
        print("failed (kept as they were):", ", ".join(failed))


if __name__ == "__main__":
    asyncio.run(main())
