"""
Turn the authored deep-research data (responses/converted_data_*.py) into schema-valid
district JSON in responses/converted/<districtId>.json -- and VERIFY it on the way.

For every cited page this script downloads the page text and then:
  * fact / headline / reason / response  -> kept only if the page names the district
    (or a known alias) -- statewide lists are not allowed to pose as district evidence.
    Facts labelled "Statewide:" skip that test.
  * every number in a fact's value      -> must appear on at least one cited page.
Anything failing is DROPPED and recorded in `verificationNotes`.
Source titles, dates and outlets come from the live pages, not from the report.

    python3 build_converted.py            # build + print the verification report
"""

from __future__ import annotations

import concurrent.futures
import html
import importlib.util
import json
import os
import re
import urllib.request
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
RESP = os.path.join(HERE, "responses")
OUT = os.path.join(RESP, "converted")
CACHE = os.path.join(RESP, ".page_cache")
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))

ALIASES = {
    "Dakshina Kannada": ["dakshina kannada", "mangaluru", "mangalore", "south canara"],
    "Udupi": ["udupi"],
    "Uttara Kannada": ["uttara kannada", "uttar kannada", "sirsi", "karwar"],
    "Belagavi": ["belagavi", "belgaum"],
    "Vijayapura": ["vijayapura", "bijapur"],
    "Bagalkote": ["bagalkot", "bagalkote"],
    "Dharwad": ["dharwad"],
    "Gadag": ["gadag"],
    "Haveri": ["haveri"],
    "Kalaburagi": ["kalaburagi", "gulbarga", "kalburgi"],
    "Bidar": ["bidar"],
    "Yadgir": ["yadgir", "yadagiri"],
    "Raichur": ["raichur"],
    "Koppal": ["koppal"],
    "Ballari (incl. Vijayanagara)": ["ballari", "bellary", "vijayanagara", "hospet"],
    "Bengaluru Urban": ["bengaluru", "bangalore"],
    "Bengaluru Rural": ["bengaluru rural", "bangalore rural", "bengaluru", "bangalore"],
    "Ramanagara": ["ramanagara", "ramanagar", "channapatna", "kanakapura"],
    "Mandya": ["mandya"],
    "Mysuru": ["mysuru", "mysore"],
    "Chamarajanagara": ["chamarajanagar", "chamarajanagara", "chamrajnagar"],
    "Chikkaballapur": ["chikkaballapur", "chikballapur", "chickballapur", "chikkaballapura"],
    "Kolar": ["kolar", "kgf"],
    "Tumakuru": ["tumakuru", "tumkur", "madhugiri"],
    "Davanagere": ["davanagere", "davangere"],
    "Chitradurga": ["chitradurga"],
    "Shivamogga": ["shivamogga", "shimoga"],
    "Chikkamagaluru": ["chikkamagaluru", "chikmagalur", "chikkamagalur"],
    "Kodagu": ["kodagu", "coorg", "madikeri"],
    "Hassan": ["hassan"],
}
OUTLETS = {
    "thehindu.com": "The Hindu", "timesofindia.indiatimes.com": "The Times of India", "daijiworld.com": "Daijiworld",
    "deccanherald.com": "Deccan Herald", "newindianexpress.com": "The New Indian Express", "newsbharati.com": "News Bharati",
    "bangaloremirror.indiatimes.com": "Bangalore Mirror", "business-standard.com": "Business Standard",
    "careerindia.com": "Careerindia", "collegedekho.com": "CollegeDekho", "schoolserv.in": "SchoolServ",
    "ijcmas.com": "Int. J. Curr. Microbiol. App. Sci.", "publications.azimpremjiuniversity.edu.in": "Azim Premji University",
    "organiser.org": "Organiser",
}
RESEARCH_HOSTS = ("ijcmas.com", "azimpremjiuniversity.edu.in")


def load(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fetch(url: str) -> str:
    os.makedirs(CACHE, exist_ok=True)
    key = re.sub(r"\W+", "_", url)[-150:]
    path = os.path.join(CACHE, key)
    if os.path.isfile(path):
        return open(path, encoding="utf-8").read()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research-verify)"})
        body = urllib.request.urlopen(req, timeout=30).read(900000).decode("utf-8", "ignore")
    except Exception:  # noqa: BLE001
        body = ""
    open(path, "w", encoding="utf-8").write(body)
    return body


def page_text(raw: str) -> str:
    raw = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw, flags=re.S | re.I)
    t = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    t = re.sub(r"(?<=\d),(?=\d)", "", t)  # 11,137 -> 11137
    return re.sub(r"\s+", " ", t).lower()


