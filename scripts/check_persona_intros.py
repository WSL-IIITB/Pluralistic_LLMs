"""
Check the persona intro scripts (`intro` in src/lib/worldview/personaCards/*.json) against their own cards.

    python3 scripts/check_persona_intros.py      # exit 1 on any failure; warnings are printed but do not fail

Each persona introduces itself in a short animated "video" (src/components/persona/PersonaIntro.tsx) whose narration
is a first-person script written from the card. The script may only say what the card says, so this checks:
  * scenes run in the fixed order and every `show` / `topic` reference points at something on the card;
  * each line is short enough to read as a caption, and the whole script is about a minute long;
  * every number in a line's caption or spoken text appears somewhere else on the card (spelled-out numbers in the
    spoken text are not checked; the caption carries the digits);
  * capitalised words that never occur on the card are reported as warnings (a likely invented name or place).
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CARDS = os.path.join(ROOT, "src", "lib", "worldview", "personaCards")
ORDER = ["hello", "household", "day", "world", "school", "district", "worries", "outro"]
BACKDROPS = {"fields", "city", "dry-plains", "coast", "hills-forest"}
MAX_LINE_WORDS = 25
TOTAL_WORDS = (130, 215)
# words that may appear in any script without being on the card
ALLOWED = {"Hello", "I", "I'm", "My", "Our", "We", "The", "That's", "In", "For", "And", "At", "When", "Between", "Before",
           "Then", "From", "Every", "Since", "After", "Village", "Mornings", "Cooking", "Only", "Six", "What", "Yellow",
           "Explore", "Pre-university", "There", "NITI", "Garment", "Once", "Rs", "A", "It", "One", "Class", "Census",
           "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November",
           "December"}


def words(s: str) -> int:
    return len(s.split())


def numbers(s: str) -> list[str]:
    return re.findall(r"\d+(?:\.\d+)?", s.replace(",", ""))


def check(rid: str, pid: str, card: dict) -> tuple[list[str], list[str]]:
    errs: list[str] = []
    warns: list[str] = []
    intro = card.get("intro")
    if not intro:
        return [f"{rid}/{pid}: no intro"], []
    rest = {k: v for k, v in card.items() if k != "intro"}
    flat = json.dumps(rest, ensure_ascii=False).replace(",", "")
    if intro.get("backdrop") not in BACKDROPS:
        errs.append(f"backdrop {intro.get('backdrop')!r} is not one of {sorted(BACKDROPS)}")
    lines = intro.get("lines", [])
    seen = [ln.get("scene") for ln in lines]
    if not seen or seen[0] != "hello" or seen[-1] != "outro":
        errs.append("script must start with 'hello' and end with 'outro'")
    pos = [ORDER.index(s) if s in ORDER else -1 for s in seen]
    if -1 in pos or pos != sorted(pos):
        errs.append(f"scenes out of order: {seen}")
    lists = {"household": card.get("household", []), "day": card.get("dayInLife", []),
             "school": card.get("schoolPressures", []), "worries": card.get("worries", [])}
    topics = {t["key"]: t for t in card.get("topics", [])}
    lens = card.get("dataLens")
    for i, ln in enumerate(lines):
        tag = f"line {i + 1} ({ln.get('scene')})"
        text = ln.get("text", "")
        if words(text) > MAX_LINE_WORDS:
            errs.append(f"{tag}: {words(text)} words (max {MAX_LINE_WORDS})")
        scene = ln.get("scene")
        for j in ln.get("show", []):
            if scene == "district":
                if not lens or not 0 <= j <= len(lens["changes"]):
                    errs.append(f"{tag}: show index {j} has no dataLens change")
            elif scene not in lists or not 0 <= j < len(lists[scene]):
                errs.append(f"{tag}: show index {j} is not on the card")
        if "topic" in ln and not (topics.get(ln["topic"]) or {}).get("stat"):
            errs.append(f"{tag}: topic {ln['topic']!r} has no stat on the card")
        for n in sorted(set(numbers(text) + numbers(ln.get("say", "")))):
            if not re.search(rf"(?<!\d){re.escape(n)}(?!\d)", flat):
                errs.append(f"{tag}: number {n} is not on the card")
        for w in re.findall(r"\b[A-Z][\w'-]+", text):
            w = re.sub(r"'s$", "", w)
            if w not in ALLOWED and w.lower() not in flat.lower():
                warns.append(f"{tag}: '{w}' does not occur on the card")
    if lens and "district" not in seen:
        errs.append("card has a dataLens but the script has no 'district' scene")
    total = sum(words(ln.get("text", "")) for ln in lines)
    if not TOTAL_WORDS[0] <= total <= TOTAL_WORDS[1]:
        errs.append(f"script is {total} words (want {TOTAL_WORDS[0]}-{TOTAL_WORDS[1]})")
    return errs, warns


def main() -> int:
    failed = 0
    for path in sorted(glob.glob(os.path.join(CARDS, "*.json"))):
        rid = os.path.basename(path)[:-5]
        for pid, card in json.load(open(path, encoding="utf-8")).items():
            errs, warns = check(rid, pid, card)
            total = sum(words(ln.get("text", "")) for ln in card.get("intro", {}).get("lines", []))
            print(f"{'FAIL' if errs else 'ok  '}  {rid}/{pid}: {len(card.get('intro', {}).get('lines', []))} lines, {total} words")
            for e in errs:
                print(f"        x {e}")
            for w in warns:
                print(f"        ! {w}")
            failed += bool(errs)
    print(f"\n{failed} script(s) failed" if failed else "\nall scripts pass")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
