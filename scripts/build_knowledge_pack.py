"""
Build the hardcoded knowledge pack the dashboard's chat answers from.

    python3 scripts/build_knowledge_pack.py          # write public/data/knowledge-pack.json
    python3 scripts/build_knowledge_pack.py --check  # exit 1 if the pack is stale vs its inputs

The chat model is told to answer ONLY from this pack. It is built by deterministic extraction (no
LLM), so it cannot add errors: every line is a fact already in the research data, written as one
line ending in source ids like [S12][S40] and tagged with its scope:

    (DISTRICT)   a fact about that district      (REGIONAL) / (STATEWIDE)  NOT a district's own figure
    (SYNTHESIS)  model-written summary, not a sourced fact      (PERSONA)  composite, not a real person
    (REASONING)  general reasoning on how an indicator could be linked to dropout: possible reasons, not findings

Inputs : public/data/{districts-research,districts,default-run,news-vs-data}.json, src/lib/worldview/personaCards/*.json,
         backend/app/data/karnataka_regions.json
Output : public/data/knowledge-pack.json
         {version, builtAt, sourceHash, tokenEstimate, stats, sources[], index, caveats, digest,
          regions{}, districts{}, uidai, newsVsData, analysis, personas}

Sections the chat always sends: caveats + digest. Everything else is added by the router
(src/lib/worldview/knowledgeRouter.ts) only when the question mentions it, to fit Gemma's 32k window.
"""

from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA = os.path.join(ROOT, "public", "data")
OUT = os.path.join(DATA, "knowledge-pack.json")
sys.path.insert(0, os.path.join(ROOT, "docs", "district-research"))
from build_converted import ALIASES  # noqa: E402  (district-name spellings; one source of truth)

CATEGORY_LABEL = {
    "economic": "poverty & child labour",
    "migration": "migration",
    "school-infrastructure": "school infrastructure & staffing",
    "social-norms": "social norms & customs",
    "gender": "child marriage & girls' exits",
    "health": "health",
    "governance": "governance, tracking & exams",
    "other": "other",
}
EVIDENCE_ORDER = {"strong": 0, "moderate": 1, "thin": 2}
EVIDENCE_WEIGHT = {"strong": 3, "moderate": 2, "thin": 1}

CAVEATS = """\
These rules always apply when you answer.
1. SCOPE. This research covers why students leave or stop attending secondary school (Classes 8-10 and the SSLC exam) in Karnataka's 30 districts. It says nothing about other states, other education levels or other topics.
2. COVERAGE VARIES. Some districts are rated "thin", and even "moderate" districts often have no district-level dropout, out-of-school or SSLC figures. Many sources are old (2013-2019). Say "we found no evidence", never "it is not a factor".
3. SCOPE TAGS. A (DISTRICT) fact is about that district. A (REGIONAL) or (STATEWIDE) fact must NEVER be given as a district's own number. (SYNTHESIS) is a model-written summary, not a sourced fact. (PERSONA) is a composite character, not a real person. (REASONING) is general reasoning about how an indicator could be linked to dropout: give it as possible reasons, with no citation.
4. CASEFILE RATES. Each district has a dropout rate from the LKI-SSM casefile dataset. The very low rates for Udupi and Dakshina Kannada, and the high rate for Uttara Kannada, are not explained by any source we found. Vijayanagara is not covered separately from Ballari; sub-areas (Bengaluru North/South, Chikkodi, Madhugiri, Sirsi) are not separately covered.
5. UIDAI/NITI FACTORS. Two official files name a "dominant factor" per district. The state-level method gives the same factor (household sanitation) to every district and differs only in the value; the district-level method picks a factor per district. What the numeric "value" measures is UNVERIFIED: do not interpret values, compare them across districts, or blend the two methods. A dominant factor is a statistical flag, not a proven cause. When asked why a factor is dominant or how it relates to dropout, explain the possible links: the (REASONING) pathways in the UIDAI section, the district's "how it could work" line, and the district's documented reasons where they connect. The evidence-check results are there too, for when the user asks for proof.
6. SSLC. A pass rate is not a dropout rate. The 2025 and 2026 pass rates in the sources conflict and use different bases; never present them as a trend.
7. PERSONAS AND SYNTHESES. The 12 personas are composites built from public data. Persona replies and "consolidated answers" are model-written, not evidence.
8. Do not give policy advice or opinions beyond what the research states."""


