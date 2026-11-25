"""
Collect and verify media / official research on under-5 stunting for each Karnataka district -- the stunting
counterpart of the dropout district research (backend/app/data/district_research/), done in the repo instead of
by hand-pasted deep-research prompts.

    cd backend
    .venv/bin/python ../scripts/research_stunting_districts.py --district 29-559      # one district
    .venv/bin/python ../scripts/research_stunting_districts.py --all                  # every district
    .venv/bin/python ../scripts/research_stunting_districts.py --all --skip-existing

Per district:
  1. Web search (Claude's server-side web search tool, on the Azure deployment): stunting / malnutrition / anaemia / anganwadi queries, plus one query per
     factor the NITI stunting model prescribes most change for (backend/app/stunting.py, default settings).
  2. Fetch every result page; keep only pages that name the district (or a known alias) AND talk about child
     nutrition. Nothing else can be cited.
  3. Claude compiles the district file (same shape as the dropout files, see SCHEMA.md there) citing only those
     pages, plus `modelFactorWhy`: for each top prescribed factor, whether local evidence says why it matters here.
  4. Verification, as for dropout: every number in a claim must appear on a cited page AND be attributable to the
     district (the page is about it -- named in title/URL -- or the number sits next to a mention of it); a claim with no
     surviving source is dropped; titles / dates / outlets come from the live page. Everything dropped is listed
     in `verificationNotes`. Verdicts are made consistent with what survived.

Output: backend/app/data/district_research_stunting/<districtId>.json
Pages are cached in docs/stunting-research/.page_cache/ (git-ignored).
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import html
import json
import os
import re
import sys
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import httpx  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.connectors.llm import get_llm_client  # noqa: E402
from app.persona_library import district_by_id, districts  # noqa: E402
from app.stunting import model  # noqa: E402

OUT = os.path.join(ROOT, "backend", "app", "data", "district_research_stunting")
CACHE = os.path.join(ROOT, "docs", "stunting-research", ".page_cache")

ALIASES = {
    "Dakshina Kannada": ["dakshina kannada", "mangaluru", "mangalore", "south canara"],
    "Udupi": ["udupi"],
    "Uttara Kannada": ["uttara kannada", "uttar kannada", "karwar", "sirsi"],
    "Belagavi": ["belagavi", "belgaum"],
    "Vijayapura": ["vijayapura", "bijapur"],
    "Bagalkote": ["bagalkot", "bagalkote"],
    "Dharwad": ["dharwad", "hubballi", "hubli"],
    "Gadag": ["gadag"],
    "Haveri": ["haveri"],
    "Kalaburagi": ["kalaburagi", "gulbarga", "kalburgi"],
    "Bidar": ["bidar"],
    "Yadgir": ["yadgir", "yadagiri"],
    "Raichur": ["raichur"],
    "Koppal": ["koppal"],
    "Ballari (incl. Vijayanagara)": ["ballari", "bellary", "vijayanagara", "hosapete", "hospet"],
    "Bengaluru Urban": ["bengaluru urban", "bengaluru", "bangalore"],
    "Bengaluru Rural": ["bengaluru rural", "bangalore rural", "devanahalli", "doddaballapur"],
    "Ramanagara": ["ramanagara", "ramanagar", "channapatna", "kanakapura"],
    "Mandya": ["mandya"],
    "Mysuru": ["mysuru", "mysore"],
    "Chamarajanagara": ["chamarajanagar", "chamarajanagara", "chamrajnagar"],
    "Chikkaballapur": ["chikkaballapur", "chikballapur", "chickballapur", "chikkaballapura"],
    "Kolar": ["kolar"],
    "Tumakuru": ["tumakuru", "tumkur"],
    "Davanagere": ["davanagere", "davangere"],
    "Chitradurga": ["chitradurga"],
    "Shivamogga": ["shivamogga", "shimoga"],
    "Chikkamagaluru": ["chikkamagaluru", "chikmagalur", "chikkamagalur"],
    "Kodagu": ["kodagu", "coorg", "madikeri"],
    "Hassan": ["hassan"],
}
TOPIC_WORDS = re.compile(
    r"stunt|malnutri|malnourish|undernourish|underweight|wasting|anaemi|anemi|nutrition|anganwadi|poshan|"
    r"low birth weight|child marriage|iron.folic|nutrition rehabilitation|\bsam\b|\bmam\b",
    re.I,
)
BLOCKED_HOSTS = ("news.google.", "msn.com", "dailyhunt", "facebook.com", "instagram.com", "youtube.com", "x.com",
                 "twitter.com", "linkedin.com")
OUTLETS = {
    "thehindu.com": "The Hindu", "timesofindia.indiatimes.com": "The Times of India", "deccanherald.com": "Deccan Herald",
    "newindianexpress.com": "The New Indian Express", "thesouthfirst.com": "The South First", "daijiworld.com": "Daijiworld",
    "indianexpress.com": "The Indian Express", "starofmysore.com": "Star of Mysore", "udayavani.com": "Udayavani",
    "prajavani.net": "Prajavani", "vijaykarnataka.com": "Vijay Karnataka", "bangaloremirror.indiatimes.com": "Bangalore Mirror",
    "hindustantimes.com": "Hindustan Times", "downtoearth.org.in": "Down To Earth", "indiaspend.com": "IndiaSpend",
    "scroll.in": "Scroll", "thewire.in": "The Wire", "nfhsiips.in": "IIPS (NFHS)", "rchiips.org": "IIPS (NFHS)",
    "karnataka.gov.in": "Government of Karnataka", "pib.gov.in": "PIB",
}
CATEGORIES = ("nutrition-diet", "maternal-health", "health-services", "water-sanitation", "economic",
              "social-norms", "governance", "other")


def queries(name: str, top_factors: list[str]) -> list[str]:
    q = [
        f"{name} district stunting children Karnataka",
        f"{name} malnutrition children anganwadi",
        f"{name} malnourished children news",
        f"{name} severe acute malnutrition children",
        f"{name} anaemia pregnant women",
        f"{name} NFHS stunting underweight children",
        f"{name} Poshan Abhiyaan nutrition",
        f"{name} child marriage teenage pregnancy",
    ]
    return q + [f"{name} {f}" for f in top_factors]


# ── search (Claude web search tool) ─────────────────────────────────────────


async def claude_search(qs: list[str]) -> dict[str, dict]:
    """Run each query through Claude's web search tool; return {url: {title, page_age}} of every result."""
    from anthropic import AsyncAnthropicFoundry

    settings = get_settings()
    client = AsyncAnthropicFoundry(api_key=settings.azure_anthropic_api_key, base_url=settings.azure_anthropic_endpoint)
    messages: list[dict] = [{
        "role": "user",
        "content": "Run each of these web searches, one search per line, exactly as written, and do nothing else. "
                   "When all are done, reply with the single word: done.\n\n" + "\n".join(qs),
    }]
    found: dict[str, dict] = {}
    for _ in range(4):  # server-side tool loops may pause; continue them
        resp = await client.messages.create(
            model=settings.azure_anthropic_deployment, max_tokens=1500,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": len(qs)}],
            messages=messages,
        )
        for block in resp.content:
            if getattr(block, "type", None) == "web_search_tool_result" and isinstance(block.content, list):
                for r in block.content:
                    url = (getattr(r, "url", "") or "").split("#")[0]
                    if url and url not in found:
                        found[url] = {"title": getattr(r, "title", "") or "", "page_age": getattr(r, "page_age", "") or ""}
        if resp.stop_reason != "pause_turn":
            break
        messages = [*messages, {"role": "assistant", "content": resp.content}]
    return found