def page_meta(raw: str, fallback_title: str) -> tuple[str, str]:
    og = re.search(r'property=["\']og:title["\']\s+content=["\']([^"\']+)', raw)
    t = re.search(r"<title[^>]*>(.*?)</title>", raw, re.S | re.I)
    title = html.unescape((og.group(1) if og else (t.group(1) if t else "")).strip()) or fallback_title
    title = re.sub(r"\s*[|\-–]\s*(The Hindu|Deccan Herald|Times of India|Bengaluru News|Mysuru News|Bangalore Mirror).*$", "", title).strip()
    date = ""
    for pat in (r'article:published_time["\']\s+content=["\']([^"\']+)', r'"datePublished"\s*:\s*"([^"]+)"',
                r'itemprop=["\']datePublished["\']\s+content=["\']([^"\']+)'):
        m = re.search(pat, raw)
        if m:
            date = m.group(1)[:10]
            break
    if not date:
        m = re.search(r"Published\s*-\s*([A-Z][a-z]+ \d{1,2}, \d{4})", raw)
        if m:
            import datetime

            try:
                date = datetime.datetime.strptime(m.group(1), "%B %d, %Y").strftime("%Y-%m-%d")
            except ValueError:
                date = ""
    return title[:200], date


NUMWORDS = {"1": "one", "2": "two", "3": "three", "4": "four", "5": "five", "6": "six", "7": "seven", "8": "eight",
            "9": "nine", "10": "ten", "11": "eleven", "12": "twelve", "13": "thirteen", "15": "fifteen", "20": "twenty"}


def numbers(value: str) -> list[str]:
    out = []
    for n in re.findall(r"\d[\d,]*\.?\d*", value):
        n = n.replace(",", "").rstrip(".")
        if n:
            out.append(n)
    return out