# How each Karnataka factor could be linked to dropout. General reasoning about what the indicator measures
# (tagged REASONING), so the chat can explain a flag instead of only reporting that local sources were silent.
# No statistics, places or claims about districts here.
FACTOR_REASONING = [
    "HOW EACH KARNATAKA FACTOR COULD BE LINKED TO DROPOUT (REASONING: general reasoning about what each indicator measures; possible links, not findings of this study). "
    "The workbooks do not say whether more or less of an indicator goes with higher dropout, so a link can run either way.",
    "- Household sanitation (% population in households with improved sanitation), the state-level factor (REASONING): without a toilet at home, "
    "adolescent girls may have to go out in the open, which raises safety worries and can lead families to keep older girls at home; poor sanitation "
    "spreads diarrhoea and other infections, so children miss days and fall behind; girls need privacy and water for menstrual hygiene and may miss "
    "days each month without it; and low household sanitation also marks poorer, more remote households, where pressures such as work, early "
    "marriage and distance are stronger, so it can stand in for household deprivation as much as act directly.",
    "- English-medium schools (% schools with instruction medium English), the district-level factor in most districts (REASONING): a child who "
    "studied in Kannada or another home language can struggle when lessons, textbooks or exams lean on English, fail, and leave; where English-medium "
    "private schools are common, families who can afford them move children out of government schools, which then shrink or close, leaving poorer "
    "children with longer distances; English-medium private schooling usually means fees that strain poorer households; children of migrant "
    "families whose home language differs from the school's can feel shut out; and the share of English-medium schools also tracks how urban and "
    "how well-off an area is, so it may stand in for household means and access to schooling rather than language alone.",
    "- Schools with a functional protected well (% schools), the district-level factor for Bengaluru Urban and Mysuru (REASONING): it indicates "
    "whether a school has a safe, protected drinking-water source; without safe water children may fall ill from unsafe water or leave school "
    "grounds to drink, losing time; girls need water for toilets and menstrual hygiene and may stay home on some days without it; an open or "
    "unprotected well on school grounds is a safety hazard that can worry parents; and depending on wells rather than piped supply can mark "
    "under-served or fast-growing peri-urban schools with weaker facilities and crowded classrooms, so the factor may stand in for overall school "
    "conditions; seasonal water shortages can add to all of these.",
    "- Any other indicator (REASONING): reason the same way: what it measures at home or at school, and how that could stop a child attending, "
    "keeping up, or staying in school.",
]