# ── pages ────────────────────────────────────────────────────────────────────


def cache_path(url: str) -> str:
    return os.path.join(CACHE, re.sub(r"\W+", "_", url)[-150:])


async def fetch(client: httpx.AsyncClient, url: str) -> str:
    os.makedirs(CACHE, exist_ok=True)
    path = cache_path(url)
    if os.path.isfile(path):
        return open(path, encoding="utf-8").read()
    try:
        r = await client.get(url, timeout=25.0, follow_redirects=True,
                             headers={"User-Agent": "Mozilla/5.0 (research-verify)"})
        ctype = r.headers.get("content-type", "")
        body = r.text[:900000] if r.status_code == 200 and "html" in ctype else ""
    except Exception:  # noqa: BLE001
        body = ""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    return body


def page_text(raw: str) -> str:
    raw = re.sub(r"<(script|style|nav|footer|header)[^>]*>.*?</\1>", " ", raw, flags=re.S | re.I)
    t = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    t = re.sub(r"(?<=\d),(?=\d)", "", t)
    return re.sub(r"\s+", " ", t).strip()


def page_meta(raw: str, url: str) -> tuple[str, str, str]:
    og = re.search(r'property=["\']og:title["\']\s+content=["\']([^"\']+)', raw)
    t = re.search(r"<title[^>]*>(.*?)</title>", raw, re.S | re.I)
    title = html.unescape((og.group(1) if og else (t.group(1) if t else "")).strip())
    title = re.sub(r"\s*[|\-–]\s*[^|\-–]{2,40}$", "", title).strip() or url
    date = ""
    for pat in (r'article:published_time["\']\s+content=["\']([^"\']+)', r'"datePublished"\s*:\s*"([^"]+)"',
                r'itemprop=["\']datePublished["\']\s+content=["\']([^"\']+)'):
        m = re.search(pat, raw)
        if m:
            date = m.group(1)[:10]
            break
    host = urlparse(url).netloc.removeprefix("www.")
    outlet = next((v for k, v in OUTLETS.items() if host.endswith(k)), host)
    return title[:200], date, outlet


