"""Assemble the ready-to-paste Deep Research prompts (two passes per region).

    python3 build_prompts.py                          # 6 regions x 2 passes -> prompts/
    python3 build_prompts.py --rerun <slug> k1,k2     # repair run for missing/bad topics

Inputs : region_mapping.json, _core_template.md, _topics.md, briefs/<slug>.md
Outputs: prompts/<file_no>-<slug>-pass1.md  (Part A: the 8 core topics + Annex A)
         prompts/<file_no>-<slug>-pass2.md  (Part B: the 10 depth topics + Annex D)

Everything shared lives in _core_template.md and _topics.md, so editing either
and re-running keeps all twelve prompts consistent. Only the region name,
district list, peer regions and the (topic-filtered) region brief differ.
"""

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
AS_OF = "September 2026"

PASS_SCOPES = {
    1: (
        "PASS 1 of 2",
        "REPORT SECTION 0, REPORT SECTION 1, the 8 Part A topics ({keys}), Annex A, and Annex E covering only these topics",
    ),
    2: (
        "PASS 2 of 2",
        "REPORT SECTION 0, the 10 Part B topics ({keys}), Annex D, and Annex E covering only these topics",
    ),
}

SECTION1_SPEC = (
    "REPORT SECTION 1: one paragraph of 200-250 words, plain text, with no citation markers and no brackets. "
    "It starts with the region name ({region}), names all {n} districts, describes the geography and defining "
    "character, explains why the districts are treated as one region, and ends with one sentence per internal "
    "sub-region naming its districts or taluks and its defining difference. It is shown to end users as the "
    "region description, so it must stand alone.\n"
)

ANNEX_E = (
    "Annex E, Gaps and uncertainties (200-400 words, one item per line, covering only the topics in RUN SCOPE): "
    "every gap, unverifiable claim, source conflict, missing district-level figure and short source list, each "
    "starting with one of these labels: UNVERIFIED [topic_key], CONFLICT [topic_key], GAP [topic_key], "
    "SOURCES SHORT [topic_key], BOUNDARY, VINTAGE."
)
ANNEX_A = (
    "Annex A, District indicator tables: three markdown tables (the only tables in the report), one row per "
    "district of mine in my order, district name in column 1, at most 8 further columns each. A1 demography "
    "(Census 2011): population, decadal growth, urban %, sex ratio, SC %, ST %, Muslim %, Christian %. A2 "
    "education, health and income: literacy total and female (2011), secondary-level dropout rate (UDISE+, "
    "latest year), SSLC pass % and rank (latest year), women married before 18 (NFHS-5), stunting (NFHS-5), "
    "institutional births (NFHS-5), per-capita income (year). A3 agriculture: main crops, irrigated area share "
    "(year). Write each cell as value (year) [topic_key:S#], where [topic_key:S#] points to a source line in that "
    "topic's Sources. Write n/a when no district-level figure is published; NEVER estimate. Under each table one "
    "line flags any undivided-district figure."
)
ANNEX_D = (
    "Annex D, Glossary of local terms: 40-50 entries, one per line, in the form: term | script (key terms only) "
    "| language | English gloss | domain (kinship, farming, housing, governance, school, food, other)."
)


def parse_topics(text: str) -> dict:
    """Parse _topics.md into {key: {label, definition, target, must, priority, part}}."""
    topics: dict[str, dict] = {}
    part = None
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("### PART A"):
            part = "A"
        elif line.startswith("### PART B"):
            part = "B"
        m = re.match(r"^\*\*(\w+) / (.+)\*\*$", line)
        if m:
            key, label = m.groups()
            block = {"label": label, "part": part}
            i += 1
            while i < len(lines) and lines[i].strip():
                field, _, value = lines[i].partition(": ")
                block[field] = value
                i += 1
            topics[key] = {
                "label": label,
                "part": part,
                "definition": block["Definition"],
                "target": block["Word target"],
                "must": block["Must cover"],
                "priority": block["Priority (P)"],
            }
            continue
        i += 1
    return topics