def build_set(mod, sources: dict, backend: dict[str, dict], report: list[str]) -> None:
    cites_needed = set()
    for d in mod.DISTRICTS:
        for r in d["reasons"]:
            cites_needed |= set(r[3])
        for f in d["facts"]:
            cites_needed |= set(f[2])
        for h in d["heads"]:
            cites_needed.add(h[0])
        for x in d["resp"]:
            cites_needed |= set(x[1])
        for c in d["checks"]:
            cites_needed |= set(c[3])
    urls = {n: sources[str(n)]["url"] for n in cites_needed}
    with concurrent.futures.ThreadPoolExecutor(8) as pool:
        raws = dict(zip(urls, pool.map(fetch, urls.values())))
    texts = {n: page_text(raws[n]) for n in urls}

    for d in mod.DISTRICTS:
        al = ALIASES[d["name"]]
        notes: list[str] = []

        weak: list[str] = []

        def strength(n: int) -> int:
            """2 = named in title/URL or 2+ times in the body; 1 = named once; 0 = not named."""
            head = (sources[str(n)]["title"] + " " + urls[n]).lower().replace("%20", " ")
            if any(a in head for a in al):
                return 2
            c = sum(texts[n].count(a) for a in al)
            return 2 if c >= 2 else c

        def names(n: int) -> bool:
            return bool(texts[n]) and strength(n) >= 1

        def has_all(n: int, value: str) -> bool:
            """Every number appears on the page, each within 300 characters of a district name
            (or the district is in the title/URL)."""
            t = texts[n]
            head = (sources[str(n)]["title"] + " " + urls[n]).lower().replace("%20", " ")
            titled = any(a in head for a in al)
            for num in numbers(value):
                pat = re.escape(num) if num not in NUMWORDS else f"(?:{re.escape(num)}|{NUMWORDS[num]})"
                spots = [m.start() for m in re.finditer(r"(?<![\d.])" + pat + r"(?![\d])", t)]
                if not spots:
                    return False
                if titled:
                    continue
                alias_spots = [m.start() for a in al for m in re.finditer(re.escape(a), t)]
                if not any(abs(sp - ap) <= 300 for sp in spots for ap in alias_spots):
                    return False
            return True

        reasons, facts, heads, resp = [], [], [], []
        for factor, cat, detail, cites, ev in d["reasons"]:
            ok = [c for c in cites if texts[c] and names(c)]
            if not ok:
                notes.append(f"Dropped reason '{factor}': cited page(s) do not name the district.")
                continue
            if all(strength(c) == 1 for c in ok):
                weak.append(f"reason '{factor}' (cites {ok}) -- district named only once")
            reasons.append(dict(factor=factor, category=cat, detail=detail, sources=ok, evidence=ev))
        for fact in d["facts"]:
            label, value, cites = fact[:3]
            manual = len(fact) > 3 and fact[3] == "manual"
            statewide = label.lower().startswith("statewide")
            loose = lambda c: all(num in texts[c] or NUMWORDS.get(num, "~") in texts[c] for num in numbers(value))  # noqa: E731
            good = [c for c in cites if texts[c] and (loose(c) and (statewide or (manual and names(c))) if (statewide or manual) else has_all(c, value))]
            if numbers(value) and not good:
                notes.append(f"Dropped fact '{label}': figure not confirmed on a cited page that names the district.")
                continue
            if not numbers(value):
                good = [c for c in cites if texts[c] and (statewide or names(c))]
                if not good:
                    notes.append(f"Dropped fact '{label}': cited page does not name the district.")
                    continue
            facts.append(dict(label=label, value=value, sources=good))
        for cite, take in d["heads"]:
            if texts[cite] and names(cite):
                heads.append((cite, take))
                if strength(cite) == 1:
                    weak.append(f"news item cite {cite} -- district named only once")
            else:
                notes.append(f"Dropped news item (cite {cite}): page does not name the district.")
        for text, cites in d["resp"]:
            ok = [c for c in cites if texts[c] and names(c)]
            if ok:
                resp.append(dict(text=text, sources=ok))
            else:
                notes.append("Dropped a response item: cited page does not name the district.")

        used = []
        def use(n):
            if n not in used:
                used.append(n)
            return used.index(n) + 1

        for r in reasons:
            r["sources"] = [use(c) for c in r["sources"]]
        for f in facts:
            f["sources"] = [use(c) for c in f["sources"]]
        for x in resp:
            x["sources"] = [use(c) for c in x["sources"]]
        head_rows = []
        for cite, take in heads:
            use(cite)
        sources_out = []
        for n in used:
            host = urlparse(urls[n]).netloc.lower().removeprefix("www.")
            title, date = page_meta(raws[n], sources[str(n)]["title"])
            sources_out.append(dict(
                id=used.index(n) + 1, url=urls[n], title=title,
                outlet=next((v for k, v in OUTLETS.items() if host.endswith(k)), host),
                date=date, type="research" if host.endswith(RESEARCH_HOSTS) else "news",
            ))
        for cite, take in heads:
            s = sources_out[used.index(cite)]
            head_rows.append(dict(title=s["title"], outlet=s["outlet"], date=s["date"], url=s["url"], takeaway=take))
        head_rows.sort(key=lambda h: h["date"], reverse=True)

        rows = backend.get(d["id"], {}).get("nitiFactors", [])
        checks = []
        for method, verdict, note, cites in d["checks"]:
            mrows = [r for r in rows if r["method"] == method]
            if not mrows:
                continue
            row = next((r for r in mrows if r["area"].lower().startswith(d["name"].split(" (")[0].lower())), mrows[0])
            ids = []
            for c in cites:
                if texts.get(c):
                    ids.append(use(c) if c in used else None)
            if any(c not in used for c in cites if texts.get(c)):
                for c in cites:
                    if texts.get(c) and c not in used:
                        use(c)
                        host = urlparse(urls[c]).netloc.lower().removeprefix("www.")
                        title, date = page_meta(raws[c], sources[str(c)]["title"])
                        sources_out.append(dict(id=len(sources_out) + 1, url=urls[c], title=title,
                                                outlet=next((v for k, v in OUTLETS.items() if host.endswith(k)), host),
                                                date=date, type="news"))
            checks.append(dict(factor=row["factor"], method=method, verdict=verdict, note=note,
                               sources=[used.index(c) + 1 for c in cites if texts.get(c) and c in used]))

        coverage = "moderate" if len(reasons) >= 3 and len(sources_out) >= 5 else "thin"
        out = dict(
            districtId=d["id"], name=d["name"], regionId=d["region"], researchedOn="2026-10-07",
            headline=d["headline"], summary=d["summary"], reasons=reasons, keyFacts=facts,
            headlines=head_rows, responses=resp, officialFactorCheck=checks, sources=sources_out,
            coverage=coverage, gaps=d["gaps"],
            verificationNotes=" ".join(notes) if notes else "All kept figures and attributions were confirmed on the cited pages.",
        )
        os.makedirs(OUT, exist_ok=True)
        json.dump(out, open(os.path.join(OUT, f"{d['id']}.json"), "w", encoding="utf-8"), indent=2, ensure_ascii=False)
        report.append(f"{d['id']} {d['name']:28} reasons {len(reasons)}/{len(d['reasons'])} facts {len(facts)}/{len(d['facts'])} "
                      f"news {len(head_rows)}/{len(d['heads'])} sources {len(sources_out)}")
        for n in notes:
            report.append("      - " + n)
        for w in weak:
            report.append("      ? WEAK " + w)


def main() -> None:
    cache = os.path.join(RESP, ".backend_districts.json")
    try:
        with urllib.request.urlopen("http://localhost:8001/api/karnataka/districts", timeout=30) as r:
            payload = json.load(r)
        json.dump(payload, open(cache, "w"))
    except Exception:  # noqa: BLE001 -- backend down: reuse the last copy
        payload = json.load(open(cache))
    backend = {d["districtId"]: d for d in payload["districts"]}
    report: list[str] = []
    for fname, srcname in (("converted_data_coast_north.py", "set-coast-north"), ("converted_data_south_central.py", "set-south-central")):
        mod = load(os.path.join(RESP, fname), fname[:-3])
        sources = json.load(open(os.path.join(RESP, f"{srcname}.sources.json")))
        build_set(mod, sources, backend, report)
    print("\n".join(report))


if __name__ == "__main__":
    main()