def excerpt(text: str, aliases: list[str], limit: int = 1800) -> str:
    """Windows of text around mentions of the district and of child nutrition."""
    low = text.lower()
    hits = sorted({m.start() for a in aliases for m in re.finditer(re.escape(a), low)}
                  | {m.start() for m in TOPIC_WORDS.finditer(text)})
    out, last = [], -10**9
    for h in hits:
        if h - last < 300:
            continue
        out.append(text[max(0, h - 250): h + 350])
        last = h
        if sum(len(x) for x in out) > limit:
            break
    return " … ".join(out)[:limit]


def numbers(s: str) -> list[str]:
    return [n.replace(",", "").rstrip(".") for n in re.findall(r"\d[\d,]*\.?\d*", s or "") if n.strip(".")]


ATTRIBUTION_WINDOW = 350  # characters


def attributed(n: str, page: dict, text: str, aliases: list[str]) -> bool:
    """The number is this district's: it is on a page ABOUT the district (named in its title or URL), or it sits
    within ATTRIBUTION_WINDOW characters of a mention of the district. A statewide figure on a page that merely lists
    the district fails."""
    head = f"{page.get('title', '')} {page.get('url', '')}".lower()
    if any(a in head for a in aliases):
        return number_on_page(n, text)
    low = text.lower()
    pos = [m.start() for a in aliases for m in re.finditer(re.escape(a), low)]
    return any(any(abs(m.start() - p) <= ATTRIBUTION_WINDOW for p in pos)
               for m in re.finditer(rf"(?<![\d.]){re.escape(n)}(?![\d])", text))


def number_on_page(n: str, text: str) -> bool:
    if re.search(rf"(?<![\d.]){re.escape(n)}(?![\d])", text):
        return True
    try:  # 46.30 vs 46.3, 12 vs 12.0
        f = float(n)
        return any(abs(float(m) - f) < 1e-9 for m in re.findall(r"\d+\.?\d*", text) if m.strip("."))
    except ValueError:
        return False