def topic_blocks(topics: dict, keys: list[str]) -> str:
    out, last_part = [], None
    for key in keys:
        t = topics[key]
        if t["part"] != last_part:
            out.append("### PART A: core topics" if t["part"] == "A" else "### PART B: depth topics")
            out.append("")
            last_part = t["part"]
        out += [
            f"**{key} / {t['label']}**",
            f"Definition: {t['definition']}",
            f"Word target: {t['target']}",
            f"Must cover: {t['must']}",
            f"Priority (P): {t['priority']}",
            "",
        ]
    return "\n".join(out).rstrip()


def skeleton(topics: dict, keys: list[str], run_label: str, with_section1: bool, annexes: list[str]) -> str:
    lines = [
        "BEGIN REPORT",
        "# SECTION 0: ASSUMPTIONS, BOUNDARY NOTES AND DATA VINTAGES",
        "- <short bullets>",
    ]
    if with_section1:
        lines += ["# SECTION 1: REGION DEFINITION", "<one paragraph, 200-250 words, no [S#] markers>"]
    lines.append("# SECTION 2: TOPICS")
    for n, key in enumerate(keys):
        lines.append(f"## TOPIC: {key} | {topics[key]['label']}")
        if n == 0:
            lines += [
                "### Profile",
                "<plain prose paragraphs with markers such as [S1]>",
                "### Sources",
                "- [S1] Example Title | Example Publisher | 2023 | https://example.org/page",
            ]
    lines.append("# SECTION 3: ANNEXES")
    lines += annexes
    lines.append(f"END OF REPORT | {run_label} | TOPICS DELIVERED: <keys>")
    return "\n".join(lines)


def filter_brief(brief: str, keys: list[str]) -> tuple[str, list[str]]:
    """Rename 3.x -> D.x and keep only the D.3 items whose topic key is in this run."""
    brief = re.sub(r"^###\s+3\.(\d)", r"### D.\1", brief.strip(), flags=re.M)
    m = re.search(r"^### D\.3.*?$", brief, flags=re.M)
    if not m:
        return brief, ["no D.3 section"]
    nxt = re.search(r"^### D\.4", brief[m.end():], flags=re.M)
    start, end = m.end(), (m.end() + nxt.start()) if nxt else len(brief)
    body = brief[start:end]
    marks = list(re.finditer(r"\*\*([a-z_]+):\*\*", body))
    if not marks:
        return brief, ["D.3 has no bold topic keys"]
    kept = [body[: marks[0].start()]]
    seen = []
    for i, mk in enumerate(marks):
        seg = body[mk.start(): marks[i + 1].start() if i + 1 < len(marks) else len(body)]
        seen.append(mk.group(1))
        if mk.group(1) in keys:
            kept.append(seg.rstrip() + "\n\n")
    missing = [k for k in keys if k not in seen]
    return brief[:start] + "".join(kept).rstrip() + "\n\n" + brief[end:], (
        [f"D.3 lacks keys: {missing}"] if missing else []
    )


def fill(core: str, values: dict) -> str:
    for key, value in values.items():
        core = core.replace(key, value)
    return core


