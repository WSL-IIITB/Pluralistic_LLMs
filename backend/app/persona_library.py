"""
The persona library: district-level personas, one man and one woman per Karnataka
district, kept apart from any study question or dataset.

A persona here is a PERSON -- work, family, schooling, health, community, civic life,
worldview. It carries no dropout factors, no NITI/UIDAI numbers and no study framing;
the data lives in its own files (district_research/, niti/) and is only ever handed to a
persona as evidence at question time (see `ask`). That way "What is the reason for
dropouts?" and "What is the reason for dropouts, as this person?" can be put side by
side with the same evidence, and the only difference between them is the persona.

Three sources, one record shape (`PersonaRecord`):

  curated   -- the 12 hand-researched regional personas (data/personas/<region>_<g>.json),
               each placed in the district its card names (CURATED_DISTRICTS).
  generated -- LLM-written personas for the remaining district slots
               (data/persona_library/generated/<districtId>-<gender>.json).
  custom    -- personas a user created or fine-tuned in the dashboard
               (data/persona_library/custom/<id>.json).

A curated persona's display card lives in the frontend (src/lib/worldview/personaCards);
generated and custom personas carry their own `card` in the same shape.
"""

from __future__ import annotations

import asyncio
import glob
import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

from .config import DATA_DIR
from .karnataka import build_persona_prompt, load_persona, persona_regions, region_by_id

LIBRARY_DIR = os.path.join(DATA_DIR, "persona_library")
GENERATED_DIR = os.path.join(LIBRARY_DIR, "generated")
CUSTOM_DIR = os.path.join(LIBRARY_DIR, "custom")
_BRIEFS_DIR = os.path.normpath(os.path.join(DATA_DIR, "..", "..", "..", "docs", "persona-research", "briefs"))

GENDERS = ("male", "female")

# The district each curated persona lives in (the place on its card).
CURATED_DISTRICTS: dict[tuple[str, str], str] = {
    ("old-mysuru", "male"): "29-573",
    ("old-mysuru", "female"): "29-572",
    ("bayaluseeme", "male"): "29-566",
    ("bayaluseeme", "female"): "29-582",
    ("karavali", "male"): "29-563",
    ("karavali", "female"): "29-569",
    ("malnad", "male"): "29-570",
    ("malnad", "female"): "29-576",
    ("kitturu-karnataka", "male"): "29-555",
    ("kitturu-karnataka", "female"): "29-557",
    ("kalyana-karnataka", "male"): "29-579",
    ("kalyana-karnataka", "female"): "29-565",
}

# The seven parts of a person, worded so none of them points at a study question.
TOPICS: list[tuple[str, str, str]] = [
    ("daily_life_and_work", "Daily Life and Work", "Occupation, income, the working day and economic pressures."),
    ("family_and_household", "Family and Household", "Household members, marriage, children, caregiving and gender roles."),
    (
        "education_and_schooling",
        "Education and Schooling",
        "Their own schooling, and the schooling of the children in the household: where they study, "
        "what it costs, and what the family hopes for.",
    ),
    ("health_and_wellbeing", "Health and Wellbeing", "Health access, risks and concerns for this person and their family."),
    ("community_and_belief", "Community and Belief", "Community, caste/religious context, social ties and local institutions."),
    ("civic_life_and_government", "Civic Life and Government", "Dealings with government schemes, local bodies and politics."),
    ("worldview_and_concerns", "Worldview and Concerns", "What this person worries about, is proud of, blames and demands."),
]
TOPIC_KEYS = [k for k, _, _ in TOPICS]
TOPIC_LABELS = {k: label for k, label, _ in TOPICS}

_ID_RE = re.compile(r"^[a-z0-9-]{3,80}$")


# ── Districts ────────────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def districts() -> list[dict]:
    """Every map district: id, name, region -- in region order, then by name."""
    names: dict[str, str] = {}
    for path in glob.glob(os.path.join(DATA_DIR, "district_research", "29-*.json")):
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
        names[d["districtId"]] = d.get("name") or d["districtId"]
    out = []
    for region in persona_regions():
        rows = [
            {"districtId": did, "name": names.get(did, did), "regionId": region["id"]}
            for did in region["district_ids"]
        ]
        out.extend(sorted(rows, key=lambda r: r["name"]))
    return out


def district_by_id() -> dict[str, dict]:
    return {d["districtId"]: d for d in districts()}


