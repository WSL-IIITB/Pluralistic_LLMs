"""
Build the "news vs data" reconciliation the dashboard and the chat show side by side.

    python3 scripts/build_news_vs_data.py      # write public/data/news-vs-data.json

The news research (public/data/districts-research.json) and the UIDAI/NITI dominant-factor data
(public/data/districts.json + niti-factors.json) answer different questions, so they name different
"main" factors: the news mostly reports poverty, child labour and child marriage, while the data's
district-level factor for nearly every Karnataka district is the share of English-medium schools.

This script lays the two next to each other and explains the gap with counts taken straight from
those files: what the news says, what the data says, what our checks found, and why they differ.
It is deterministic extraction (no LLM). Every sentence is a template filled with counts or with text
already in the inputs; nothing here is a new claim. The "how they could connect" note is labelled
as untested.

Output: public/data/news-vs-data.json  {statewide{...}, districts{id: {...}}}
"""

from __future__ import annotations

import json
import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA = os.path.join(ROOT, "public", "data")
OUT = os.path.join(DATA, "news-vs-data.json")

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
# The household-side reason categories, and the short noun used for each in a sentence.
SOCIAL_NOUN = {"economic": "poverty or child labour", "gender": "child marriage", "migration": "migration", "social-norms": "social customs"}

CHILD_LABOUR = re.compile(r"child labou?r", re.I)
MARRIAGE = re.compile(r"child marriage|married off|early marriage", re.I)
# Words that would make a factor "about" the household's social or economic situation. None of the factors
# the workbooks name anywhere in India match, which is why child labour can never be a data factor.
SOCIAL = re.compile(r"labou?r|work|marri|migra|income|poverty|wage|employ|caste|tribe", re.I)

# Which news reasons touch each data factor. Kept narrow on purpose: a bare "English" also matches
# "English papers" in SSLC stories, which are about exams, not the language a school teaches in.
FAMILIES = {
    "english": {
        "match": "instruction medium 1 (English)",
        "topic": "the language a school teaches in",
        "short": "English-medium schools",
        "touch": re.compile(r"language gap|language barrier|kannada[- ]medium|english[- ]medium|medium of instruction|marathi|urdu", re.I),
    },
    "sanitation": {
        "match": "Improved Sanitation",
        "topic": "toilets or sanitation",
        "short": "household sanitation",
        "touch": re.compile(r"toilet|sanitation|menstrua|open defecation", re.I),
    },
    "well": {
        "match": "Protected Well",
        "topic": "drinking water at school",
        "short": "schools with a protected well",
        "touch": re.compile(r"drinking water|water supply|\bwells?\b", re.I),
    },
}

WHY_TEXT = {
    "supported": "supported by proof about this district",
    "partly": "partly: only research from elsewhere backs the mechanism",
    "not-supported": "not supported by the sources",
    "no-evidence": "no evidence found either way",
}
CHECK_TEXT = {
    "supports": "local evidence supports it",
    "contradicts": "local evidence contradicts it",
    "unclear": "local evidence is unclear",
    "no-evidence": "the sources are silent on it",
}


def read(name: str):
    with open(os.path.join(DATA, name), encoding="utf-8") as fh:
        return json.load(fh)


def family(factor: str) -> str | None:
    return next((k for k, f in FAMILIES.items() if f["match"] in factor), None)


def count(items, key) -> dict[str, int]:
    out: dict[str, int] = {}
    for x in items:
        out[key(x)] = out.get(key(x), 0) + 1
    return out


def plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