# ── compile ──────────────────────────────────────────────────────────────────

SYSTEM = (
    "You compile a research file on UNDER-5 CHILD STUNTING / child undernutrition in ONE Karnataka district, for a "
    "dashboard. Use ONLY the supplied `pages` (id, url, title, excerpt); every claim must cite page ids that "
    "actually support it, and every number you write must appear in a cited excerpt exactly. Paraphrase; never "
    "invent. District-specific evidence only: statewide or national figures go in keyFacts with a label starting "
    "'Statewide:' or not at all. If the pages say little, say little and set coverage to 'thin'.\n\n"
    "Also, for each factor in `model_top_factors` (the NITI stunting model's factors needing the largest change "
    "here), say whether the pages give LOCAL evidence for why that factor matters for stunting in this district.\n\n"
    "Respond with JSON:\n"
    '{"headline": str (<= 25 words, best-evidenced takeaway for this district), '
    '"summary": str (60-100 words: what the sources say about child undernutrition/stunting here and why), '
    '"reasons": [{"factor": str (<= 6 words), "category": one of ' + json.dumps(list(CATEGORIES)) + ', '
    '"detail": str (<= 40 words, specific to this district), "sources": [int], "evidence": "strong"|"moderate"|"thin"}] (0-6), '
    '"keyFacts": [{"label": str (<= 8 words incl. year), "value": str (figure exactly as on the page), "sources": [int]}] (0-6), '
    '"headlines": [{"source": int, "takeaway": str (<= 25 words)}] (0-8, district-specific news items), '
    '"responses": [{"text": str (<= 30 words: a local programme or official action), "sources": [int]}] (0-4), '
    '"modelFactorWhy": [{"factor": str (exact name from model_top_factors), "verdict": "supported"|"partly"|"no-evidence", '
    '"why": str (<= 60 words), "mechanism": str (<= 35 words, general route by which this factor relates to stunting), '
    '"proof": [{"claim": str (<= 40 words), "sources": [int]}]}], '
    '"coverage": "rich"|"moderate"|"thin", "gaps": str (<= 40 words: what was looked for but not found)}'
)