# ── Records ──────────────────────────────────────────────────────────────────


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _curated_record(region_id: str, gender: str) -> dict:
    persona = load_persona(region_id, gender)
    district_id = CURATED_DISTRICTS[(region_id, gender)]
    topics = persona.get("topics") or {}
    return {
        "id": f"{district_id}-{gender}",
        "source": "curated",
        "districtId": district_id,
        "districtName": district_by_id().get(district_id, {}).get("name", district_id),
        "regionId": region_id,
        "gender": gender,
        "name": persona.get("region_name") or "",
        "definition": persona.get("region_definition") or "",
        "topics": [
            {
                "key": key,
                "label": TOPIC_LABELS.get(key) or t.get("topic_label") or key,
                "profile": (t.get("regional_profile") or "").strip(),
            }
            for key, t in topics.items()
        ],
        "card": None,  # the frontend's hand-distilled card (personaCards/<region>.json)
        "curatedRef": {"regionId": region_id, "personaId": gender},
    }


def _read_dir(path: str) -> list[dict]:
    out = []
    for f in sorted(glob.glob(os.path.join(path, "*.json"))):
        try:
            with open(f, encoding="utf-8") as fh:
                out.append(json.load(fh))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[persona_library] skipping unreadable {f}: {exc}", flush=True)
    return out


def all_personas() -> list[dict]:
    """Curated, then generated, then custom -- each with its prompt version."""
    records = [_curated_record(r["id"], g) for r in persona_regions() for g in GENDERS]
    records += _read_dir(GENERATED_DIR)
    records += _read_dir(CUSTOM_DIR)
    for r in records:
        r["version"] = persona_version(r)
    return records


def get_persona(persona_id: str) -> dict | None:
    return next((p for p in all_personas() if p["id"] == persona_id), None)


def summary(record: dict) -> dict:
    """List-view shape: everything but the long topic text."""
    card = record.get("card") or {}
    return {
        "id": record["id"],
        "source": record["source"],
        "districtId": record["districtId"],
        "districtName": record.get("districtName"),
        "regionId": record["regionId"],
        "gender": record["gender"],
        "name": card.get("name") or record.get("name"),
        "role": card.get("role"),
        "place": card.get("place") or record.get("place"),
        "emoji": card.get("emoji"),
        "curatedRef": record.get("curatedRef"),
        "basedOn": record.get("basedOn"),
        "createdAt": record.get("createdAt"),
        "version": record.get("version"),
    }


# ── Prompt ───────────────────────────────────────────────────────────────────


def build_prompt(record: dict) -> str:
    """Deterministic persona text, same template as karnataka.build_persona_prompt but
    placed in a district. Same record -> same prompt, so replies stay comparable. A curated
    persona uses the pipeline's own prompt, so its version hash matches the Map runs'."""
    ref = record.get("curatedRef")
    if record.get("source") == "curated" and ref:
        return build_persona_prompt(ref["regionId"], ref["personaId"])
    district = record.get("districtName") or record["districtId"]
    region = region_by_id().get(record["regionId"], {}).get("name", record["regionId"])
    sections = [
        f"## {t.get('label') or TOPIC_LABELS.get(t['key'], t['key'])}\n{t['profile'].strip()}"
        for t in record.get("topics") or []
        if (t.get("profile") or "").strip()
    ]
    return (
        f"PERSONA -- you are {record['name']}, a resident of {district} district in Karnataka's {region}.\n"
        f"Who you are: {record['definition']}\n\n"
        "Answer as this person would: from their own priorities, constraints, lived experience and "
        "community, naming the local places, institutions, work and concerns that matter to them. Use "
        "the profile below only where it genuinely bears on the question -- never recite it -- and "
        "never invent statistics beyond it and the supplied evidence.\n\n"
        "PERSONA PROFILE\n\n" + "\n\n".join(sections)
    )


def persona_version(record: dict) -> str:
    return hashlib.sha256(build_prompt(record).encode("utf-8")).hexdigest()[:10]


# ── Saving ───────────────────────────────────────────────────────────────────