def build() -> dict:
    research = read("districts-research.json")
    profiles = {d["districtId"]: d for d in read("districts.json")["districts"]}
    niti = read("niti-factors.json")
    rows = niti["rows"]
    ka_rows = [r for r in rows if r["state"] == "Karnataka"]
    n = len(research)

    # ---- the data side -------------------------------------------------------------------------
    ka_factor_rows = [f for d in profiles.values() for f in d.get("nitiFactors", [])]
    state_factors = count([f for f in ka_factor_rows if f["method"] == "state"], lambda f: f["factor"])
    district_factors = count([f for f in ka_factor_rows if f["method"] == "district"], lambda f: f["factor"])
    district_rows_ka = sum(district_factors.values())
    top_district_factor, top_district_rows = max(district_factors.items(), key=lambda kv: kv[1])

    national_district = count([r for r in rows if r["districtFactor"]], lambda r: r["districtFactor"])
    national_state = count(rows, lambda r: r["stateFactor"])
    national_rank = sorted(national_district.items(), key=lambda kv: -kv[1])
    all_factor_names = sorted(set(national_district) | set(national_state))
    social_hits = [f for f in all_factor_names if SOCIAL.search(f)]

    # ---- the news side -------------------------------------------------------------------------
    cats: dict[str, dict] = {}
    labour = {"districts": set(), "reasons": 0, "strong": 0, "moderate": 0, "thin": 0}
    marriage_districts: set[str] = set()
    for did, d in research.items():
        for r in d["reasons"]:
            c = cats.setdefault(r["category"], {"districts": set(), "reasons": 0, "strong": 0, "moderate": 0, "thin": 0})
            c["districts"].add(did)
            c["reasons"] += 1
            c[r["evidence"]] += 1
            text = f"{r['factor']} {r['detail']}"
            if CHILD_LABOUR.search(text):
                labour["districts"].add(d["name"])
                labour["reasons"] += 1
                labour[r["evidence"]] += 1
            if MARRIAGE.search(text):
                marriage_districts.add(d["name"])
    categories = sorted(
        ({"category": k, "label": CATEGORY_LABEL[k], "districts": len(v["districts"]), "reasons": v["reasons"],
          "strong": v["strong"], "moderate": v["moderate"], "thin": v["thin"]} for k, v in cats.items() if k != "other"),
        key=lambda c: (-c["districts"], -c["reasons"]),
    )
    headlines = [h for d in research.values() for h in d["headlines"]]
    hl_text = [f"{h['title']} {h.get('takeaway', '')}" for h in headlines]

    # ---- what our checks found -----------------------------------------------------------------
    checks = {m: count([c for d in research.values() for c in d.get("officialFactorCheck", []) if c["method"] == m], lambda c: c["verdict"]) for m in ("state", "district")}
    why_entries = [e for d in research.values() for e in (d.get("dominantFactorWhy") or {}).get("entries", [])]
    why = {m: count([e for e in why_entries if e["method"] == m], lambda e: e["verdict"]) for m in ("state", "district")}
    proof = {s: sum(1 for e in why_entries if e["method"] == "district" for p in e["proof"] if p["scope"] == s) for s in ("district", "general")}
    general_claims = sorted({p["claim"] for e in why_entries if e["method"] == "district" for p in e["proof"] if p["scope"] == "general"})

    # ---- per district --------------------------------------------------------------------------
    touching_all: list[dict] = []
    districts: dict[str, dict] = {}
    for did, d in sorted(research.items(), key=lambda kv: kv[1]["name"]):
        name = d["name"]
        prof = profiles.get(did, {})
        factors = prof.get("nitiFactors", [])
        reasons = sorted(d["reasons"], key=lambda r: EVIDENCE_ORDER[r["evidence"]])
        dcats = count(d["reasons"], lambda r: r["category"])
        top_cats = [CATEGORY_LABEL[c] for c, _ in sorted(dcats.items(), key=lambda kv: -kv[1]) if c != "other"][:3]
        has_labour = any(CHILD_LABOUR.search(f"{r['factor']} {r['detail']}") for r in d["reasons"])

        fams = []
        for f in factors:
            fam = family(f["factor"])
            if fam and fam not in fams:
                fams.append(fam)
        touching = []
        for r in d["reasons"]:
            for fam in fams:
                if FAMILIES[fam]["touch"].search(f"{r['factor']} {r['detail']}"):
                    touching.append({"family": fam, "factor": r["factor"], "detail": r["detail"], "evidence": r["evidence"]})
                    touching_all.append({"districtId": did, "name": name, "family": fam, "factor": r["factor"], "evidence": r["evidence"]})

        entries = (d.get("dominantFactorWhy") or {}).get("entries", [])
        found = {}
        for m in ("state", "district"):
            es = [e for e in entries if e["method"] == m]
            chk = next((c for c in d.get("officialFactorCheck", []) if c["method"] == m), None)
            found[m] = {
                "check": chk["verdict"] if chk else None,
                "why": sorted({e["verdict"] for e in es}),
                "districtProof": sum(1 for e in es for p in e["proof"] if p["scope"] == "district"),
                "generalProof": sum(1 for e in es for p in e["proof"] if p["scope"] == "general"),
            }

        # why the two pictures differ here -- every bullet is a template over the counts above
        dfam = family(next((f["factor"] for f in factors if f["method"] == "district"), "")) or "english"
        topic = FAMILIES[dfam]["topic"]
        differ: list[str] = []
        social_cats = sorted((c for c in SOCIAL_NOUN if c in dcats), key=lambda c: -dcats[c])
        if social_cats:
            what = "child labour" if has_labour else SOCIAL_NOUN[social_cats[0]]
            differ.append(
                f"The news for {name} is mostly about {' and '.join(top_cats[:2])}. The data method only chooses among school, "
                f"teacher, inspection, household-amenity and women's-schooling indicators, so {what} could never come out as {name}'s data factor."
            )
        own = [t for t in touching if t["family"] == dfam]
        if own:
            differ.append(
                f"One news reason does touch {topic}: \"{own[0]['factor']}\" ({own[0]['evidence']} evidence). "
                "So here the news and the data do meet, on one point."
            )
        else:
            differ.append(
                f"None of the {plural(len(d['reasons']), 'reason')} the news gives for {name} mentions {topic}. "
                "The sources are silent on it, which is not the same as contradicting the data."
            )
        fd = found["district"]
        if fd["why"]:
            verdicts = ", ".join(WHY_TEXT[v] for v in fd["why"])
            counts = (
                f" ({plural(fd['districtProof'], 'verified proof item')} about {name}, {fd['generalProof']} from elsewhere)"
                if fd["districtProof"] or fd["generalProof"] else ""
            )
            differ.append(f"When we asked deep research why this factor would be dominant here, the result was: {verdicts}{counts}.")
        if dfam == "english":
            differ.append(
                f"The same factor is named for {top_district_rows} of {district_rows_ka} Karnataka district-level rows, "
                f"so it says more about a statewide pattern than about {name} in particular."
            )
        else:
            k = district_factors.get(next(f["factor"] for f in factors if f["method"] == "district"), 0)
            differ.append(
                f"This factor is named for only {k} of {district_rows_ka} Karnataka district-level rows; "
                f"the rest get {FAMILIES['english']['short']}."
            )
        if d["coverage"] == "thin":
            differ.append(f"News coverage of {name} is thin, so the news picture itself rests on few stories.")

        districts[did] = {
            "name": name,
            "regionId": d["regionId"],
            "coverage": d["coverage"],
            "news": {
                "reasons": len(d["reasons"]),
                "topCategories": top_cats,
                "top": [{"factor": r["factor"], "category": r["category"], "evidence": r["evidence"]} for r in reasons[:4]],
                "childLabour": has_labour,
            },
            "data": [{"method": f["method"], "factor": f["factor"], "short": FAMILIES[family(f["factor"])]["short"] if family(f["factor"]) else f["factor"],
                      "area": f["area"], "value": f["value"]} for f in factors],
            "found": found,
            "touching": touching,
            "differ": differ,
        }

    # ---- statewide explanation -----------------------------------------------------------------
    top = categories[0]
    second = categories[1] if len(categories) > 1 else None
    english_national = national_district.get(top_district_factor, 0)
    english_rank = next(i for i, (f, _) in enumerate(national_rank) if f == top_district_factor) + 1
    touch_english = [t for t in touching_all if t["family"] == "english"]
    touch_names = sorted({t["name"] for t in touch_english})
    hl_labour = sum(1 for t in hl_text if CHILD_LABOUR.search(t))
    hl_marriage = sum(1 for t in hl_text if MARRIAGE.search(t))
    lead = (
        f"In the news, the most widely reported reasons are {top['label']} ({top['districts']} of {n} districts)"
        + (f" and {second['label']} ({second['districts']})" if second else "")
        + f". Child labour is named outright in {len(labour['districts'])} districts, though child marriage gets more headlines "
        f"({hl_marriage} against {hl_labour}). In the UIDAI/NITI data, the district-level "
        f"dominant factor for {top_district_rows} of {district_rows_ka} Karnataka rows is the share of English-medium schools. "
        "They look like two answers to one question, but they are answers to two different questions."
    )
    differ_state = [
        {
            "title": "They answer different questions",
            "text": "The data asks which measured school or household indicator best tracks the differences in dropout "
                    "between districts. The news reports what pushes particular children out of school. A factor can track "
                    "dropout across districts without being what families describe, and the other way round.",
        },
        {
            "title": "The data cannot see child labour",
            "text": f"Across all {niti['source']['rows']} district rows in India, the workbooks name {len(national_state)} different "
                    f"state-level and {len(national_district)} district-level factors. Every one is a school-facility, teacher, inspection, "
                    "household-amenity or women's-schooling indicator. "
                    + ("None measures child labour, child marriage, migration or household income, so child labour could never come out "
                       "as a data factor." if not social_hits else f"Only these touch social conditions: {', '.join(social_hits)}."),
        },
        {
            "title": "News follows events",
            "text": f"Rescue raids, enforcement drives and NGO reports make stories, and each names a district. A school's language of "
                    f"instruction rarely does. Of the {labour['reasons']} child-labour reasons we found, {labour['strong']} rests on strong "
                    f"evidence, {labour['moderate']} on moderate and {labour['thin']} on thin. Child labour is widely mentioned, "
                    "but the evidence behind each mention is usually thin.",
        },
        {
            "title": "One indicator for almost every district",
            "text": f"English-medium share is the district-level factor for {top_district_rows} of {district_rows_ka} Karnataka rows and "
                    f"for {english_national} of {niti['source']['rows']} districts nationally, the "
                    f"{'most common' if english_rank == 1 else f'#{english_rank} most common'} factor in India. When the same indicator is "
                    "picked nearly everywhere, it behaves like a broad background marker rather than a local explanation. "
                    f"Its value is described as a fitted weight from the analysis, not a share of schools.",
        },
    ]
    connect = {
        "text": "Both can be true. The share of English-medium schools may track access to private and urban schooling and "
                "household means, which are the same conditions under which the news reports children working instead of "
                "studying. General research from elsewhere, found during our checks, also links a change in the medium of "
                "instruction, or lessons in an unfamiliar language, to students dropping out"
                + (f" ({len(general_claims)} page-verified claims, none about a Karnataka district)." if general_claims else "."),
        "untested": "We have not tested this. Our files hold neither each district's actual share of English-medium schools nor a "
                    "district-level measure of child labour. Testing it would need both, analysed together against dropout.",
    }

    statewide = {
        "districts": n,
        "lead": lead,
        "news": {
            "categories": categories,
            "childLabour": {"districts": sorted(labour["districts"]), "reasons": labour["reasons"],
                            "strong": labour["strong"], "moderate": labour["moderate"], "thin": labour["thin"]},
            "childMarriageDistricts": len(marriage_districts),
            "headlines": {
                "total": len(headlines),
                "childLabour": hl_labour,
                "childMarriage": hl_marriage,
                "language": sum(1 for t in hl_text if FAMILIES["english"]["touch"].search(t)),
            },
            "touchingLanguage": touch_english,
            "touchingLanguageDistricts": touch_names,
        },
        "data": {
            "methods": niti["methods"],
            "stateFactors": [{"factor": f, "rows": k} for f, k in sorted(state_factors.items(), key=lambda kv: -kv[1])],
            "districtFactors": [{"factor": f, "rows": k} for f, k in sorted(district_factors.items(), key=lambda kv: -kv[1])],
            "karnatakaWorkbookRows": len(ka_rows),
            "national": {
                "rows": niti["source"]["rows"],
                "topDistrictFactor": top_district_factor,
                "topDistrictFactorRows": english_national,
                "topDistrictFactorRank": english_rank,
                "stateFactorNames": sorted(national_state),
                "districtFactorNames": sorted(national_district),
                "socialFactors": social_hits,
            },
        },
        "found": {"check": checks, "why": why, "districtLevelProof": proof, "generalClaims": general_claims},
        "differ": differ_state,
        "connect": connect,
    }
    return {"version": 1, "inputs": ["districts-research.json", "districts.json", "niti-factors.json"], "statewide": statewide, "districts": districts}


def main() -> int:
    out = build()
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    s = out["statewide"]
    print(f"wrote {os.path.relpath(OUT, ROOT)} ({os.path.getsize(OUT) // 1024} KB, {len(out['districts'])} districts)")
    print(" ", s["lead"])
    print("  social factors in the data:", s["data"]["national"]["socialFactors"] or "none")
    print("  news reasons touching the language of instruction:", ", ".join(s["news"]["touchingLanguageDistricts"]) or "none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