async def research_district(did: str, llm, client: httpx.AsyncClient) -> dict:
    d = district_by_id()[did]
    name = d["name"].split(" (")[0]
    aliases = ALIASES.get(d["name"], [name.lower()])
    m = model()
    sd = m["districts"].get(did) or {}
    info = {f["name"]: f for f in m["factors"]}
    top = [f["name"] for f in (sd.get("factors") or [])[:3]]

    # 1. search
    found = await claude_search(queries(name, [info[t]["short"] for t in top]))
    seen = {u: r for u, r in found.items() if not any(b in u for b in BLOCKED_HOSTS)}

    # 2. fetch + filter
    pages, texts = [], {}
    sem = asyncio.Semaphore(6)

    async def one(url: str, r: dict) -> None:
        async with sem:
            raw = await fetch(client, url)
        text = page_text(raw) if raw else ""  # pdf / blocked pages cannot be verified, so they are skipped
        low = text.lower()
        if not text or not any(a in low for a in aliases) or not TOPIC_WORDS.search(text):
            return
        title, date, outlet = page_meta(raw, url)
        if title == url and r.get("title"):
            title = r["title"][:200]
        texts[url] = text
        pages.append({"url": url, "title": title, "date": date, "outlet": outlet, "excerpt": excerpt(text, aliases)})

    await asyncio.gather(*(one(u, r) for u, r in seen.items()))
    pages.sort(key=lambda p: -len(TOPIC_WORDS.findall(p["excerpt"])))
    pages = pages[:20]
    for i, p in enumerate(pages, start=1):
        p["id"] = i

    base = {
        "districtId": did, "name": d["name"], "regionId": d["regionId"], "topic": "stunting",
        "researchedOn": datetime.date.today().isoformat(),
        "method": "automated: web search + Claude compile + page verification (scripts/research_stunting_districts.py)",
    }
    if not pages:
        return {**base, "headline": f"No district-specific reporting on child stunting found for {name}.",
                "summary": "", "reasons": [], "keyFacts": [], "headlines": [], "responses": [], "sources": [],
                "modelFactorWhy": [], "coverage": "thin",
                "gaps": f"{len(seen)} search results; none named {name} and discussed child nutrition.",
                "verificationNotes": [], "searched": len(seen)}

    # 3. compile
    user = {
        "district": name,
        "model": {"stunting_pct_nfhs6": sd.get("stunting"), "karnataka_mean_pct": m["statewide"]["mean"]},
        "model_top_factors": top,
        "pages": [{k: p[k] for k in ("id", "url", "title", "excerpt")} for p in pages],
    }
    out = await llm._chat_json(SYSTEM, json.dumps(user, ensure_ascii=False), timeout=240.0)

    # 4. verify
    notes: list[str] = []
    by_id = {p["id"]: p for p in pages}

    def keep_sources(ids, claim: str, label: str) -> list[int]:
        ids = [i for i in ids or [] if isinstance(i, int) and i in by_id]
        if not ids:
            notes.append(f"dropped {label} (no valid source): {claim[:90]}")
            return []
        missing = [n for n in numbers(claim) if not any(number_on_page(n, texts[by_id[i]["url"]]) for i in ids)]
        if missing:
            notes.append(f"dropped {label} (number {', '.join(missing)} not on cited page): {claim[:90]}")
            return []
        statewide = label == "fact" and claim.lower().startswith("statewide")
        loose = [n for n in numbers(claim) if not re.fullmatch(r"(19|20)\d\d", n) and not statewide
                 and not any(attributed(n, by_id[i], texts[by_id[i]["url"]], aliases) for i in ids)]
        if loose:
            notes.append(f"dropped {label} (number {', '.join(loose)} not attributable to {name}): {claim[:90]}")
            return []
        return ids

    reasons = []
    for r in out.get("reasons") or []:
        ids = keep_sources(r.get("sources"), f"{r.get('factor', '')}: {r.get('detail', '')}", "reason")
        if ids:
            cat = r.get("category") if r.get("category") in CATEGORIES else "other"
            ev = r.get("evidence") if r.get("evidence") in ("strong", "moderate", "thin") else "thin"
            reasons.append({"factor": str(r.get("factor", ""))[:80], "category": cat, "detail": str(r.get("detail", "")),
                            "sources": ids, "evidence": ev})
    facts = []
    for f in out.get("keyFacts") or []:
        ids = keep_sources(f.get("sources"), f"{f.get('label', '')} {f.get('value', '')}", "fact")
        if ids:
            facts.append({"label": str(f.get("label", "")), "value": str(f.get("value", "")), "sources": ids})
    responses = []
    for r in out.get("responses") or []:
        ids = keep_sources(r.get("sources"), str(r.get("text", "")), "response")
        if ids:
            responses.append({"text": str(r.get("text", "")), "sources": ids})
    headlines = []
    for h in out.get("headlines") or []:
        p = by_id.get(h.get("source"))
        if p and keep_sources([p["id"]], str(h.get("takeaway", "")), "headline"):
            headlines.append({"title": p["title"], "outlet": p["outlet"], "date": p["date"], "url": p["url"],
                              "takeaway": str(h.get("takeaway", ""))})
    headlines.sort(key=lambda h: h["date"] or "", reverse=True)
    why = []
    for w in out.get("modelFactorWhy") or []:
        if w.get("factor") not in top:
            continue
        proof = []
        for pr in w.get("proof") or []:
            ids = keep_sources(pr.get("sources"), str(pr.get("claim", "")), f"proof for {w['factor'][:30]}")
            if ids:
                proof.append({"claim": str(pr.get("claim", "")), "sources": ids})
        verdict = w.get("verdict") if w.get("verdict") in ("supported", "partly", "no-evidence") else "no-evidence"
        if verdict != "no-evidence" and not proof:
            notes.append(f"{w['factor'][:40]}: verdict {verdict} -> no-evidence (no proof survived)")
            verdict = "no-evidence"
        why.append({"factor": w["factor"], "verdict": verdict, "why": str(w.get("why", "")),
                    "mechanism": str(w.get("mechanism", "")), "proof": proof})
    for t in top:  # every top factor gets an entry
        if not any(w["factor"] == t for w in why):
            why.append({"factor": t, "verdict": "no-evidence", "why": "", "mechanism": "", "proof": []})

    # renumber sources to the ones actually cited
    used = sorted({i for x in (*reasons, *facts, *responses) for i in x["sources"]}
                  | {p["id"] for p in pages if any(h["url"] == p["url"] for h in headlines)}
                  | {i for w in why for pr in w["proof"] for i in pr["sources"]})
    remap = {old: new for new, old in enumerate(used, start=1)}
    for x in (*reasons, *facts, *responses):
        x["sources"] = [remap[i] for i in x["sources"]]
    for w in why:
        for pr in w["proof"]:
            pr["sources"] = [remap[i] for i in pr["sources"]]
    sources = [{"id": remap[i], "url": by_id[i]["url"], "title": by_id[i]["title"], "outlet": by_id[i]["outlet"],
                "date": by_id[i]["date"], "type": source_type(by_id[i]["url"])} for i in used]
    # headline / summary: every number must be on a page or be one of the model's own figures (NFHS-6)
    allowed = {str(sd.get("stunting")), str(m["statewide"]["mean"])}
    all_text = " ".join(texts[p["url"]] for p in pages)

    def ok_number(n: str) -> bool:
        return n in allowed or number_on_page(n, all_text)

    summary = " ".join(
        sent for sent in re.split(r"(?<=[.!?])\s+", str(out.get("summary", "")))
        if all(ok_number(n) for n in numbers(sent)) or not notes.append(f"dropped summary sentence (unverified number): {sent[:90]}")
    )
    headline = str(out.get("headline", ""))
    if not all(ok_number(n) for n in numbers(headline)):
        notes.append(f"headline replaced (unverified number): {headline[:90]}")
        headline = (reasons[0]["detail"] if reasons else summary)[:180]
    coverage = out.get("coverage") if out.get("coverage") in ("rich", "moderate", "thin") else "thin"
    if len(reasons) < 2 or len(sources) < 3:
        coverage = "thin"
    return {**base, "headline": headline, "summary": summary,
            "reasons": reasons, "keyFacts": facts, "headlines": headlines, "responses": responses, "sources": sources,
            "modelFactorWhy": why, "coverage": coverage, "gaps": str(out.get("gaps", "")),
            "verificationNotes": notes, "searched": len(seen), "candidatePages": len(pages)}


