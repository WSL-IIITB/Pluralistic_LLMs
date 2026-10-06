"""
Builds the two deep-research prompts (ChatGPT / Gemini) for the district round.

    python3 build_prompts.py        # needs the backend running on :8001 for the district context

Split (15 districts each, by region):
  ChatGPT Deep Research -> Old Mysuru (6) + Bayaluseeme (5) + Malnad (4)
  Gemini Deep Research  -> Karavali (3) + Kitturu Karnataka (6) + Kalyana Karnataka (6)

Each district's block is filled from live project data: its casefile dropout rate,
its UIDAI/NITI dominant-factor rows (both methods), its sub-areas, and how much
media research we already hold for it.
"""

from __future__ import annotations

import json
import os
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
RESEARCH_DIR = os.path.join(ROOT, "backend", "app", "data", "district_research")
REGIONS = json.load(open(os.path.join(ROOT, "backend", "app", "data", "karnataka_regions.json")))["regions"]

NAMES = {
    "29-555": "Belagavi", "29-556": "Bagalkote", "29-557": "Vijayapura", "29-558": "Bidar",
    "29-559": "Raichur", "29-560": "Koppal", "29-561": "Gadag", "29-562": "Dharwad",
    "29-563": "Uttara Kannada", "29-564": "Haveri", "29-565": "Ballari (and Vijayanagara)", "29-566": "Chitradurga",
    "29-567": "Davanagere", "29-568": "Shivamogga", "29-569": "Udupi", "29-570": "Chikkamagaluru",
    "29-571": "Tumakuru", "29-572": "Bengaluru Urban", "29-573": "Mandya", "29-574": "Hassan",
    "29-575": "Dakshina Kannada", "29-576": "Kodagu", "29-577": "Mysuru", "29-578": "Chamarajanagara",
    "29-579": "Kalaburagi", "29-580": "Yadgir", "29-581": "Kolar", "29-582": "Chikkaballapur",
    "29-583": "Bengaluru Rural", "29-584": "Ramanagara",
}

SPLITS = {
    "chatgpt": {"regions": ["old-mysuru", "bayaluseeme", "malnad"], "title": "ChatGPT Deep Research"},
    "gemini": {"regions": ["karavali", "kitturu-karnataka", "kalyana-karnataka"], "title": "Gemini Deep Research"},
}

PLATFORM_NOTES = {
    "chatgpt": """You are running as ChatGPT Deep Research. I have pre-answered every clarifying question below -- do NOT ask me
questions and do NOT propose a plan for approval; start researching immediately.""",
    "gemini": """You are running as Gemini Deep Research. Do NOT ask me to confirm or edit the research plan -- treat the plan as
approved and start researching immediately. Put the complete deliverable in the final report text itself (not in a
linked document, canvas or table-only summary).""",
}

