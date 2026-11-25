"""
Import District Mocha's Karnataka district profiles (https://district-mocha.netlify.app/) as background context for
each district: baseline figures, strengths, challenges, opportunities, goals, programmes, industries and role-based
actions. It is outside context, not our research: an AI-assisted project by another team, with no per-figure
citations, so the UI and the chat label it that way and link every profile to its page.

    python3 scripts/import_district_mocha.py ../district-mocha/district-mocha.json

Input is the full-site scrape (district-mocha/scraper/parse.py). Output: backend/app/data/district_mocha/karnataka.json,
keyed by our district ids. Vijayanagara has its own page but shares Ballari's map polygon, so it is attached to
Ballari as a second profile.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "backend", "app", "data", "district_mocha", "karnataka.json")
IDS = os.path.join(ROOT, "backend", "app", "data", "niti", "stunting", "district_ids.json")
SITE = "https://district-mocha.netlify.app/"

# District Mocha's spelling -> ours (district_ids.json)
ALIAS = {
    "Chamarajanagar": "Chamarajanagara",
    "Chikmagalur": "Chikkamangaluru",
    "Kalaburagi": "Kalburgi",
    "Yadgir": "Yadagiri",
    "Vijayanagara": "Ballari",
}


def leaves(x, out: dict[str, list], links: list) -> None:
    """Every leaf string under x, grouped by its key; links collected separately."""
    if isinstance(x, dict):
        if "href" in x and "text" in x and isinstance(x["text"], str):
            links.append({"text": x["text"], "href": x["href"]})
        for k, v in x.items():
            if k in ("href", "arrow", "_data", "data"):
                continue
            if isinstance(v, str):
                out.setdefault(k, []).append(v)
            else:
                leaves(v, out, links)
    elif isinstance(x, list):
        for v in x:
            leaves(v, out, links)


def items(body) -> list[dict]:
    """A card body as a list of {key: text} items."""
    rows = body if isinstance(body, list) else None
    if rows is None and isinstance(body, dict):
        rows = next((v for v in body.values() if isinstance(v, list)), [body])
    res = []
    for r in rows or []:
        f: dict[str, list] = {}
        links: list = []
        leaves(r, f, links)
        row = {k: " ".join(v) for k, v in f.items()}
        if links:
            row["links"] = links
        if row:
            res.append(row)
    return res


def cards(x, acc: list) -> list:
    if isinstance(x, dict):
        if isinstance(x.get("head"), str) and "body" in x:
            acc.append((x["head"], x["body"]))
        for v in x.values():
            cards(v, acc)
    elif isinstance(x, list):
        for v in x:
            cards(v, acc)
    return acc


def baseline(content) -> list[dict]:
    found: list[dict] = []

    def walk(x):
        if isinstance(x, dict):
            if "val" in x and ("meta" in x or "label" in x):
                meta = x.get("meta") if isinstance(x.get("meta"), dict) else x
                found.append({"label": meta.get("label", ""), "value": x["val"], "year": meta.get("year", ""),
                              "note": x.get("delta", "")})
                return
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(content)
    seen, out = set(), []
    for b in found:
        if b["label"] not in seen:
            seen.add(b["label"])
            out.append(b)
    return out


def profile(page: dict) -> dict:
    p: dict = {
        "name": page["header"].get("title") or page["title"],
        "tagline": page["header"].get("sub", ""),
        "region": re.sub(r"(\s*Region)?\s*·\s*Karnataka$", "", page["header"].get("eyebrow", "")).strip(),
        "url": page["url"],
        "baseline": baseline(page["content"]),
        "strengths": [], "challenges": [], "opportunities": [], "goals": [], "programmes": [], "industries": [],
        "roles": [], "linked": [],
    }
    for head, body in cards(page["content"], []):
        rows = items(body)
        h = head.lower()
        if h == "strengths" or h == "challenges" or h == "opportunities":
            p[h] = [{"title": r.get("title", ""), "detail": r.get("desc", "")} for r in rows]
        elif h == "goals":
            p["goals"] = [{"target": r.get("target", ""), "detail": r.get("desc", "")} for r in rows]
        elif h == "core programs":
            p["programmes"] = [{"name": r.get("name", ""), "status": r.get("status", "")} for r in rows]
        elif h.startswith("4 industries") or "industries" in h:
            p["industriesTitle"] = head
            p["industries"] = [{"name": r.get("name", ""), "priority": r.get("badge", ""),
                                "stats": r.get("stats", ""), "note": r.get("note", "")} for r in rows]
        elif h == "role-based actions":
            p["roles"] = [{"role": r.get("name", ""), "action": r.get("action", "")} for r in rows]
        elif "—" in head:  # Gram Kaapi / Re Gen / City Latte link cards
            for r in rows:
                link = (r.get("links") or [{}])[0]
                href = link.get("href", "")
                p["linked"].append({"kind": head.split("—", 1)[1].strip(), "name": r.get("name") or link.get("text", ""),
                                    "summary": r.get("action", ""),
                                    "url": href if href.startswith("http") else SITE + href if href else ""})
    return p


def main() -> None:
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "..", "district-mocha", "district-mocha.json")
    with open(src, encoding="utf-8") as fh:
        site = json.load(fh)
    with open(IDS, encoding="utf-8") as fh:
        ids: dict[str, str] = json.load(fh)["districts"]
    pages = [p for p in site["pages"] if p["path"].startswith("karnataka/") and p["type"] == "district"]
    districts: dict[str, dict] = {}
    unmatched = []
    for page in sorted(pages, key=lambda p: p["path"]):
        prof = profile(page)
        ours = ALIAS.get(prof["name"], prof["name"])
        did = ids.get(ours)
        if not did:
            unmatched.append(prof["name"])
            continue
        if did in districts:  # Vijayanagara under Ballari
            districts[did].setdefault("also", []).append(prof)
        else:
            districts[did] = {"districtId": did, **prof}
    if unmatched:
        sys.exit(f"no district id for: {unmatched}")
    out = {
        "source": {
            "name": "District Mocha, City Latte (Public A.I.)",
            "url": SITE + "india.html",
            "about": "An AI-assisted development-dashboard project by another team, covering every Karnataka "
                     "district: baseline figures, strengths, challenges, opportunities, goals, programmes and actions. "
                     "Figures are as published there, without per-figure citations, and were not checked by this study.",
            "importedOn": datetime.date.today().isoformat(),
            "scrapedOn": site.get("scrapedOn"),
        },
        "districts": dict(sorted(districts.items())),
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    missing = sorted(set(ids.values()) - set(districts))
    print(f"wrote {len(districts)} districts to {os.path.relpath(OUT, ROOT)}; missing: {missing or 'none'}")


if __name__ == "__main__":
    main()
