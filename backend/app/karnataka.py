"""
Karnataka's four persona regions -- the fixed geographic unit the Story View
pipeline now works in (not districts, not agent-inferred regions).

Single source of truth: data/karnataka_regions.json (region -> district
membership, identity colour, search terms, name aliases, and a town/alt-
spelling lexicon mapping to districts) plus data/personas/*.json (the
user-supplied regional persona descriptions). public/geo/karnataka-regions.geojson
is generated FROM the same membership by data/build_karnataka_regions_geo.py.

Every one of the map's 30 Karnataka districts belongs to exactly one region
(Uttara Kannada -> Karavali; the seven districts no persona names are folded
into the nearest region -- see the JSON). Posts that are about Karnataka but
not any one region land in the non-persona STATEWIDE bucket.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from functools import lru_cache
from typing import TypedDict

from .config import DATA_DIR

_REGISTRY_PATH = os.path.join(DATA_DIR, "karnataka_regions.json")
_NORMALIZE_RE = re.compile(r"[^a-z0-9]+")


def normalize_place(name: str) -> str:
    """Mirrors build_gazetteer.normalize, so lookups land on the gazetteer's own keys."""
    return _NORMALIZE_RE.sub(" ", name.lower()).strip()


class RegionSpec(TypedDict):
    id: str
    name: str
    short_name: str
    persona_file: str
    color: list[int]
    search_terms: str
    district_ids: list[str]
    aliases: list[str]


@lru_cache(maxsize=1)
def _registry() -> dict:
    with open(_REGISTRY_PATH, encoding="utf-8") as f:
        return json.load(f)


def karnataka_state_code() -> str:
    return _registry()["state_code"]


def statewide_region_id() -> str:
    return _registry()["statewide_region_id"]


def statewide_region_name() -> str:
    return _registry()["statewide_region_name"]


def persona_regions() -> list[RegionSpec]:
    return list(_registry()["regions"])


@lru_cache(maxsize=1)
def region_by_id() -> dict[str, RegionSpec]:
    return {r["id"]: r for r in persona_regions()}


@lru_cache(maxsize=1)
def region_of_district() -> dict[str, str]:
    return {d: r["id"] for r in persona_regions() for d in r["district_ids"]}


@lru_cache(maxsize=1)
def _alias_patterns() -> list[tuple[re.Pattern[str], str]]:
    """Region-name aliases ("Malnad", "Kalyana Karnataka", "Tulu Nadu"...),
    longest first so "north karnataka" wins over a shorter overlapping alias."""
    pairs = [(normalize_place(a), r["id"]) for r in persona_regions() for a in r["aliases"]]
    pairs.sort(key=lambda p: len(p[0]), reverse=True)
    return [(re.compile(rf"\b{re.escape(a)}\b"), rid) for a, rid in pairs]


def region_from_alias(text: str) -> str | None:
    """A region explicitly named in `text` (a place mention or a whole post)."""
    norm = normalize_place(text)
    for pattern, rid in _alias_patterns():
        if pattern.search(norm):
            return rid
    return None


def load_karnataka_gazetteer(base_gazetteer: dict) -> dict:
    """The India-wide district gazetteer, augmented with Karnataka towns/taluks
    and alternate spellings (Mangaluru, Manipal, Hubballi, Coorg...) that the
    district-name-only gazetteer can't resolve, and with the bare "karnataka"
    key REMOVED -- it maps to arbitrary representative districts (Bidar,
    Kalaburagi), which would misattribute every statewide mention to North
    Karnataka. A Karnataka-only mention is handled as statewide instead
    (see graph/nodes/resolve_regions.py)."""
    gazetteer = {k: v for k, v in base_gazetteer.items() if k != "karnataka"}
    by_id: dict[str, dict] = {}
    for candidates in base_gazetteer.values():
        for cand in candidates:
            if cand.get("districtId") and cand["districtId"] not in by_id:
                by_id[cand["districtId"]] = cand
    for alias, district_id in _registry()["place_aliases"].items():
        cand = by_id.get(district_id)
        key = normalize_place(alias)
        if cand and key not in gazetteer:
            gazetteer[key] = [cand]
    return gazetteer


# ── Personas ────────────────────────────────────────────────────────────────


@lru_cache(maxsize=None)
def load_persona(region_id: str) -> dict:
    spec = region_by_id()[region_id]
    with open(os.path.join(DATA_DIR, spec["persona_file"]), encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=None)
def build_persona_prompt(region_id: str) -> str:
    """Deterministic persona text built from the region's description file.
    Deterministic on purpose: divergence is measured against a no-persona
    reply, so the persona itself must not vary from run to run."""
    persona = load_persona(region_id)
    topics = persona.get("topics") or {}
    sections = []
    for topic in topics.values():
        label = topic.get("topic_label") or ""
        profile = (topic.get("regional_profile") or "").strip()
        if profile:
            sections.append(f"## {label}\n{profile}")
    profile_text = "\n\n".join(sections)
    return (
        f"PERSONA -- you speak for the people of Karnataka's {persona['region_name']}.\n"
        f"Who you represent: {persona['region_definition']}\n\n"
        "Answer as this region would: from its own priorities, constraints, lived experience and "
        "history, emphasising what people here would emphasise and naming the local places, "
        "institutions, crops, industries and disputes that matter to them. Use the regional "
        "profile below only where it genuinely bears on the question -- never recite it -- and "
        "never invent statistics beyond it and the supplied evidence.\n\n"
        f"REGIONAL PROFILE\n\n{profile_text}"
    )


def persona_version(region_id: str) -> str:
    """Short content hash of the built persona -- shown with divergence results
    so a score can always be traced to the exact persona text that produced it."""
    return hashlib.sha256(build_persona_prompt(region_id).encode("utf-8")).hexdigest()[:10]


def persona_payload(region_id: str) -> dict:
    """Wire/UI shape for /api/personas."""
    persona = load_persona(region_id)
    spec = region_by_id()[region_id]
    return {
        "regionId": region_id,
        "name": persona["region_name"],
        "shortName": spec["short_name"],
        "definition": persona["region_definition"],
        "version": persona_version(region_id),
        "topics": [
            {
                "key": key,
                "label": t.get("topic_label") or key,
                "profile": t.get("regional_profile") or "",
                "sources": [
                    {"title": s.get("title") or "", "url": s.get("url") or "", "year": s.get("year")}
                    for s in (t.get("sources") or [])
                ],
            }
            for key, t in (persona.get("topics") or {}).items()
        ],
    }