def build_one(region, regions, topics, core, keys, run_label, scope, with_s1, annexes, annex_spec, out) -> list[str]:
    problems: list[str] = []
    brief_path = HERE / "briefs" / f"{region['slug']}.md"
    if not brief_path.exists():
        return [f"missing brief: {brief_path.name}"]
    brief, brief_problems = filter_brief(brief_path.read_text(encoding="utf-8"), keys)
    problems += [f"{region['slug']}: {p}" for p in brief_problems]
    names = [d["name"] for d in region["districts"]]
    peers = "; ".join(
        f"{r['name']} ({', '.join(d['name'] for d in r['districts'])})" for r in regions if r["id"] != region["id"]
    )
    text = fill(
        core,
        {
            "{{TOPIC_BLOCKS}}": topic_blocks(topics, keys),
            "{{SKELETON}}": skeleton(topics, keys, run_label, with_s1, annexes),
            "{{SECTION1_SPEC}}": SECTION1_SPEC.format(region=region["name"], n=len(names)) if with_s1 else "",
            "{{ANNEX_SPEC}}": annex_spec,
            "{{REGION_BRIEF}}": brief,
        },
    )
    text = fill(
        text,
        {
            "{{RUN_LABEL}}": run_label,
            "{{PASS_SCOPE}}": scope,
            "{{REGION_NAME}}": region["name"],
            "{{DISTRICT_COUNT}}": str(len(names)),
            "{{DISTRICT_LIST}}": ", ".join(names),
            "{{PEER_REGIONS}}": peers,
            "{{AS_OF}}": AS_OF,
        },
    )
    left = sorted(set(re.findall(r"\{\{[A-Za-z0-9_]+\}\}", text)))
    if left:
        problems.append(f"{out.name}: unfilled placeholders {left}")
    n_topics = len(re.findall(r"^## TOPIC:", text, flags=re.M))
    if n_topics != len(keys):
        problems.append(f"{out.name}: {n_topics} skeleton topics, expected {len(keys)}")
    for name in names:
        if name not in text:
            problems.append(f"{out.name}: district {name} missing")
    out.write_text(text.rstrip() + "\n", encoding="utf-8")
    print(f"wrote {out.name}: {len(text.split()):,} words, {len(keys)} topics")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rerun", nargs=2, metavar=("SLUG", "KEYS"))
    ap.add_argument("--core", default="_core_template.md")
    args = ap.parse_args()

    mapping = json.loads((HERE / "region_mapping.json").read_text(encoding="utf-8"))
    core = (HERE / args.core).read_text(encoding="utf-8")
    topics = parse_topics((HERE / "_topics.md").read_text(encoding="utf-8"))
    regions = mapping["regions"]
    part_keys = {p: [k for k, t in topics.items() if t["part"] == p] for p in "AB"}
    (HERE / "prompts").mkdir(exist_ok=True)
    problems: list[str] = []

    if args.rerun:
        slug, keys_arg = args.rerun
        keys = [k.strip() for k in keys_arg.split(",") if k.strip()]
        unknown = [k for k in keys if k not in topics]
        if unknown:
            print(f"unknown topic keys: {unknown}", file=sys.stderr)
            return 2
        keys = [k for k in topics if k in keys]  # canonical order
        region = next(r for r in regions if r["slug"] == slug)
        scope = f"REPORT SECTION 0, ONLY these topics ({', '.join(keys)}), and Annex E covering only these topics"
        problems += build_one(
            region, regions, topics, core, keys, "REPAIR RUN", scope, False,
            ["## ANNEX E: GAPS AND UNCERTAINTIES"], ANNEX_E,
            HERE / "prompts" / f"repair-{slug}.md",
        )
    else:
        for region in regions:
            for n, part in ((1, "A"), (2, "B")):
                label, scope_t = PASS_SCOPES[n]
                keys = part_keys[part]
                scope = scope_t.format(keys=", ".join(keys))
                annex = ANNEX_A if n == 1 else ANNEX_D
                annexes = (
                    ["## ANNEX A: DISTRICT INDICATOR TABLES"] if n == 1 else ["## ANNEX D: GLOSSARY OF LOCAL TERMS"]
                ) + ["## ANNEX E: GAPS AND UNCERTAINTIES"]
                problems += build_one(
                    region, regions, topics, core, keys, label, scope, n == 1, annexes,
                    annex + "\n\n" + ANNEX_E,
                    HERE / "prompts" / f"{region['file_no']}-{region['slug']}-pass{n}.md",
                )
    for p in problems:
        print("PROBLEM:", p, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