TEMPLATE = """# TASK: District-by-district research on secondary-school dropout in Karnataka ({n} districts)

{platform_note}

## 1. Pre-answered clarifications
- Topic (fixed): **why students leave, or stop attending, secondary school -- Classes 8-10 / SSLC -- in each named district of Karnataka**, India. Also relevant: out-of-school and irregular-attendance children of that age, SSLC (Class 10) failure and exam-linked exits, and the transition from Class 8 to 9.
- Geography: ONLY the {n} districts listed in section 4. Treat each district separately. Do not substitute state-level or neighbouring-district evidence for a district; if you can only find state-level material, say so in `gaps` and mark coverage "thin".
- Time window: prioritise 2022-2026 reporting and data; use older material (2015-2021) only when it is the best district-specific evidence available, and say which year it is from.
- Languages: search in English AND Kannada (e.g. Prajavani, Vijay Karnataka, Vijayavani, Udayavani, Kannada Prabha, Samyukta Karnataka, Public TV, TV9 Kannada, Daijiworld, local district editions of The Hindu / Deccan Herald / Times of India). Kannada-language articles are valuable for the thinly covered districts -- read them and paraphrase in English.
- Source types wanted, in this priority: (1) district-specific news and investigations, (2) government / official data (Samagra Shiksha Karnataka, DSERT, KSEAB SSLC results, DDPI/BEO statements, UDISE+, District Statistical Handbooks, Karnataka State Commission for Protection of Child Rights, Labour Dept child-labour drives, Zilla Panchayat/DC orders and "out-of-school children survey" results), (3) NGO / research reports (Pratham ASER, CRY, Azim Premji Foundation, Child Rights Trust, KHPT, Mythri, Bachpan Bachao Andolan, UNICEF/UNESCO case studies, peer-reviewed papers).
- Output language: English. Output format: exactly as specified in section 6.

## 2. What to find, for EVERY district
1. The specific reasons students leave secondary school there, as documented: poverty and seasonal/labour migration (sugarcane cutting, tobacco/cotton/chilli/brick-kiln/construction work, plantation/estate work, fishing/harbour work, mining belt), child labour, child marriage and girls leaving after puberty, school distance / closed or merged schools / zero-enrolment schools, teacher vacancies, toilets and other infrastructure, language-of-instruction issues, SSLC failure and "slow learner" exits, safety of girls, post-COVID drop, Lambani/tanda and other community-specific access gaps, Devadasi-linked practices, disability, health.
2. Hard numbers with the year: out-of-school counts from the state's annual survey, dropout counts/rates, SSLC pass % and state rank (2024, 2025, 2026 if available), number of schools closed/merged, child marriages stopped, children rescued from labour, teacher-vacancy counts, enrolment/GER.
3. Recent district-specific news items (aim for 5-10 per district) with real, openable URLs.
4. What local authorities and NGOs are actually doing (tracking drives, bridge courses, residential schools, cash transfers, bicycle/bus schemes).
5. **Check the official UIDAI/NITI factors** supplied for each district in section 4 (see section 3): for each factor row, does local evidence support it, contradict it, or is there no evidence either way?

## 3. About the UIDAI / NITI Aayog "dominant factor" rows
For each district I am giving you rows from two official-statistics files that name the factor statistically most associated with that district's secondary-school dropout rate:
- `method: state` -- the SAME factor is the top-ranked factor for the whole state (here: sanitation), paired with this district's own figure for it.
- `method: district` -- a factor selected individually for the district (e.g. share of schools with English as medium of instruction, schools with a protected well).
Do NOT try to reinterpret the numeric values (I could not verify what the numbers measure) and do not present them as findings. Your job is only to test, using real-world evidence from the district, whether each named factor plausibly matters locally. Report one `officialFactorCheck` entry per supplied row with a verdict of `supports`, `contradicts`, `unclear` or `no-evidence`, a one-sentence note, and the source numbers behind it. A verdict of `no-evidence` is a perfectly good answer.
Where a district has sub-area rows (e.g. "Belagavi Chikkodi"), the sub-area is part of the same district: include it in that district's research and name it in the factor note.

## 4. The {n} districts (project data -- treat as background, never cite it as a source)
{district_blocks}

## 5. Hard rules -- accuracy over volume
- Every claim, number, date and headline must be backed by a page you actually opened. NEVER invent or guess a URL, outlet, date, headline, quote or figure. Do not reconstruct a URL from memory.
- Every `url` must be the canonical, directly openable article/report URL on the publisher's own domain. Never output search-engine, news-aggregator or redirect links (e.g. google.com/url, vertexaisearch.cloud.google.com/grounding-api-redirect, news.google.com/rss, bing.com). If you cannot resolve a source to its real URL, drop that source.
- Be district-specific. A national or statewide statistic may appear only as context in `gaps` or a clearly labelled key fact; never as evidence for a district.
- If two sources disagree (e.g. different SSLC pass rates), report the one from the more authoritative source and note the conflict in `gaps`.
- Paraphrase. Quote at most 12 consecutive words from any source. No markdown formatting inside JSON string values.
- Dates as the source shows them: YYYY-MM-DD, or YYYY-MM, or YYYY; use "" only if truly unknown.
- Be honest about thin coverage: `coverage` is "rich" (several recent district-specific sources with numbers), "moderate", or "thin". Do not pad. Put what you looked for but could not find in `gaps`.
- "Existing coverage" in section 4 tells you what a previous, shallow pass already found. Go beyond it: new sources, newer data, Kannada-language sources, official documents.

## 6. Output format -- follow exactly (I will parse it by machine)
Output ONLY the district blocks below, one per district, in the order of section 4, with no introduction, no summary table, no commentary between blocks and no markdown code fences. Each block is a sentinel line, one valid JSON object, and a closing sentinel line:

=== DISTRICT <districtId> | <District name> | BEGIN ===
{{ ...JSON object... }}
=== DISTRICT <districtId> | <District name> | END ===

The JSON object for each district:
{{
  "districtId": "29-577",
  "name": "Mysuru",
  "regionId": "old-mysuru",
  "researchedOn": "<today, YYYY-MM-DD>",
  "headline": "<= 25 words: the single best-evidenced takeaway for THIS district",
  "summary": "70-110 words synthesising why students leave or stop attending secondary school here, and how strong the evidence is",
  "reasons": [
    {{ "factor": "<= 6 words", "category": "economic | migration | school-infrastructure | social-norms | gender | health | governance | other",
      "detail": "<= 40 words, specific to this district, paraphrased", "sources": [1, 3], "evidence": "strong | moderate | thin" }}
  ],
  "keyFacts": [ {{ "label": "<= 8 words incl. the year", "value": "figure exactly as the source states it", "sources": [2] }} ],
  "headlines": [ {{ "title": "article title", "outlet": "The Hindu", "date": "2025-06-12", "url": "https://...", "takeaway": "<= 25 words" }} ],
  "responses": [ {{ "text": "<= 30 words: a local programme or official action", "sources": [4] }} ],
  "officialFactorCheck": [
    {{ "factor": "factor name exactly as supplied in section 4", "method": "state | district", "verdict": "supports | contradicts | unclear | no-evidence",
      "note": "<= 35 words", "sources": [2] }}
  ],
  "sources": [
    {{ "id": 1, "url": "https://...", "title": "...", "outlet": "...", "date": "2025-06-12", "type": "news | government | ngo | research | data" }}
  ],
  "coverage": "rich | moderate | thin",
  "gaps": "<= 50 words: what you looked for but could not find or verify"
}}

Counts per district: reasons 4-6, keyFacts 4-8, headlines 5-10 (newest first; district-specific news only), responses 0-4, sources up to ~15. `sources[].id` are 1-based; every number in a `sources` array must exist; every `headlines[].url` must also appear in `sources`. Use `regionId` exactly as given in section 4.

If you reach an output-length limit mid-way, stop cleanly after a completed END line and I will reply "continue" -- then resume with the next district, repeating nothing.
"""


