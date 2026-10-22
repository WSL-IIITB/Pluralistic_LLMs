"""
Builds the deep-research prompt for the districts with the thinnest source coverage (see source-library/COVERAGE.md).

    python3 build_thin_prompt.py        # reads public/data/*.json -- no backend needed

One prompt covering 8 districts, written for ChatGPT and for Gemini Deep Research (same content, so both can be run
and cross-checked). It reuses the original district-research output format, so answers go through the same
ingest_responses.py / build_converted.py verification. Each district block lists the sources the dashboard already
holds, so the researcher must find NEW ones.
"""

from __future__ import annotations

import json
import os
import re

import build_prompts as bp

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
DATA = os.path.join(ROOT, "public", "data")

THIN = ["29-564", "29-559", "29-566", "29-567", "29-571", "29-574", "29-582", "29-584"]  # Haveri, Raichur, Chitradurga, Davanagere, Tumakuru, Hassan, Chikkaballapur, Ramanagara

EXTRA_FOCUS = """## 2b. Extra priorities for this round (these districts are thinly sourced)
Our earlier pass found mostly the same handful of English-language newspaper stories. This round is about **new, district-specific, checkable sources**:
1. **Official local documents:** district Samagra Shiksha / DDPI / BEO statements and press releases, Zilla Panchayat and Deputy Commissioner orders, "out-of-school children" and "Shaale Kade Nanna Nade" / re-enrolment drive results, KSEAB and DSERT district or taluk results analyses, district statistical handbooks, High Court suo motu out-of-school case filings that name the district, Legislative Assembly/Council answers that give district figures.
2. **Kannada-language local media** (Prajavani, Vijay Karnataka, Vijayavani, Kannada Prabha, Samyukta Karnataka, Udayavani, Public TV, TV9 Kannada, district editions of The Hindu / Deccan Herald / Times of India / New Indian Express): read them and paraphrase in English. Search with Kannada district and taluk names.
3. **Academic and NGO work on the district or its taluks:** theses, journal articles, university working papers, CRY / Pratham ASER / Azim Premji / Child Rights Trust / KHPT / Mythri / Bachpan Bachao Andolan field reports.
4. **Numbers with years:** district out-of-school counts (2018-19 survey, 2021-22 household survey, 2024-25 or 2025-26 drives), dropout counts, SSLC pass % and rank for 2024 / 2025 / 2026, school closures and zero-enrolment schools, teacher vacancies, hostel and KGBV seat gaps, migration-linked absence.
5. **Do NOT re-report** any URL listed under "Already held sources" for a district. You may cite them only if you add something they do not say. Spend your effort on sources we do not have.
"""

EXTRA_RULES = """- **Child marriage and other single events:** a reason about child marriage, child labour, trafficking or violence is a *dropout* reason only if a cited page says (or clearly shows) that it led children, especially girls, to leave school. A count of marriages stopped, a single POCSO case or one rescue is context, not evidence of a district pattern: put it in `keyFacts` with its number, and mark any reason resting on one case or one article as `thin`. Never rate a reason `strong` unless at least two independent sources about this district support it.
- **Separate what the page says from what you infer.** If a page gives a statistic but not the link to dropout, say so in `detail` ("count only; link to leaving school not stated").
- Prefer a smaller number of well-supported reasons over a long list. If you find nothing new for a district, say so in `gaps` rather than padding with statewide material.
"""

NOTE_OVERRIDE = {
    "chatgpt": bp.PLATFORM_NOTES["chatgpt"],
    "gemini": bp.PLATFORM_NOTES["gemini"],
}


def held_sources(res: dict, did: str) -> str:
    srcs = res[did]["sources"]
    lines = [f"- {s['outlet']} {s['date']}: {s['url']}" for s in srcs]
    return "- Already held sources (do not just repeat these; find NEW ones):\n  " + "\n  ".join(l[2:] for l in lines) if lines else "- Already held sources: none"


def main() -> None:
    profiles = {d["districtId"]: d for d in json.load(open(os.path.join(DATA, "districts.json"), encoding="utf-8"))["districts"]}
    res = json.load(open(os.path.join(DATA, "districts-research.json"), encoding="utf-8"))
    region_of = {}
    for region in bp.REGIONS:
        for did in region["district_ids"]:
            region_of[did] = region["id"]
    blocks = []
    for did in THIN:
        b = bp.district_block(did, profiles[did], region_of[did])
        blocks.append(b + "\n" + held_sources(res, did))
    base = bp.TEMPLATE
    # tailor the original template to this round
    base = base.replace("# TASK: District-by-district research on secondary-school dropout in Karnataka ({n} districts)",
                        "# TASK: Fill the source gaps -- secondary-school dropout in {n} thinly covered Karnataka districts")
    base = base.replace("## 3. About the UIDAI / NITI", EXTRA_FOCUS + "\n## 3. About the UIDAI / NITI", 1)
    base = base.replace("## 5. Hard rules -- accuracy over volume\n", "## 5. Hard rules -- accuracy over volume\n" + EXTRA_RULES, 1)
    base = base.replace("Counts per district: reasons 4-6, keyFacts 4-8, headlines 5-10 (newest first; district-specific news only), responses 0-4, sources up to ~15.",
                        "Counts per district: reasons 3-6, keyFacts 4-8, headlines 5-12 (newest first; district-specific only, and not already held), responses 0-4, sources up to ~20. Quality over count: fewer sources are fine if every one is new, real and district-specific.")
    os.makedirs(os.path.join(HERE, "prompts"), exist_ok=True)
    for kind in ("chatgpt", "gemini"):
        text = base.format(n=len(THIN), platform_note=NOTE_OVERRIDE[kind], district_blocks="\n\n".join(blocks))
        path = os.path.join(HERE, "prompts", f"thin-districts-{kind}-deep-research.md")
        open(path, "w", encoding="utf-8").write(text)
        print(f"{path}: {len(text.split())} words")
    print("districts:", ", ".join(bp.NAMES[d] for d in THIN))


if __name__ == "__main__":
    main()