def read(path: str):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def toks(text: str) -> int:
    return -(-len(text) // 4)  # conservative: ~4 characters per token


def input_files() -> list[str]:
    return sorted(
        [
            os.path.join(DATA, "districts-research.json"),
            os.path.join(DATA, "districts.json"),
            os.path.join(DATA, "default-run.json"),
            os.path.join(DATA, "news-vs-data.json"),
            os.path.join(ROOT, "backend", "app", "data", "karnataka_regions.json"),
            *glob.glob(os.path.join(ROOT, "src", "lib", "worldview", "personaCards", "*.json")),
            os.path.abspath(__file__),
        ]
    )


def source_hash() -> str:
    h = hashlib.sha256()
    for f in input_files():
        h.update(os.path.basename(f).encode())
        h.update(open(f, "rb").read())
    return h.hexdigest()[:16]


SSLC_NOTE = " (NOTE: SSLC pass rate/rank, not a dropout rate; never compare across years)"


def sslc(line: str) -> str:
    """Tag lines about SSLC pass rates/ranks so the model cannot read them as dropout or as a trend."""
    return line + SSLC_NOTE if re.search(r"SSLC", line) and re.search(r"pass|rank|result|topper", line, re.I) else line


def scope_tag(label: str) -> str:
    l = label.lower()
    if l.startswith("statewide"):
        return "(STATEWIDE)"
    if any(w in l for w in ("region", "division", "hyderabad-karnataka")):
        return "(REGIONAL)"
    return "(DISTRICT)"


def build() -> dict:
    research = read(os.path.join(DATA, "districts-research.json"))
    profiles = {d["districtId"]: d for d in read(os.path.join(DATA, "districts.json"))["districts"]}
    methods = read(os.path.join(DATA, "districts.json"))["methods"]
    run = read(os.path.join(DATA, "default-run.json"))
    regions = {r["id"]: r for r in read(os.path.join(ROOT, "backend", "app", "data", "karnataka_regions.json"))["regions"]}
    region_short = {rid: r["short_name"] for rid, r in regions.items()}

    # ---- global source ids (S1..) --------------------------------------------------------------
    sources: list[dict] = []
    gid_by_url: dict[str, str] = {}
    local_to_global: dict[str, dict[int, str]] = {}
    why_to_global: dict[str, dict[int, str]] = {}
    for did in sorted(research):
        local_to_global[did] = {}
        for s in research[did]["sources"]:
            if s["url"] not in gid_by_url:
                gid = f"S{len(sources) + 1}"
                gid_by_url[s["url"]] = gid
                sources.append({"id": gid, "title": s["title"][:150], "outlet": s["outlet"], "date": s["date"], "type": s["type"], "url": s["url"]})
            local_to_global[did][s["id"]] = gid_by_url[s["url"]]
        # the "why is this factor dominant" answer carries its own source list (ids local to that block)
        why_to_global[did] = {}
        for s in (research[did].get("dominantFactorWhy") or {}).get("sources", []):
            if s["url"] not in gid_by_url:
                gid = f"S{len(sources) + 1}"
                gid_by_url[s["url"]] = gid
                sources.append({"id": gid, "title": s["title"][:150], "outlet": s["outlet"], "date": s["date"], "type": s["type"], "url": s["url"]})
            why_to_global[did][s["id"]] = gid_by_url[s["url"]]

    def cites(did: str, ids: list[int]) -> str:
        return "".join(f"[{local_to_global[did][i]}]" for i in ids if i in local_to_global[did])

    # ---- aggregate stats -----------------------------------------------------------------------
    cat_districts: dict[str, set] = {}
    region_cats: dict[str, dict[str, int]] = {}
    verdicts = {"state": {}, "district": {}}
    why_tally: dict[str, dict[str, int]] = {"state": {}, "district": {}}
    why_districts = 0
    coverage: dict[str, int] = {}
    outlets = set()
    headlines = 0
    for did, d in research.items():
        coverage[d["coverage"]] = coverage.get(d["coverage"], 0) + 1
        headlines += len(d["headlines"])
        outlets |= {s["outlet"] for s in d["sources"]}
        for r in d["reasons"]:
            cat_districts.setdefault(r["category"], set()).add(did)
            rc = region_cats.setdefault(d["regionId"], {})
            rc[r["category"]] = rc.get(r["category"], 0) + EVIDENCE_WEIGHT[r["evidence"]]
        for c in d.get("officialFactorCheck", []):
            verdicts[c["method"]][c["verdict"]] = verdicts[c["method"]].get(c["verdict"], 0) + 1
        why_block = d.get("dominantFactorWhy") or {}
        if why_block.get("entries"):
            why_districts += 1
            for e in why_block["entries"]:
                why_tally[e["method"]][e["verdict"]] = why_tally[e["method"]].get(e["verdict"], 0) + 1
    categories = sorted(cat_districts.items(), key=lambda kv: -len(kv[1]))
    stats = {
        "districts": len(research), "sources": len(sources), "outlets": len(outlets), "headlines": headlines,
        "coverage": coverage, "verdicts": verdicts,
        "categories": {c: len(s) for c, s in categories},
    }

    def rate_text(did: str) -> str:
        p = profiles.get(did, {})
        if p.get("dropoutRate") is not None:
            return f"{p['dropoutRate']}%"
        subs = p.get("subAreas") or []
        return "; ".join(f"{s['name']} {s['dropoutRate']}%" for s in subs) or "n/a"

    def top_cats(rid: str, n: int = 3) -> list[str]:
        best = sorted(((c, v) for c, v in region_cats.get(rid, {}).items() if c != "other"), key=lambda kv: -kv[1])[:n]
        return [CATEGORY_LABEL[c] for c, _ in best]

    # ---- district sections ---------------------------------------------------------------------
    districts: dict[str, str] = {}
    for did, d in sorted(research.items()):
        L = [f"DISTRICT: {d['name']} ({region_short[d['regionId']]} region) | coverage: {d['coverage']} | casefile dropout rate: {rate_text(did)}"]
        L.append(f"Headline (DISTRICT): {d['headline']}")
        L.append(f"Summary (DISTRICT): {d['summary']}")
        L.append("Reasons students leave, strongest evidence first:")
        for r in sorted(d["reasons"], key=lambda r: EVIDENCE_ORDER[r["evidence"]]):
            L.append(f"- [{r['evidence']} evidence] {r['factor']} (DISTRICT): {r['detail']} {cites(did, r['sources'])}".rstrip())
        if d["keyFacts"]:
            L.append("Key facts:")
            for f in d["keyFacts"]:
                L.append(f"- {f['label']}: {f['value']} {scope_tag(f['label'])} {cites(did, f['sources'])}".rstrip())
        if d.get("responses"):
            L.append("What is being done locally:")
            for r in d["responses"]:
                L.append(f"- {r['text']} {cites(did, r['sources'])}".rstrip())
        checks = d.get("officialFactorCheck") or []
        if checks:
            L.append("Evidence check on the UIDAI/NITI factors (for questions about evidence or proof; when asked WHY a factor is dominant, give the possible reasons instead):")
            for c in checks:
                L.append(f"- {c['method']}-method factor \"{c['factor']}\": {c['verdict']}. {c['note']} {cites(did, c['sources'])}".rstrip())
        why = d.get("dominantFactorWhy") or {}
        if why.get("entries"):
            L.append("Deep-research answers on why each dominant factor may matter here (the verdict is the evidence check: report it only when asked for evidence or proof; each proof item was checked against its page):")
            for e in why["entries"]:
                def proofs(scope: str) -> str:
                    return " ".join(
                        f"{p['claim']} " + "".join(f"[{why_to_global[did][i]}]" for i in p["sources"] if i in why_to_global[did])
                        for p in e["proof"] if p["scope"] == scope
                    )
                parts = [f"- {e['method']}-method factor \"{e['factor']}\": {e['verdict']}. Model-written reasoning, not verified (SYNTHESIS): {e['why']}"]
                if e.get("mechanism"):
                    parts.append(f"How it could work (REASONING): {e['mechanism']}")
                if proofs("district"):
                    parts.append(f"Proof about this district (DISTRICT): {proofs('district')}")
                if proofs("general"):
                    parts.append(f"General research from elsewhere, not local evidence (GENERAL): {proofs('general')}")
                L.append(" ".join(parts))
        if d["headlines"]:
            L.append("Recent coverage:")
            for h in d["headlines"][:3]:
                L.append(f"- {h['outlet']}{(' ' + h['date']) if h['date'] else ''}: {h['title']} - {h['takeaway']}")
        if d["gaps"]:
            L.append(f"Gaps (what we could not find): {d['gaps']}")
        districts[did] = "\n".join(sslc(l) for l in L)

    # ---- region sections -----------------------------------------------------------------------
    sv = run.get("storyVsOfficial", {})
    ps = run.get("personaSimilarity", {})
    region_sections: dict[str, str] = {}
    for rid, r in regions.items():
        members = [(did, research[did]) for did in r["district_ids"] if did in research]
        rates = [profiles[did]["dropoutRate"] for did, _ in members if profiles.get(did, {}).get("dropoutRate") is not None]
        L = [f"REGION: {r['name']} | {len(members)} districts | average casefile dropout rate: {sum(rates) / len(rates):.1f}%" if rates else f"REGION: {r['name']}"]
        L.append(f"Most-documented reasons across its districts (DISTRICT-level evidence, summed): {', '.join(top_cats(rid)) or 'mixed'}.")
        L.append("Districts:")
        for did, d in sorted(members, key=lambda m: m[1]["name"]):
            L.append(sslc(f"- {d['name']} (casefile rate {rate_text(did)}, {d['coverage']} coverage): {d['headline']}"))
            top = sorted(d["reasons"], key=lambda r: EVIDENCE_ORDER[r["evidence"]])[:3]
            if top:
                L.append("    Top documented reasons here (DISTRICT): " + "; ".join(
                    f"{r['factor']} [{r['evidence']}] {cites(did, r['sources'])}".rstrip() for r in top))
        if rid in ps and ps[rid].get("status") == "ok":
            p = ps[rid]
            L.append(
                f"Persona analysis (SYNTHESIS, from a saved model run): answers in this region's male / female persona voice scored "
                f"{p['maleSimilarity']:.2f} / {p['femaleSimilarity']:.2f} similarity to a generic Karnataka answer (1.00 = identical; lower = the generic answer misses more of this region)."
            )
        if rid in sv and sv[rid].get("consolidatedAnswer"):
            L.append(f"Story Mode vs UIDAI/NITI, consolidated answer for the region (SYNTHESIS, model-written): {sv[rid]['consolidatedAnswer']}")
        region_sections[rid] = "\n".join(L)

    # ---- UIDAI/NITI section --------------------------------------------------------------------
    U = ["UIDAI / NITI AAYOG DOMINANT-FACTOR DATA (official statistics) and our check against local evidence",
         f"State-level method: {methods['state']}",
         f"District-level method: {methods['district']}",
         "Verdicts from checking each district's factor against local media/government/NGO evidence: " +
         "; ".join(f"{m}-method: " + ", ".join(f"{v} {n}" for v, n in sorted(t.items())) for m, t in verdicts.items()) +
         ". 'no-evidence' means the sources were silent, not that the factor is irrelevant.",
         *([f"Deep-research answers to 'why is this district's dominant factor dominant?' (each proof item checked against its page) exist for {why_districts} of {len(research)} districts. Verdicts: " +
            "; ".join(f"{m}-method: " + ", ".join(f"{v} {n}" for v, n in sorted(t.items())) for m, t in why_tally.items() if t) +
            ". 'partly' means only general research from elsewhere supports the mechanism, not local evidence; 'no-evidence' means nothing was found; none was supported by district-specific proof."] if why_districts else []),
         *FACTOR_REASONING,
         "Factor rows per district (value meaning unverified; never blend methods):"]
    for did in sorted(profiles):
        p = profiles[did]
        name = research[did]["name"] if did in research else did
        rows = "; ".join(f"{f['method']}-method{(' ' + f['area']) if f['area'].lower() != name.lower() else ''}: {f['factor']} = {f['value']}" for f in p.get("nitiFactors", []))
        U.append(f"- {name}: {rows or 'no rows'}")
    uidai = "\n".join(U)

    # ---- news vs data (scripts/build_news_vs_data.py: counts + templated sentences, no LLM) -------
    nvd = read(os.path.join(DATA, "news-vs-data.json"))
    s = nvd["statewide"]
    cl = s["news"]["childLabour"]
    hl = s["news"]["headlines"]
    nat = s["data"]["national"]
    N = ["NEWS VS DATA: why the news research and the UIDAI/NITI data name different main factors. Built from counts over the "
         "verified research files and the two workbooks (no model-written text), except where marked NOT TESTED.",
         f"Overview: {s['lead']}",
         "What the news says (districts where the research found each reason, of " + str(s["districts"]) + "): " +
         "; ".join(f"{c['label']} {c['districts']} ({c['strong']} strong, {c['moderate']} moderate, {c['thin']} thin reasons)" for c in s["news"]["categories"]) + ".",
         f"Child labour is named outright in {len(cl['districts'])} districts ({', '.join(cl['districts'])}): {cl['reasons']} reasons, "
         f"{cl['strong']} strong, {cl['moderate']} moderate, {cl['thin']} thin evidence. Of {hl['total']} headlines, {hl['childMarriage']} are about child marriage, "
         f"{hl['childLabour']} about child labour and {hl['language']} about the language of instruction.",
         "What the data says: state-level factor " + "; ".join(f"{f['factor']} on {f['rows']} Karnataka rows" for f in s["data"]["stateFactors"]) +
         ". District-level factor " + "; ".join(f"{f['factor']} on {f['rows']} rows" for f in s["data"]["districtFactors"]) +
         f". Across India the district-level factor '{nat['topDistrictFactor']}' is named for {nat['topDistrictFactorRows']} of {nat['rows']} districts "
         f"(rank {nat['topDistrictFactorRank']} of {len(nat['districtFactorNames'])} factors). Factors in the workbooks that measure child labour, marriage, migration or income: "
         f"{', '.join(nat['socialFactors']) or 'none'}.",
         "What our checks found: 'why is this factor dominant?' deep research, district-level rows: " +
         ", ".join(f"{v} {k}" for k, v in sorted(s["found"]["why"]["district"].items())) + "; state-level rows: " +
         ", ".join(f"{v} {k}" for k, v in sorted(s["found"]["why"]["state"].items())) +
         f". Verified proof for the district-level factor: about a Karnataka district itself {s['found']['districtLevelProof']['district']}; general proof from elsewhere "
         f"{s['found']['districtLevelProof']['general']} items ({'; '.join(s['found']['generalClaims'])}). News reasons that touch the language of instruction: " +
         ("; ".join(f"{x['name']} \"{x['factor']}\" ({x['evidence']})" for x in s["news"]["touchingLanguage"]) or "none") + ".",
         "Why they differ:"]
    for i, d in enumerate(s["differ"], 1):
        N.append(f"{i}. {d['title']}: {d['text']}")
    N.append(f"How both could be true (NOT TESTED, a hypothesis): {s['connect']['text']} {s['connect']['untested']}")
    N.append("Per district (news: most-documented reason groups | data: district-level factor | news reasons touching that factor | 'why dominant' verdict):")
    for did, d in sorted(nvd["districts"].items(), key=lambda kv: kv[1]["name"]):
        dfac = next((f["short"] for f in d["data"] if f["method"] == "district"), "none")
        touch = "; ".join(f"\"{x['factor']}\" ({x['evidence']})" for x in d["touching"]) or "none"
        N.append(f"- {d['name']}: news {', '.join(d['news']['topCategories'][:3])}{' (child labour named)' if d['news']['childLabour'] else ''} | "
                 f"data {dfac} | touching: {touch} | why: {', '.join(d['found']['district']['why']) or 'not researched'}")
    news_vs_data = "\n".join(N)

    # ---- analysis (story vs official + persona similarity, from the saved run) -------------------
    A = [f"ANALYSIS FROM A SAVED MODEL RUN (everything here is SYNTHESIS, model-written, not sourced evidence). Question asked: \"{run['query']}\" ({run.get('mode', '?')} mode)."]
    if sv.get("karnataka-statewide"):
        s = sv["karnataka-statewide"]
        if s.get("comparison"):
            A.append(f"Statewide, Story Mode vs UIDAI/NITI comparison: {s['comparison']}")
        if s.get("consolidatedAnswer"):
            A.append(f"Statewide consolidated answer: {s['consolidatedAnswer']}")
    sims = [(rid, p) for rid, p in ps.items() if p.get("status") == "ok"]
    if sims:
        matches = [((p["maleSimilarity"] + p["femaleSimilarity"]) / 2, rid) for rid, p in sims]
        gaps = [abs(p["maleSimilarity"] - p["femaleSimilarity"]) for _, p in sims]
        A.append(
            f"Persona similarity: a generic Karnataka answer matches region-voiced answers {sum(m for m, _ in matches) / len(matches):.2f} on average "
            f"(0-1 scale), ranging from {min(matches)[0]:.2f} ({region_short[min(matches)[1]]}) to {max(matches)[0]:.2f} ({region_short[max(matches)[1]]}). "
            f"Male and female persona voices in the same region differ by {sum(gaps) / len(gaps):.2f} on average, so region matters more than gender in this run."
        )
    analysis = "\n".join(A)

    # ---- personas ------------------------------------------------------------------------------
    P = ["PERSONAS: 12 composite characters (a man and a woman per region) built from public data -- (PERSONA), not real people. Facts about them are regional context, not sourced evidence."]
    for path in sorted(glob.glob(os.path.join(ROOT, "src", "lib", "worldview", "personaCards", "*.json"))):
        rid = os.path.basename(path)[:-5]
        for gender, c in read(path).items():
            pressures = "; ".join(f"{p['label']}: {p['detail']}" for p in c["schoolPressures"])
            P.append(
                f"- {region_short.get(rid, rid)} / {gender}: {c['name']}, {c['ageLabel']}, {c['role']}, {c['place']}"
                f"{', ' + c['community'] if c['community'] else ''}. {c['tagline']} What pulls children out of school in this household: {pressures}. "
                f"Worries: {', '.join(c['worries'])}."
            )
    personas = "\n".join(P)

    # ---- digest (always sent) ------------------------------------------------------------------
    strong_total = sum(1 for d in research.values() for r in d["reasons"] if r["evidence"] == "strong")
    D = [f"STUDY: why students leave secondary school (Classes 8-10 / SSLC) across Karnataka. Researched {stats['districts']} districts in {len(regions)} regions "
         f"from {stats['sources']} sources ({stats['outlets']} outlets, {stats['headlines']} news items, plus government and NGO reports). "
         f"Coverage: {coverage.get('moderate', 0)} districts moderate, {coverage.get('thin', 0)} thin. Every figure was checked against its cited page.",
         "Reasons documented, by number of districts: " + "; ".join(f"{CATEGORY_LABEL[c]} {len(s)} of {stats['districts']}" for c, s in categories if c != "other") + ".",
         "Regions: " + "; ".join(f"{region_short[rid]} (avg casefile dropout {sum(profiles[d]['dropoutRate'] for d in r['district_ids'] if profiles.get(d, {}).get('dropoutRate') is not None) / max(1, sum(1 for d in r['district_ids'] if profiles.get(d, {}).get('dropoutRate') is not None)):.1f}%; main reasons: {', '.join(top_cats(rid, 2))})" for rid, r in regions.items()) + ".",
         "UIDAI/NITI factor checks: " + "; ".join(f"{m}-method " + ", ".join(f"{v} {n}" for v, n in sorted(t.items())) for m, t in verdicts.items()) + " (no-evidence = sources silent).",
         "District index (name | region | coverage | casefile dropout rate | headline):"]
    for did, d in sorted(research.items(), key=lambda kv: kv[1]["name"]):
        D.append(sslc(f"- {d['name']} | {region_short[d['regionId']]} | {d['coverage']} | {rate_text(did)} | {d['headline']}"))
    D.append(f"Best-evidenced findings ({strong_total} reasons rated strong):")
    for did, d in sorted(research.items(), key=lambda kv: kv[1]["name"]):
        for r in d["reasons"]:
            if r["evidence"] == "strong":
                D.append(sslc(f"- {d['name']} (DISTRICT): {r['factor']} - {r['detail']} {cites(did, r['sources'])}".rstrip()))
    digest = "\n".join(D)

    # ---- router index --------------------------------------------------------------------------
    index = {
        "districts": [{"id": did, "name": d["name"], "regionId": d["regionId"], "aliases": ALIASES.get(d["name"], [d["name"].lower()])} for did, d in sorted(research.items())],
        "regions": [{"id": rid, "name": region_short[rid], "aliases": sorted({region_short[rid].lower(), *[a.lower() for a in r.get("aliases", [])]})} for rid, r in regions.items()],
    }

    pack = {
        "version": 1,
        "builtAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sourceHash": source_hash(),
        "stats": stats,
        "sources": sources,
        "index": index,
        "caveats": CAVEATS,
        "digest": digest,
        "regions": region_sections,
        "districts": districts,
        "uidai": uidai,
        "newsVsData": news_vs_data,
        "analysis": analysis,
        "personas": personas,
    }
    sections = [CAVEATS, digest, uidai, news_vs_data, analysis, personas, *region_sections.values(), *districts.values()]
    known = {s["id"] for s in sources}
    dangling = sorted({m for t in sections for m in re.findall(r"\[(S\d+)\]", t)} - known)
    if dangling:
        raise SystemExit(f"knowledge pack references unknown source ids: {dangling}")
    pack["tokenEstimate"] = {
        "alwaysSent": toks(CAVEATS) + toks(digest),
        "uidai": toks(uidai), "newsVsData": toks(news_vs_data), "analysis": toks(analysis), "personas": toks(personas),
        "regionMax": max(toks(t) for t in region_sections.values()),
        "districtMax": max(toks(t) for t in districts.values()),
        "wholePack": sum(toks(t) for t in sections),
    }
    return pack


def main() -> int:
    current = source_hash()
    if "--check" in sys.argv:
        if not os.path.isfile(OUT):
            print("knowledge-pack.json is missing -- run: python3 scripts/build_knowledge_pack.py")
            return 1
        built = read(OUT).get("sourceHash")
        if built != current:
            print(f"knowledge-pack.json is STALE (inputs changed). Rebuild: python3 scripts/build_knowledge_pack.py  [{built} != {current}]")
            return 1
        print(f"knowledge pack is up to date ({current})")
        return 0
    pack = build()
    if os.path.isfile(OUT):  # keep builtAt stable when nothing changed, so rebuilds don't churn git
        old = read(OUT)
        if old.get("sourceHash") == pack["sourceHash"]:
            pack["builtAt"] = old["builtAt"]
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(pack, fh, ensure_ascii=False, separators=(",", ":"))
    t = pack["tokenEstimate"]
    print(f"wrote {os.path.relpath(OUT, ROOT)} ({os.path.getsize(OUT) // 1024} KB, hash {pack['sourceHash']})")
    print(f"  always sent (caveats+digest): ~{t['alwaysSent']} tokens | biggest district ~{t['districtMax']} | biggest region ~{t['regionMax']}")
    print(f"  uidai ~{t['uidai']} | news vs data ~{t['newsVsData']} | analysis ~{t['analysis']} | personas ~{t['personas']} | whole pack ~{t['wholePack']} (Gemma window: 32,768)")
    print(f"  {pack['stats']['districts']} districts, {pack['stats']['sources']} global sources")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