def _clean_record(raw: dict) -> dict:
    """Validate and normalise a record coming from the generator or the UI."""
    district_id = raw.get("districtId")
    district = district_by_id().get(district_id or "")
    if not district:
        raise ValueError(f"unknown district {district_id!r}")
    gender = raw.get("gender")
    if gender not in GENDERS:
        raise ValueError("gender must be 'male' or 'female'")
    name = str(raw.get("name") or "").strip()
    definition = str(raw.get("definition") or "").strip()
    if not name or not definition:
        raise ValueError("a persona needs a name and a definition")
    by_key = {t.get("key"): t for t in raw.get("topics") or [] if isinstance(t, dict)}
    topics = [
        {"key": key, "label": TOPIC_LABELS[key], "profile": str((by_key.get(key) or {}).get("profile") or "").strip()}
        for key in TOPIC_KEYS
    ]
    if sum(1 for t in topics if t["profile"]) < 3:
        raise ValueError("a persona needs at least three topics written")
    card = _clean_card(raw["card"]) if isinstance(raw.get("card"), dict) else None
    out = {
        "districtId": district_id,
        "districtName": district["name"],
        "regionId": district["regionId"],
        "gender": gender,
        "name": name,
        "place": str(raw.get("place") or "").strip(),
        "definition": definition,
        "topics": topics,
        "card": card,
        "traits": raw.get("traits") if isinstance(raw.get("traits"), dict) else {},
        "basedOn": raw.get("basedOn"),
        "provider": raw.get("provider"),
    }
    return out