def load_context() -> dict[str, dict]:
    with urllib.request.urlopen("http://localhost:8001/api/karnataka/districts", timeout=30) as r:
        return {d["districtId"]: d for d in json.load(r)["districts"]}


def existing_coverage(district_id: str) -> str:
    path = os.path.join(RESEARCH_DIR, f"{district_id}.json")
    if not os.path.isfile(path):
        return "none yet"
    d = json.load(open(path, encoding="utf-8"))
    return f"{d['coverage']} ({len(d['sources'])} sources, {len(d['headlines'])} news items)"


def district_block(did: str, ctx: dict, region_id: str) -> str:
    name = NAMES[did]
    lines = [f"### {did} | {name} | regionId \"{region_id}\""]
    rate = ctx["dropoutRate"]
    lines.append(f"- Casefile secondary dropout rate (LKI-SSM): {rate}%" if rate is not None else "- Casefile dropout rate: reported only for sub-areas (below)")
    for s in ctx["subAreas"]:
        lines.append(f"- Sub-area in the data files: {s['name']} -- dropout {s['dropoutRate']}%")
    for method in ("state", "district"):
        rows = [f for f in ctx["nitiFactors"] if f["method"] == method]
        for f in rows:
            lines.append(f"- UIDAI/NITI row [method: {method}] area \"{f['area']}\": factor \"{f['factor']}\" (value {f['value']})")
    lines.append(f"- Existing coverage from a previous shallow pass: {existing_coverage(did)}")
    return "\n".join(lines)


def build(kind: str, ctx: dict[str, dict]) -> str:
    cfg = SPLITS[kind]
    blocks, count = [], 0
    for region in REGIONS:
        if region["id"] not in cfg["regions"]:
            continue
        for did in region["district_ids"]:
            blocks.append(district_block(did, ctx[did], region["id"]))
            count += 1
    return TEMPLATE.format(
        n=count,
        platform_note=PLATFORM_NOTES[kind],
        district_blocks="\n\n".join(blocks),
    )


def main() -> None:
    ctx = load_context()
    os.makedirs(os.path.join(HERE, "prompts"), exist_ok=True)
    for kind in SPLITS:
        text = build(kind, ctx)
        path = os.path.join(HERE, "prompts", f"{kind}-deep-research.md")
        open(path, "w", encoding="utf-8").write(text)
        print(f"{path}: {len(text.split())} words")


if __name__ == "__main__":
    main()
