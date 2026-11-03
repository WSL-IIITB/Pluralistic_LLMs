"""
Build the "news vs data" reconciliation the dashboard and the chat show side by side.

    python3 scripts/build_news_vs_data.py      # write public/data/news-vs-data.json

The news research (public/data/districts-research.json) and the UIDAI/NITI dominant-factor data
(public/data/districts.json + niti-factors.json) answer different questions, so they name different
"main" factors: the news mostly reports poverty, child labour and child marriage, while the data's
district-level factor for nearly every Karnataka district is the share of English-medium schools.

This script lays the two next to each other and explains the gap with counts taken straight from
those files: what the news says, what the data says, and how the two may connect.
It is deterministic extraction (no LLM). Every sentence is a template filled with counts or with text
already in the inputs, or general reasoning on how a data factor could be linked to a kind of news reason (labelled as
possible links, not findings).

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

# Which researched news reasons touch each factor of the NITI prescriptive model (public/data/niti-prescriptive.json).
CHANGE_TOUCH = {
    "% Classrooms in Good Condition": r"classroom|school building|dilapidat|roof|leak|collaps|repair|crumbl",
    "% Schools with Functional Total Toilets": r"toilet|washroom|sanitar",
    "% Schools with Library": r"librar",
    "% Schools with Furniture available for students": r"furniture|desk|bench|sit on the floor",
    "% of female teachers": r"female teacher|women teacher|woman teacher|lady teacher",
    "% Women with 10+ Years Schooling": r"mother|parental illitera|female literacy|women.{0,20}literacy|illiterate parent",
    "% Population Living in Households with Improved Sanitation": r"toilet|sanitation|open defecation",
    "% Schools with CCE Implemented": r"evaluation|assessment|\\bcce\\b|tracking",
    "% Schools with Playground": r"playground|sport",
    "% Schools with All-Weather Roads": r"\\broads?\\b|\\bbus\\b|transport|commute",
    "% Teachers Trained in ICT/Computers": r"computer|digital|\\bict\\b|smart class|online",
    "% Schools with Computer/ICT Labs": r"computer|digital|\\bict\\b|smart class|online",
    "% Schools with Functional Protected Well": r"drinking water|water supply|\\bwells?\\b",
    "Teachers per 100 students": r"teacher (vacanc|shortage)|shortage of teachers|single-teacher|zero-teacher|teacherless",
}
# How each data factor could be linked to each kind of reason the news reports. General reasoning, worded as
# possibilities; the UI and the chat label these as possible links, not findings. {name} is the district.
LINKS = {
    "english": {
        "economic": "Where few schools teach in English, families who can pay move their children to private English-medium schools, and the government schools left behind serve the poorest households: the ones the news describes as short of money and sending children to work.",
        "economic-higher": "Most English-medium schools charge fees, so the share marks the line between families who can pay and those who cannot; the poorest households, the ones the news describes as short of money and sending children to work, stay in government schools that teach in Kannada.",
        "gender": "When lessons and the SSLC papers lean on English, girls who studied in Kannada can fall behind, and in a family already weighing a daughter's marriage, falling behind becomes the reason to stop. Families also tend to pay for English-medium schooling for sons first.",
        "migration": "Children of migrant families often speak another language at home; schooling in an unfamiliar language, or a switch of medium each time the family moves, makes them fall behind again and again.",
        "school-infrastructure": "As families who can afford it move to English-medium private schools, the government schools that remain lose pupils, teachers and upkeep: the same weak school conditions the news reports.",
        "governance": "The SSLC exam is where a weak grip on English shows: students who studied in Kannada but face English-heavy subjects can fail, and the news here links exam failure with leaving school.",
        "social-norms": "Where custom gives girls' schooling less weight, families are less likely to pay for English-medium schooling for daughters, so the language gap and the custom feed each other.",
        "health": "Children who miss school through illness fall further behind in an English-heavy curriculum, and catching up gets harder each time.",
    },
    "sanitation": {
        "economic": "Homes without a toilet are usually the poorest ones. The same lack of money that leaves a toilet unbuilt pushes children toward work, so household sanitation can track the poverty the news reports.",
        "gender": "Without a toilet at home, adolescent girls face safety risks going out in the open and lack privacy; families fearful for a daughter's safety may keep her home or marry her early: the girls' exits the news describes.",
        "migration": "Migrant and seasonal-work families often live in temporary housing without toilets, so household sanitation can track the same mobility the news ties to dropout.",
        "school-infrastructure": "Where homes lack toilets, schools often lack working ones too, and girls stay home on the days they cannot manage at school.",
        "governance": "Illness spread by poor sanitation means missed days and lost lessons in the run-up to the SSLC exam.",
        "social-norms": "The worries about girls' safety and privacy that grow without a home toilet feed the same customs that end girls' schooling early.",
        "health": "Poor sanitation spreads infections, and repeated illness keeps children out of class: the health link the news reports.",
    },
    "well": {
        "economic": "Schools that rely on wells rather than piped water tend to sit in under-served, poorer neighbourhoods and fringes, the same places where families need children's earnings.",
        "gender": "Without safe water at school, girls cannot use the toilets or manage menstruation there, one more pressure on adolescent girls to stay home.",
        "migration": "Fast-growing fringes where migrant families settle often have schools still on wells, with weaker facilities and crowded classrooms.",
        "school-infrastructure": "Depending on a well marks a school with weaker facilities overall: the infrastructure gaps the news reports.",
        "governance": "Schools with weaker facilities also tend to follow up less on absent students, so a child drifting away goes unnoticed.",
        "social-norms": "Unsafe water and unusable toilets give families who doubt the value of a daughter's schooling one more reason to keep her home.",
        "health": "Unsafe drinking water at school means illness and lost school days.",
    },
}
# A clause tying any NITI prescriptive change to the district's main kind of news reason.
BRIDGE = {
    "economic": "a school that works well is one less reason for a hard-pressed family to send a child to work",
    "gender": "a school girls can attend safely and comfortably weighs against early marriage",
    "migration": "a school worth coming back to matters for children who come and go with their families' work",
    "school-infrastructure": "it is part of the same school conditions the news describes",
    "governance": "better rooms and teaching give students a better chance at the SSLC exam the news links to leaving",
    "social-norms": "a school families trust makes it easier to keep daughters enrolled against local custom",
    "health": "it helps children who miss days through illness keep up",
    "other": "it removes one more obstacle to staying in school",
}
# Household factors in the prescriptive model need their own tie-in (they are not about the school).
BRIDGE_HOUSEHOLD = {
    "% Women with 10+ Years Schooling": {
        "economic": "mothers who studied longer are more likely to hold out against sending a child to work",
        "gender": "mothers who studied longer are more likely to resist an early marriage for a daughter",
        "other": "mothers who studied longer are more likely to keep their children in school",
    },
    "% Population Living in Households with Improved Sanitation": {
        "gender": "a toilet at home removes one of the worries that push families to keep daughters home or marry them early",
        "economic": "a toilet at home is part of the same basic security that keeps children in school rather than at work",
        "other": "fewer infections at home mean fewer missed school days",
    },
}
REASON_PREFER = {
    "economic": re.compile(r"labou?r|poverty|work|wage|earn|debt|cost", re.I),
    "gender": re.compile(r"marri|girl", re.I),
    "migration": re.compile(r"migra|seasonal|move", re.I),
    "school-infrastructure": re.compile(r"classroom|building|toilet|teacher|distance|school", re.I),
    "governance": re.compile(r"sslc|exam|fail|track", re.I),
}
SHARE_LABEL = {
    "english": "share of English-medium schools",
    "sanitation": "share of people in households with improved sanitation",
    "well": "share of schools with a protected well",
}
PRES_NAME = {
    "english": "% Schools with instruction medium 1 (English)",
    "sanitation": "% Population Living in Households with Improved Sanitation",
    "well": "% Schools with Functional Protected Well",
}


def level(rank: int, total: int = 35) -> str:
    return "a high" if rank <= total // 3 else "a middling" if rank <= 2 * total // 3 else "a low"


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
    pres = read("niti-prescriptive.json")
    pres_info = {f["name"]: f for f in pres["factors"]}
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

    # ---- research from elsewhere on the district-level factor (verified general claims) ---------
    why_entries = [e for d in research.values() for e in (d.get("dominantFactorWhy") or {}).get("entries", [])]
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

        # the district's real indicator values (share and rank) from the NITI prescriptive file, matched by workbook area
        area_rows = {a["area"]: {f["name"]: f for f in a["factors"]} for a in pres["districts"].get(did, {}).get("areas", [])}
        main_area = next(iter(area_rows), None)

        def share(fam: str, area: str | None = None) -> dict | None:
            rows = area_rows.get(area or main_area) or area_rows.get(main_area) or {}
            return rows.get(PRES_NAME[fam])

        # how the news and the data may connect here -- possible links, worded as reasoning
        dfam = family(next((f["factor"] for f in factors if f["method"] == "district"), "")) or "english"
        cats = [c for c, _ in sorted(dcats.items(), key=lambda kv: -kv[1]) if c != "other" and c in LINKS[dfam]][:2] or ["economic"]
        connections: list[dict] = []
        own = [t for t in touching if t["family"] == dfam]
        if own:
            connections.append({
                "title": "Where they already meet",
                "text": f"The news here reports \"{own[0]['factor']}\": {own[0]['detail']} That is the data's factor, {FAMILIES[dfam]['topic']}, showing up on the ground.",
            })
        def top_reason(cat: str) -> dict | None:
            """The best-evidenced reason in the category, preferring one whose wording matches what the link is about."""
            pool = [r for r in reasons if r["category"] == cat]
            rx = REASON_PREFER.get(cat)
            return next((r for r in pool if rx and rx.search(r["factor"])), pool[0] if pool else None)

        s = share(dfam)
        lead_in = (f"{name} has {level(s['rank'])} {SHARE_LABEL[dfam]} ({s['value']:.1f}%, rank {s['rank']} of 35). " if s else "")
        for k, c in enumerate(cats):
            r = top_reason(c)
            connections.append({
                "title": f"{FAMILIES[dfam]['short'].capitalize()} and {CATEGORY_LABEL[c]}",
                "text": (lead_in if k == 0 else "") + (f"The news here reports \"{r['factor']}\". " if r else "")
                        + LINKS[dfam].get(f"{c}-higher" if s and s["rank"] <= 23 and dfam == "english" else c, LINKS[dfam][c]),
                "reason": r["factor"] if r else "", "reasonSources": r["sources"] if r else [],
            })
        scat = "gender" if "gender" in dcats else cats[0]
        s2 = share("sanitation")
        r2 = top_reason(scat)
        connections.append({
            "title": f"Household sanitation and {CATEGORY_LABEL[scat]}",
            "text": (f"{s2['value']:.1f}% of people in {name} live in households with improved sanitation (rank {s2['rank']} of 35). " if s2 else "")
                    + (f"The news here reports \"{r2['factor']}\". " if r2 else "") + LINKS["sanitation"][scat],
            "reason": r2["factor"] if r2 else "", "reasonSources": r2["sources"] if r2 else [],
        })
        connections.append({
            "title": "The common thread",
            "text": f"Both data factors describe how well-off and well-served {name} is; the news describes what falling short of that "
                    "does to particular families. Read together, they are two sides of the same picture.",
        })

        # the NITI prescriptive model's top three changes vs the verified web sources vs the news research
        pre = d.get("prescriptiveEvidence") or {}
        best: dict[str, dict] = {}
        for a in pres["districts"].get(did, {}).get("areas", []):
            for f in a["factors"]:
                if f["feasible"]["contribution"] > best.get(f["name"], {}).get("feasible", {}).get("contribution", -1):
                    best[f["name"]] = {**f, "area": a["area"]}
        top_changes = []
        for i, c in enumerate(pre.get("changes", []), 1):
            rx = re.compile(CHANGE_TOUCH.get(c["factor"], r"(?!x)x"), re.I)
            hits = [r["factor"] for r in d["reasons"] if rx.search(f"{r['factor']} {r['detail']}")]
            local = [k for k in c["findings"] if k["scope"] == "district"]
            gaps = [k for k in local if k["stance"] == "gap"]
            short = pres_info[c["factor"]]["short"]
            f = best.get(c["factor"], {})
            why = pres_info[c["factor"]]["why"].split(". ")[0].rstrip(".") + "."
            cat = cats[(i - 1) % len(cats)]  # a different news reason for each change, where there are several
            hb = BRIDGE_HOUSEHOLD.get(c["factor"])
            tie = (hb.get(cat) or hb["other"]) if hb else BRIDGE.get(cat, BRIDGE["other"])
            line = f"{why} Here, where the news reports {CATEGORY_LABEL[cat]}, {tie}."
            if hits:
                line += f" The news itself names it: \"{hits[0]}\"."
            if gaps:
                line += f" Local reports show this gap in {name}."
            top_changes.append({
                "rank": i, "factor": c["factor"], "short": short, "area": f.get("area", ""),
                "value": f.get("value"), "karnatakaRank": f.get("rank"), "contribution": f.get("feasible", {}).get("contribution"),
                "findings": len(c["findings"]), "districtFindings": len(local), "stances": count(local, lambda k: k["stance"]),
                "newsReasons": hits[:3], "line": line,
            })

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
                      "area": f["area"], "weight": f["value"],
                      "share": (share(family(f["factor"]), f["area"]) or {}).get("value") if family(f["factor"]) else None,
                      "shareRank": (share(family(f["factor"]), f["area"]) or {}).get("rank") if family(f["factor"]) else None}
                     for f in factors],
            "touching": touching,
            "connections": connections,
            "topChanges": top_changes,
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
        "They look like two answers to one question; they are two views of the same problem."
    )
    gender_districts = next((c["districts"] for c in categories if c["category"] == "gender"), 0)
    examples = "; ".join(f"{x['name']}: \"{x['factor']}\"" for x in touch_english)
    connections = [
        {
            "title": "Two views of one problem",
            "text": "The data compares districts by the conditions of their schools and households; the news follows what happens "
                    "inside particular families. The data's indicators are all school, teacher, inspection, household-amenity and "
                    "women's-schooling measures, none of them child labour, marriage or migration, so child labour itself can never "
                    "appear as a data factor: the data shows the conditions around a child, the news what happens to the child. The "
                    "same deprivation shows up in both: as a low share or a poor facility in the data, and as a child sent to work or "
                    "married early in the news.",
        },
        {
            "title": "English-medium share as a marker of means",
            "text": f"English-medium share is the district-level factor for {top_district_rows} of {district_rows_ka} Karnataka rows. "
                    "Where few schools teach in English, families who can pay move their children to private English-medium schools, "
                    "and government schools are left with the poorest households: the ones the news describes sending children to "
                    f"work (child labour is named outright in {len(labour['districts'])} districts).",
        },
        {
            "title": "Language and the SSLC exam",
            "text": "Students who studied in Kannada can struggle when lessons and papers lean on English. Failing the SSLC exam "
                    "often ends schooling, and in a family already weighing work or marriage, one failure is enough. Research from "
                    "elsewhere links a change in the medium of instruction, and lessons in an unfamiliar language, to students dropping out.",
        },
        {
            "title": "Household sanitation and girls' exits",
            "text": "Household sanitation is the state-level factor for every Karnataka row. Without a toilet at home, adolescent "
                    "girls face safety and privacy worries, and families respond by keeping daughters home or marrying them early: "
                    f"the girls' exits the news reports in {gender_districts} of {n} districts.",
        },
        *([{
            "title": "Where they already meet",
            "text": f"In {' and '.join(touch_names)}, the news itself reports the language of instruction as a problem ({examples}).",
        }] if touch_english else []),
    ]

    all_changes = [c for x in districts.values() for c in x["topChanges"]]
    pre_factor: dict[str, dict[str, int]] = {}
    for c in all_changes:
        pf = pre_factor.setdefault(c["short"], {"districts": 0, "withSources": 0})
        pf["districts"] += 1
        pf["withSources"] += any(k == "gap" for k in c["stances"])
    by_factor = [{"short": k, **v} for k, v in sorted(pre_factor.items(), key=lambda kv: -kv[1]["districts"])]
    picks = ", ".join(f"{f['short'].lower()} ({f['districts']})" for f in by_factor[:4])
    top_pf = by_factor[0] if by_factor else None
    prescriptive = {
        "changes": len(all_changes),
        "byFactor": by_factor,
        "text": (
            f"The NITI model's top changes are about school conditions: {picks} districts. The news describes household "
            f"pressures: {top['label']} and {second['label'] if second else 'more'}. They meet in the classroom: a family weighing a "
            "child's work or a daughter's marriage looks at what the school offers, and a leaking room, no desk or no woman teacher "
            "can tip that choice."
            + (f" Local reports show the {top_pf['short'].lower()} gap in {top_pf['withSources']} of the {top_pf['districts']} districts "
               "where it is a top change." if top_pf and top_pf["withSources"] else "")
        ),
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
        "meet": {"touchingLanguage": touch_english, "generalClaims": general_claims},
        "connections": connections,
        "prescriptive": prescriptive,
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