def source_type(url: str) -> str:
    host = urlparse(url).netloc
    if host.endswith((".gov.in", ".nic.in")) or "gov" in host:
        return "government"
    if any(k in host for k in ("ncbi", "pubmed", "journal", ".ac.in", ".edu", "research", "springer", "elsevier")):
        return "research"
    if any(k in host for k in ("unicef", "who.int", "worldbank", "foundation", "trust", ".org")):
        return "ngo"
    return "news"


def reverify(path: str) -> int:
    """Re-apply the attribution check to an existing file from the cached pages (no search, no LLM)."""
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    aliases = ALIASES.get(d["name"], [d["name"].split(" (")[0].lower()])
    src = {x["id"]: x for x in d["sources"]}
    text = {i: page_text(open(cache_path(x["url"]), encoding="utf-8").read()) if os.path.isfile(cache_path(x["url"])) else ""
            for i, x in src.items()}
    notes, dropped = list(d.get("verificationNotes") or []), 0

    def ok(claim: str, ids: list[int], label: str, statewide: bool = False) -> bool:
        nonlocal dropped
        loose = [n for n in numbers(claim) if not re.fullmatch(r"(19|20)\d\d", n) and not statewide
                 and not any(attributed(n, src[i], text[i], aliases) for i in ids if i in src)]
        if loose:
            notes.append(f"dropped {label} (number {', '.join(loose)} not attributable to {d['name']}): {claim[:90]}")
            dropped += 1
            return False
        return True

    d["keyFacts"] = [x for x in d["keyFacts"] if ok(f"{x['label']} {x['value']}", x["sources"], "fact", x["label"].lower().startswith("statewide"))]
    d["reasons"] = [x for x in d["reasons"] if ok(x["detail"], x["sources"], "reason")]
    d["responses"] = [x for x in d["responses"] if ok(x["text"], x["sources"], "response")]
    for w in d["modelFactorWhy"]:
        w["proof"] = [p for p in w["proof"] if ok(p["claim"], p["sources"], "proof")]
        if w["verdict"] != "no-evidence" and not w["proof"]:
            notes.append(f"{w['factor'][:40]}: verdict {w['verdict']} -> no-evidence (no proof survived)")
            w["verdict"] = "no-evidence"
    if len(d["reasons"]) < 2 or len(d["sources"]) < 3:
        d["coverage"] = "thin"
    d["verificationNotes"] = notes
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(d, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    return dropped


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--district", action="append", default=[])
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--skip-existing", action="store_true")
    ap.add_argument("--provider", default="azure_anthropic")
    ap.add_argument("--concurrency", type=int, default=2)
    ap.add_argument("--reverify", action="store_true", help="re-apply verification to existing files from cached pages")
    args = ap.parse_args()
    if args.reverify:
        total = 0
        for f in sorted(os.listdir(OUT)):
            if f.endswith(".json"):
                n = reverify(os.path.join(OUT, f))
                total += n
                if n:
                    print(f"  {f}: {n} claims dropped")
        print(f"re-verified; {total} claims dropped")
        return
    ids = [d["districtId"] for d in districts()] if args.all else args.district
    if not ids:
        ap.error("pass --district <id> or --all")
    if args.skip_existing:
        ids = [i for i in ids if not os.path.isfile(os.path.join(OUT, f"{i}.json"))]
    settings = get_settings()
    if not settings.has_azure_anthropic:
        sys.exit("AZURE_ANTHROPIC_API_KEY / AZURE_ANTHROPIC_ENDPOINT are needed (Claude does the web search)")
    llm = get_llm_client(settings, args.provider)
    os.makedirs(OUT, exist_ok=True)
    sem = asyncio.Semaphore(args.concurrency)
    async with httpx.AsyncClient() as client:

        async def run(did: str) -> None:
            async with sem:
                for attempt in range(2):
                    try:
                        rec = await research_district(did, llm, client)
                        break
                    except Exception as exc:  # noqa: BLE001
                        print(f"  fail {did} (attempt {attempt + 1}): {exc}", flush=True)
                else:
                    return
            with open(os.path.join(OUT, f"{did}.json"), "w", encoding="utf-8") as fh:
                json.dump(rec, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
            print(f"  ok   {rec['name']}: {rec['coverage']}, {len(rec['sources'])} sources, {len(rec['reasons'])} reasons, "
                  f"{len(rec['headlines'])} headlines, {len(rec['verificationNotes'])} dropped "
                  f"({rec.get('searched')} results searched)", flush=True)

        await asyncio.gather(*(run(i) for i in ids))


if __name__ == "__main__":
    asyncio.run(main())