def _write(path: str, record: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(record, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


def save_generated(raw: dict) -> dict:
    record = _clean_record(raw)
    record["id"] = f"{record['districtId']}-{record['gender']}"
    if any(d == record["districtId"] and g == record["gender"] for (_, g), d in CURATED_DISTRICTS.items()):
        raise ValueError(f"{record['id']} is a curated persona's slot")
    record["source"] = "generated"
    record["createdAt"] = _now()
    _write(os.path.join(GENERATED_DIR, f"{record['id']}.json"), record)
    record["version"] = persona_version(record)
    return record


def save_custom(raw: dict, persona_id: str | None = None) -> dict:
    """Create (persona_id None) or overwrite a user's own persona."""
    record = _clean_record(raw)
    if persona_id is None:
        persona_id = f"custom-{record['districtId']}-{record['gender']}-{uuid.uuid4().hex[:6]}"
    elif not persona_id.startswith("custom-") or not _ID_RE.match(persona_id):
        raise ValueError("only custom personas can be edited in place")
    path = os.path.join(CUSTOM_DIR, f"{persona_id}.json")
    created = None
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            created = json.load(fh).get("createdAt")
    record.update(id=persona_id, source="custom", createdAt=created or _now(), updatedAt=_now())
    _write(path, record)
    record["version"] = persona_version(record)
    return record


def delete_custom(persona_id: str) -> bool:
    if not persona_id.startswith("custom-") or not _ID_RE.match(persona_id):
        return False
    path = os.path.join(CUSTOM_DIR, f"{persona_id}.json")
    if not os.path.isfile(path):
        return False
    os.remove(path)
    return True


# ── Generation ───────────────────────────────────────────────────────────────


def _region_brief(region_id: str) -> str:
    """The region's research brief (the same one the curated personas were researched
    from), minus its terminology notes -- region-level texture for a new persona."""
    path = os.path.join(_BRIEFS_DIR, f"{region_id}.md")
    if not os.path.isfile(path):
        return ""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    start = text.find("### 3.3")
    return (text[start:] if start >= 0 else text).strip()[:24000]


_PROFILE_SYSTEM = (
    "You write a composite persona: one ordinary, plausible resident of a specific Karnataka "
    "district, described in the third person, present tense. The persona will later be asked "
    "many different questions, so it must describe a PERSON, not a position on any issue.\n\n"
    "Rules:\n"
    "- Place them concretely in the district and (if given) the taluk/town: real local crops, "
    "industries, institutions, festivals, communities, transport and places from the region brief.\n"
    "- Honour every trait the user fixed (name, age, occupation, community, notes) exactly; choose "
    "the rest so they fit the district.\n"
    "- Do NOT write about why children leave or drop out of school, dropout rates, or how the person "
    "would explain any particular public problem. Describe schooling only as part of their life "
    "(where the children study, what it costs, what the family hopes for). Never say that children (theirs or "
    "anyone's) drop out or leave school, or list what could make them.\n"
    "- Do NOT state which party or candidate they or anyone voted for or supports; civic life is about schemes, "
    "local bodies and officials, not party choice.\n"
    "- No precise statistics unless they are well established; prefer concrete lived detail to numbers.\n"
    "- Their taluk/town MUST lie inside the given district (not a neighbouring one).\n"
    "- Never give them an occupation in `occupations_not_allowed` (any job involving those words).\n"
    "- Make them distinct: choose a first name NOT in `names_in_use` and an occupation clearly "
    "different from every entry in `occupations_in_use`, unless the user fixed those traits. Draw on the "
    "district's real range of livelihoods and communities (Muslim, Christian, Jain, Dalit, Adivasi, "
    "Lingayat, Vokkaliga, Kuruba, fishing, trading and other communities as the district warrants).\n"
    "- Plain prose, no markdown, no citation markers.\n\n"
    'Respond with JSON: {"name": str (first name), "age": int, "occupation": str (<= 6 words), '
    '"community": str (or ""), "place": str (taluk/town, district; <= 6 words), '
    '"definition": str (2 sentences beginning "<Name> is a composite portrait of"), '
    '"topics": {"<key>": str, ...}} with EXACTLY these topic keys, each 150-200 words: '
    + ", ".join(f"{k} ({d})" for k, _, d in TOPICS)
)

_CARD_SYSTEM = (
    "Distil a persona profile into a display card. Use ONLY facts in the profile -- never invent "
    "names, numbers or places. Plain, warm, concrete; no markdown.\n"
    'Respond with JSON: {"name": str, "ageLabel": str, "emoji": str (ONE emoji avatar), '
    '"role": str (<= 6 words), "place": str (<= 6 words), "community": str, '
    '"tagline": str (<= 16 words, third person), '
    '"household": [{"who": str, "emoji": str}] (2-6 OTHER members as stated -- never the persona themself), '
    '"vitals": [{"label": str, "value": str}] (3-4 tiles, only figures stated), '
    '"dayInLife": [{"when": str, "emoji": str, "text": str (<= 18 words)}] (4-5 beats), '
    '"topics": [{"key": str, "label": str, "emoji": str, "headline": str (<= 12 words), '
    '"points": [str, str, str] (each <= 20 words), "stat": {"value": str, "label": str} (optional, '
    'only a number stated in the profile)}] (one per profile topic, same keys and order), '
    '"worries": [str] (4-6 chips, each <= 4 words)}'
)


async def _chat(llm: Any, system: str, user: str, timeout: float = 180.0) -> dict:
    chat = getattr(llm, "_chat_json", None)
    if chat is None:
        raise RuntimeError("this LLM provider cannot generate personas")
    return await chat(system, user, timeout=timeout)


def _s(v: Any) -> str:
    return str(v).strip() if v is not None else ""


def _clean_card(card: dict) -> dict:
    """Keep only the persona fields a card shows -- never study/factor fields -- in exactly the
    shape the UI renders (every list present, every item with its string fields)."""
    out: dict[str, Any] = {
        k: _s(card.get(k)) for k in ("name", "ageLabel", "emoji", "role", "place", "community", "tagline")
    }
    lst = lambda k: [x for x in card.get(k) or [] if isinstance(x, dict)]  # noqa: E731
    out["household"] = [{"who": _s(m.get("who")), "emoji": _s(m.get("emoji")) or "👤"} for m in lst("household") if _s(m.get("who"))]
    out["vitals"] = [{"label": _s(v.get("label")), "value": _s(v.get("value"))} for v in lst("vitals") if _s(v.get("value"))]
    out["dayInLife"] = [
        {"when": _s(b.get("when")), "emoji": _s(b.get("emoji")) or "•", "text": _s(b.get("text"))}
        for b in lst("dayInLife") if _s(b.get("text"))
    ]
    topics = []
    for t in lst("topics"):
        key = _s(t.get("key"))
        if not key:
            continue
        entry: dict[str, Any] = {
            "key": key,
            "label": _s(t.get("label")) or TOPIC_LABELS.get(key, key),
            "emoji": _s(t.get("emoji")) or "•",
            "headline": _s(t.get("headline")),
            "points": [_s(p) for p in t.get("points") or [] if _s(p)][:5],
        }
        stat = t.get("stat")
        if isinstance(stat, dict) and _s(stat.get("value")):
            entry["stat"] = {"value": _s(stat.get("value")), "label": _s(stat.get("label"))}
        topics.append(entry)
    out["topics"] = topics
    out["worries"] = [_s(w) for w in card.get("worries") or [] if _s(w)]
    # The UI draws the persona first in their household; drop them if the model listed them too.
    me = str(out.get("name") or "").strip().lower()
    out["household"] = [
        m for m in out["household"]
        if isinstance(m, dict) and str(m.get("who") or "").strip().lower().split(" (")[0] not in (me, "")
    ]
    return out


async def build_card(llm: Any, record: dict) -> dict:
    profile = {
        "name": record["name"],
        "place": record.get("place"),
        "definition": record["definition"],
        "topics": [{"key": t["key"], "label": t["label"], "profile": t["profile"]} for t in record["topics"]],
    }
    return _clean_card(await _chat(llm, _CARD_SYSTEM, json.dumps(profile, ensure_ascii=False)))


def _names_and_jobs(exclude_id: str | None = None) -> tuple[list[str], list[str]]:
    names, jobs = set(), set()
    for r in all_personas():
        if r["id"] == exclude_id:
            continue
        card = r.get("card") or {}
        if card.get("name"):
            names.add(card["name"])
        if card.get("role"):
            jobs.add(card["role"])
    return sorted(names), sorted(jobs)


def _misplaced(record: dict) -> str | None:
    """Another district named in the persona's place, e.g. a Tumakuru persona living in 'Kolar town'."""
    text = f"{record.get('place') or ''} {(record.get('card') or {}).get('place') or ''}".lower()
    own = record["districtName"].split(" (")[0].lower()
    for d in districts():
        name = d["name"].split(" (")[0].lower()
        if d["districtId"] != record["districtId"] and name not in own and re.search(rf"\b{re.escape(name)}\b", text):
            return d["name"]
    if record["districtId"] == "29-572" and "devanahalli" in text:  # Bengaluru Rural, not Urban
        return "Bengaluru Rural"
    return None


async def generate(llm: Any, *, district_id: str, gender: str, traits: dict | None = None, provider: str | None = None, replacing: str | None = None, banned_occupations: list[str] | None = None) -> dict:
    """A draft persona for (district, gender): profile text, then a card distilled from it.
    Not saved -- the caller saves it (save_generated / save_custom) once it is reviewed."""
    district = district_by_id().get(district_id)
    if not district:
        raise ValueError(f"unknown district {district_id!r}")
    if gender not in GENDERS:
        raise ValueError("gender must be 'male' or 'female'")
    traits = {k: str(v).strip() for k, v in (traits or {}).items() if v is not None and str(v).strip()}
    region = region_by_id()[district["regionId"]]
    others = [
        f"{p['name']} ({p.get('place') or p['districtName']})"
        for p in (summary(r) for r in all_personas())
        if p["regionId"] == district["regionId"] and p["name"]
    ]
    user = {
        "district": district["name"],
        "region": region["name"],
        "region_definition": region.get("definition", ""),
        "gender": gender,
        "fixed_traits": traits,
        "avoid_duplicating": others,  # personas already in this region -- vary the occupation and community
        "names_in_use": _names_and_jobs(replacing)[0],
        "occupations_in_use": _names_and_jobs(replacing)[1],
        "occupations_not_allowed": banned_occupations or [],  # families already used enough elsewhere
        "region_brief": _region_brief(district["regionId"]),
    }
    raw = await _chat(llm, _PROFILE_SYSTEM, json.dumps(user, ensure_ascii=False))
    topics_raw = raw.get("topics") if isinstance(raw.get("topics"), dict) else {}
    record = {
        "districtId": district_id,
        "gender": gender,
        "name": str(raw.get("name") or traits.get("name") or "").strip(),
        "place": str(raw.get("place") or "").strip(),
        "definition": str(raw.get("definition") or "").strip(),
        "topics": [{"key": k, "label": TOPIC_LABELS[k], "profile": str(topics_raw.get(k) or "").strip()} for k in TOPIC_KEYS],
        "traits": {
            **traits,
            "age": str(raw.get("age") or traits.get("age") or ""),
            "occupation": str(raw.get("occupation") or traits.get("occupation") or ""),
            "community": str(raw.get("community") or traits.get("community") or ""),
        },
        "provider": provider,
    }
    record = _clean_record(record)
    wrong = _misplaced(record)
    if wrong:
        raise ValueError(f"placed in {wrong}, not {district['name']}: {record['place']!r}")
    record["card"] = await build_card(llm, record)
    record["source"] = "draft"
    record["id"] = "draft"
    record["version"] = persona_version(record)
    return record


# ── Asking: the same question with and without the persona ───────────────────


def district_evidence(district_id: str) -> dict | None:
    """The district's research file, trimmed to what an answer can cite. This is the
    data side -- handed identically to both answers, never written into the persona."""
    path = os.path.join(DATA_DIR, "district_research", f"{district_id}.json")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    return {
        "district": d.get("name"),
        "about": "Media and official-source research on secondary-school dropout in this district.",
        "headline": d.get("headline"),
        "summary": d.get("summary"),
        "reasons": [
            {"factor": r.get("factor"), "detail": r.get("detail"), "evidence": r.get("evidence")}
            for r in d.get("reasons") or []
        ],
        "keyFacts": [{"label": k.get("label"), "value": k.get("value")} for k in d.get("keyFacts") or []],
    }


# Two key points count as "the same point" at or above this cosine similarity (all-MiniLM-L6-v2):
# paraphrases of one reason land around 0.5-0.6, different reasons on one topic around 0.2-0.4.
_POINT_MATCH = 0.45

_ASK_TASK = (
    "Answer the user's question about Karnataka, India. {evidence_rule} If you do not know, say "
    "less rather than inventing.\n"
    "Focus on the everyday problems behind the issue -- what families actually run into -- and on what the "
    "government could practically do about them (services, schemes, staff, facilities, timing, money). Use numbers "
    "sparingly: at most two, and only where they make a point; never list rankings or percentages for their own "
    "sake. If the data says the district does well, still say what goes wrong for the families who are left behind.\n"
    "If you have been given a person to speak as, answer in the first person as that person: talk about your own "
    "household, work, neighbours and village or town as described, the problems you or people around you face that "
    "connect to this issue, and what you would want the government to do for you -- specific help, not slogans. Do "
    "not invent family members or facts beyond your description; where the issue does not touch your own home, "
    "speak about relatives or neighbours you would plausibly know. Do not recite statistics like a report.\n"
    'Respond with JSON: {{"answer": str (130-190 words, plain prose), "points": [str] (3-5 distinct '
    'key points, each <= 25 words)}}. Plain text only: no markdown, no URLs.'
)


async def _answer(llm: Any, question: str, persona_prompt: str | None, evidence: dict | None) -> dict:
    rule = (
        "Ground the answer in the supplied `evidence` where it bears on the question."
        if evidence
        else "No evidence is supplied; answer from general knowledge."
    )
    task = _ASK_TASK.format(evidence_rule=rule)
    system = f"{persona_prompt}\n\n{task}" if persona_prompt else task
    payload: dict = {"question": question}
    if evidence:
        payload["evidence"] = evidence
    data = await _chat(llm, system, json.dumps(payload, ensure_ascii=False), timeout=120.0)
    answer = str(data.get("answer") or "").strip()
    points = [str(p).strip() for p in data.get("points") or [] if str(p).strip()][:6]
    if not answer:
        raise ValueError("empty answer")
    return {"answer": answer, "points": points}


TOPICS_EVIDENCE = ("dropout", "stunting")


def topic_evidence(topic: str, district_id: str) -> dict | None:
    """The data side for one study topic -- never part of the persona, only handed to answers."""
    if topic == "stunting":
        from .stunting import district_evidence as stunting_evidence

        return stunting_evidence(district_id)
    return district_evidence(district_id)


async def ask(llm: Any, record: dict, question: str, *, use_evidence: bool, topic: str = "dropout") -> dict:
    """One question, answered twice with identical evidence: once plainly, once as the persona."""
    from .connectors.llm import _local_semantic_embed

    evidence = topic_evidence(topic, record["districtId"]) if use_evidence else None
    generic, persona = await asyncio.gather(
        _answer(llm, question, None, evidence),
        _answer(llm, question, build_prompt(record), evidence),
    )

    similarity: float | None = None
    added: list[str] = []
    dropped: list[str] = []
    try:
        texts = [generic["answer"], persona["answer"], *generic["points"], *persona["points"]]
        vecs = await _local_semantic_embed(texts)
        import numpy as np

        m = np.asarray(vecs, dtype=float)
        m = m / np.maximum(np.linalg.norm(m, axis=1, keepdims=True), 1e-9)
        similarity = round(float(m[0] @ m[1]), 3)
        g = m[2 : 2 + len(generic["points"])]
        p = m[2 + len(generic["points"]) :]
        if len(g) and len(p):
            sims = p @ g.T
            added = [persona["points"][i] for i in range(len(p)) if sims[i].max() < _POINT_MATCH]
            dropped = [generic["points"][j] for j in range(len(g)) if sims[:, j].max() < _POINT_MATCH]
    except Exception as exc:  # noqa: BLE001 -- the answers are still worth returning
        print(f"[persona_library] similarity failed: {exc}", flush=True)

    return {
        "question": question,
        "personaId": record["id"],
        "personaVersion": persona_version(record),
        "evidence": {"used": bool(evidence), "district": record.get("districtName"), "topic": topic},
        "generic": generic,
        "persona": persona,
        "similarity": similarity,
        "onlyWithPersona": added,
        "onlyWithout": dropped,
    }
