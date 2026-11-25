"""
Take the school-dropout study out of the curated persona text, so a persona describes a person
rather than an answer to the dropout study.

    cd backend && .venv/bin/python ../scripts/neutralize_personas.py [--dry-run] [--provider azure_anthropic]

Sentence DELETION only -- the model never rewrites text. Each topic is split into numbered
sentences; the model returns the numbers of the sentences that belong to the study (reasons,
pressures or risks that could take children out of school, dropout/out-of-school/pass-rate
statistics, how the person would explain or frame dropout). Those sentences are dropped and every
other sentence is kept verbatim. Topic definitions are reset to the neutral wording in
app/persona_library.py.

Every deleted sentence is written to docs/persona-research/neutralized-deletions.md for review.
Run it on the committed originals (git checkout backend/app/data/personas/ first); the originals
stay in git history.
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
from app.persona_library import TOPICS  # noqa: E402

PERSONA_DIR = os.path.join(ROOT, "backend", "app", "data", "personas")
REPORT = os.path.join(ROOT, "docs", "persona-research", "neutralized-deletions.md")
DROPOUT = re.compile(
    r"drop[- ]?out|dropping out|leav\w* school|left school|out of school|out-of-school|"
    r"pull\w* (?:\w+ ){0,3}out of school|absentee|pass rate|pass percentage",
    re.I,
)
ALWAYS = {"education_and_schooling", "worldview_and_concerns"}
TOPIC_DEFS = {k: d for k, _, d in TOPICS}
_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\"'])")

SYSTEM = (
    "You are given the numbered sentences of one section of a persona profile. The persona must "
    "describe a PERSON, independent of a study of secondary-school dropout. Return the numbers of the "
    "sentences to DELETE. Delete a sentence ONLY if its main content is one of:\n"
    "(a) general patterns of why children in the area/region/state leave school (other families, "
    "'children like theirs', documented patterns), or an analysis listing the pressures, risks or "
    "barriers that could push this household's children out of school;\n"
    "(b) dropout, out-of-school, pass-rate or retention statistics;\n"
    "(c) how this person would explain, frame, blame or fix school dropout, including notes such as "
    "'(This is an inference...)' that belong to such a sentence.\n"
    "NEVER delete a sentence that states a fact about this household: how far the person or their "
    "spouse studied (even if it says why they stopped), where and in what class each child studies "
    "now, a decision the family is weighing about a child's next school or college, costs, transport, "
    "hopes, language-medium worries. Never delete sentences about health, work, water, politics, "
    "pride, demands or worries unrelated to children leaving school. When unsure, KEEP.\n"
    'Respond with JSON: {"delete": [int, ...]}'
)


def sentences(text: str) -> list[list[str]]:
    return [_SENT.split(p.strip()) for p in re.split(r"\n{2,}", text) if p.strip()]


async def neutralize(llm, text: str) -> tuple[str, list[str]]:
    paras = sentences(text)
    flat = [s for p in paras for s in p]
    numbered = "\n".join(f"{i}. {s}" for i, s in enumerate(flat))
    data = await llm._chat_json(SYSTEM, numbered, timeout=120.0)
    drop = {int(i) for i in data.get("delete") or [] if isinstance(i, int) and 0 <= i < len(flat)}
    out, removed, i = [], [], 0
    for p in paras:
        kept = []
        for s in p:
            (removed if i in drop else kept).append(s)
            i += 1
        if kept:
            out.append(" ".join(kept))
    return "\n\n".join(out), removed


VOTE = re.compile(r"\bvot(?:ed|es|ing)\b[^.]{0,60}\b(?:Congress|BJP|JD\s?\(?S\)?|JDS|party|candidate)\b|"
                  r"\b(?:Congress|BJP|JD\s?\(?S\)?)\b[^.]{0,40}\bvot", re.I)


async def neutralize_generated(args) -> None:
    from app.persona_library import GENERATED_DIR, build_card

    llm = get_llm_client(get_settings(), args.provider)
    sem = asyncio.Semaphore(4)
    report: dict[str, list[str]] = {}

    async def one(path: str) -> None:
        with open(path, encoding="utf-8") as fh:
            rec = json.load(fh)
        changed = False
        for t in rec["topics"]:
            text = t.get("profile") or ""
            paras = sentences(text)
            removed = [x for p in paras for x in p if VOTE.search(x)]
            if t["key"] in ALWAYS or DROPOUT.search(text):
                if t["key"] in ALWAYS:
                    async with sem:
                        try:
                            _, dropped = await neutralize(llm, text)
                        except Exception as exc:  # noqa: BLE001
                            print(f"  ! {rec['id']} {t['key']}: {exc}")
                            dropped = []
                    removed += [x for x in dropped if x not in removed]
                removed += [x for p in paras for x in p if DROPOUT.search(x) and x not in removed]
            if removed:
                t["profile"] = "\n\n".join(" ".join(x for x in p if x not in removed) for p in paras
                                            if any(x not in removed for x in p))
                report[f"{rec['id']} / {t['key']}"] = removed
                changed = True
        if changed:
            async with sem:
                rec["card"] = await build_card(llm, rec)
            if not args.dry_run:
                with open(path, "w", encoding="utf-8") as fh:
                    json.dump(rec, fh, ensure_ascii=False, indent=2)
                    fh.write("\n")
            print(f"  {rec['id']}: {sum(len(v) for k, v in report.items() if k.startswith(rec['id']))} sentences dropped, card rebuilt", flush=True)

    await asyncio.gather(*(one(f) for f in sorted(glob.glob(os.path.join(GENERATED_DIR, "*.json")))))
    out = os.path.join(ROOT, "docs", "persona-research", "neutralized-deletions-generated.md")
    lines = ["# Sentences removed from the generated district personas", "",
             "scripts/neutralize_personas.py --generated: dropout framing and statements of whom someone voted for. "
             "Everything else is verbatim.", ""]
    for key in sorted(report):
        lines += [f"## {key}", "", *[f"- {x}" for x in report[key]], ""]
    if not args.dry_run:
        with open(out, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
    print("deletions listed in", os.path.relpath(out, ROOT))


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--provider", default="azure_anthropic")
    ap.add_argument("--generated", action="store_true",
                    help="the persona library's generated personas instead of the 12 curated ones (also drops "
                         "sentences stating whom someone voted for, and rebuilds the edited personas' cards)")
    args = ap.parse_args()
    if args.generated:
        return await neutralize_generated(args)
    llm = get_llm_client(get_settings(), args.provider)
    sem = asyncio.Semaphore(4)
    report: dict[str, list[str]] = {}

    async def one(path: str) -> None:
        with open(path, encoding="utf-8") as fh:
            persona = json.load(fh)
        name = os.path.basename(path)[:-5]

        async def topic(key: str, t: dict) -> None:
            if key in TOPIC_DEFS:
                t["definition"] = TOPIC_DEFS[key]
            text = t.get("regional_profile") or ""
            if not (key in ALWAYS or DROPOUT.search(text)):
                return
            if key not in ALWAYS:
                # Outside education/worldview, drop only sentences that literally name dropout or
                # leaving school -- deterministic, so unrelated family/work detail is never touched.
                paras = sentences(text)
                removed = [x for p in paras for x in p if DROPOUT.search(x)]
                new = "\n\n".join(" ".join(x for x in p if not DROPOUT.search(x)) for p in paras if any(not DROPOUT.search(x) for x in p))
                t["regional_profile"] = new
                report[f"{name} / {key}"] = removed
                print(f"  {name} {key}: {len(removed)} sentences dropped (literal match)", flush=True)
                return
            async with sem:
                try:
                    new, removed = await neutralize(llm, text)
                except Exception as exc:  # noqa: BLE001 -- leave this topic as it is
                    print(f"  ! {name} {key} unchanged: {exc}")
                    return
            t["regional_profile"] = new
            report[f"{name} / {key}"] = removed
            left = len(DROPOUT.findall(new))
            print(f"  {name} {key}: {len(text.split())} -> {len(new.split())} words, {len(removed)} sentences dropped"
                  f"{f'  (still {left} dropout-word mentions)' if left else ''}", flush=True)

        await asyncio.gather(*(topic(k, t) for k, t in persona["topics"].items()))
        if not args.dry_run:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(persona, fh, ensure_ascii=False, indent=2)
                fh.write("\n")

    files = sorted(glob.glob(os.path.join(PERSONA_DIR, "*_male.json")) + glob.glob(os.path.join(PERSONA_DIR, "*_female.json")))
    await asyncio.gather(*(one(f) for f in files))

    lines = ["# Sentences removed from the curated personas", "",
             "Written by scripts/neutralize_personas.py. Each persona topic lost only these sentences; "
             "everything else is verbatim. Restore any sentence by editing backend/app/data/personas/.", ""]
    for key in sorted(report):
        if report[key]:
            lines += [f"## {key}", "", *[f"- {s}" for s in report[key]], ""]
    if not args.dry_run:
        with open(REPORT, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
        print("deletions listed in", os.path.relpath(REPORT, ROOT))


if __name__ == "__main__":
    asyncio.run(main())
