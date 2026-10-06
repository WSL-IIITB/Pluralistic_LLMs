"""
LLMClient implementations (see base.py for the Protocol contract).

`StubLLMClient` is fully deterministic and makes zero external calls — every
method is seeded off a hash of its own input, never real randomness or wall
clock time, so the same query/posts always produce the same clusters/labels/
answer. `OpenAILLMClient` is the real implementation, gated behind
`Settings.has_llm`; every one of its methods falls back to the equivalent stub
call on any OpenAI error so a single transient failure never crashes a run.

`get_llm_client(settings)` is the seam the rest of the pipeline should import.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections import Counter

from ..config import DATA_DIR, Settings
from ..reasoning_modes import OLLAMA_MODEL_TAGS, RESEARCH_WORDCOUNT_HINT, LlmProvider, ResearchMode
from .base import LLMClient

# Shared across every research()/_research_one() prompt (OpenAI, LocalOllama,
# RemoteGemma) so "prefer official sources" doesn't drift out of sync between
# them. Named Indian government/statistical sources are called out explicitly
# rather than left as a vague "government reports" -- a search/summarization
# model reliably recognizes and prioritizes concrete institution names
# (NITI Aayog, data.gov.in, PIB, Census/NSSO/NFHS/UDISE+) far better than an
# abstract instruction to prefer "official" content, which under-specifies
# what counts.
# How much of a search result's body text to retain for GEOGRAPHY extraction
# (research.py's _posts_from_research_documents), as opposed to the ~220-char
# `snippet` the UI renders. A source's state/district is often named in its
# body rather than its title -- an official "Dropout Rate of School Children"
# PIB release names the states in its table, not its headline -- so extracting
# places from a 220-char snippet finds nothing for most documents. Capped
# rather than unbounded: this text is fed to a per-document LLM call, so it
# needs to stay a sane prompt size.
_GEO_TEXT_CHARS = 1500

# Results requested per web_search call, shared by every provider's
# `_web_search`. Raised from Ollama's own default of 5: each research angle
# makes a fixed, small number of search CALLS, so asking for more results per
# call is the one lever that materially increases the gathered-source (and
# therefore mapped-post -- see research.py's _posts_from_research_documents)
# count WITHOUT adding requests. That matters specifically because this API
# rate-limits on request count (observed 429s), so widening each call is
# strictly cheaper than making more of them. Documents are deduped by URL
# downstream, so overlap between angles costs nothing but is not wasted
# either.
_WEB_SEARCH_MAX_RESULTS = 10

_OFFICIAL_SOURCE_BIAS = (
    "Prioritize OFFICIAL Indian government and statistical sources when they cover the topic: "
    "NITI Aayog (niti.gov.in), the Open Government Data platform (data.gov.in), the Press "
    "Information Bureau (pib.gov.in), central/state ministry websites (*.gov.in), state "
    "government portals, and official statistical releases (Census, NSSO, NFHS, UDISE+, RBI, "
    "parliamentary reports/Lok Sabha or Rajya Sabha replies), and for Karnataka specifically "
    "karnataka.gov.in department portals, the Karnataka Economic Survey, Karnataka Human "
    "Development Reports, Samagra Shikshana Karnataka, and district NIC portals (*.nic.in). These "
    "are authoritative and "
    "citable by name -- prefer them over generic news coverage or blog commentary whenever they "
    "exist for the topic; fall back to reputable news/NGO/academic sources only when no official "
    "source covers it."
)

# ── Shared stub fixtures ──────────────────────────────────────────────────────

# ~30 major Indian city/state names — enough to exercise the place_ner resolver
# stage meaningfully without needing a full gazetteer scan in the stub path.
_PLACE_NAMES = [
    "Mumbai", "Delhi", "Chennai", "Kolkata", "Bengaluru", "Bangalore", "Hyderabad",
    "Pune", "Ahmedabad", "Jaipur", "Lucknow", "Surat", "Kochi", "Coimbatore",
    "Chandigarh", "Bhopal", "Patna", "Nagpur", "Indore", "Guwahati",
    "Kerala", "Punjab", "Gujarat", "Tamil Nadu", "Maharashtra", "Karnataka",
    "West Bengal", "Uttar Pradesh", "Rajasthan", "Bihar", "Odisha", "Assam",
    "Haryana", "Madhya Pradesh", "Telangana", "Goa", "Kashmir",
]

_POLICY_KEYWORDS = (
    "should", "policy", "intervene", "intervention", "government", "govt",
    "recommend", "dropout", "budget", "allocate", "where to", "invest",
)

_PII_RE = re.compile(r"u/\S+|@\S+|https?://\S+", re.IGNORECASE)
_WS_RE = re.compile(r"\s+")
_TOKEN_RE = re.compile(r"[a-z0-9']+")


def _clean_for_display(text: str, max_len: int = 140) -> str:
    """Strip username/handle/URL tokens, collapse whitespace, cap length.

    Guaranteed to differ from the verbatim input whenever a PII-like token was
    present (the substitution necessarily removes characters); otherwise this
    is just light whitespace/length normalization.
    """
    cleaned = _PII_RE.sub("", text)
    cleaned = _WS_RE.sub(" ", cleaned).strip()
    if not cleaned:
        cleaned = "(redacted post)"
    if len(cleaned) > max_len:
        cleaned = cleaned[: max_len - 1].rstrip() + "…"
    return cleaned


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _hash_embed(text: str, dim: int = 32) -> list[float]:
    """Deterministic pseudo-embedding: average a per-token sha256-seeded
    vector over all tokens in `text`. Because it's a bag-of-tokens average
    (not a whole-string hash), stub posts sharing template phrases land with
    genuinely closer vectors than unrelated ones — enough structure for
    clustering to produce varied, non-random groupings on templated content.
    """
    tokens = _tokenize(text) or [text.lower() or "empty"]
    vec = [0.0] * dim
    for tok in tokens:
        digest = hashlib.sha256(tok.encode("utf-8")).digest()
        for i in range(dim):
            byte = digest[i % len(digest)]
            vec[i] += (byte / 127.5) - 1.0
    n = len(tokens)
    return [v / n for v in vec]


_local_embedder = None  # lazily-loaded sentence-transformers model, module-level singleton

# Serializes ALL access to _local_embedder -- both its lazy construction and
# every .encode() call. Verified empirically (independent repro during this
# feature's review) that firing several concurrent FIRST-ever calls into this
# model via asyncio.to_thread (multiple background threads racing the lazy
# singleton init / the native backend's own one-time thread-pool/BLAS setup
# on their first encode()) reliably crashes the process (SIGSEGV/SIGABRT) --
# not merely slow or racy, an outright process-ending native crash. Before
# research.py's concurrent per-region research fan-out, nothing in
# this codebase ever called this function concurrently with itself (every
# prior caller issued one embed() per gather_research invocation); the new
# per-state research chain fires up to _MAX_CONCURRENT_STATE_RESEARCH of
# these at once, so this lock is required for extrahigh mode to be safe, not
# just theoretical. Embedding a single short query string is a few
# milliseconds once warm (measured independently), so fully serializing this
# one call site costs negligible wall-clock time against the LLM/web-search
# calls actually dominating the research stage's latency.
_local_embedder_lock = asyncio.Lock()


def _get_local_embedder():
    """Loaded once per process -- constructing a SentenceTransformer parses
    model weights from disk and is too slow to redo per call. Used by every
    provider with no hosted embeddings endpoint of its own (LocalOllamaLLMClient,
    RemoteGemmaLLMClient); running the model locally means clustering has no
    dependency on any provider's API being up or funded, unlike routing
    embeddings through a second LLM provider's account.

    MUST be called only while holding `_local_embedder_lock` -- see that
    lock's own docstring for why (concurrent first-use crashes the process)."""
    global _local_embedder
    if _local_embedder is None:
        from sentence_transformers import SentenceTransformer  # local import: keep this optional dep lazy

        _local_embedder = SentenceTransformer("all-MiniLM-L6-v2")
    return _local_embedder


async def _local_semantic_embed(texts: list[str]) -> list[list[float]]:
    """Shared body for every embed() override with no hosted embeddings
    endpoint of its own (the local Ollama providers, and RemoteGemmaLLMClient)
    -- one lazy-loaded sentence-transformers singleton (_get_local_embedder)
    instead of duplicating this per class. Raises on failure; callers catch
    and fall back to `_hash_embed`.

    Holds `_local_embedder_lock` for the model's entire lifetime of use here
    (construction AND every .encode() call) -- see that lock's docstring.
    This serializes concurrent callers (e.g. research.py's per-region
    per-state fan-out) rather than running their encode() calls in parallel,
    trading a small amount of parallelism for not crashing the process."""
    async with _local_embedder_lock:
        model = _get_local_embedder()
        # .encode() is a synchronous, CPU-bound call -- run it off the event
        # loop rather than blocking every other in-flight request. Safe to
        # do while holding an asyncio.Lock (unlike a threading.Lock, it only
        # blocks other COROUTINES, not this thread-pool thread).
        vectors = await asyncio.to_thread(model.encode, texts)
    return [vec.tolist() for vec in vectors]


# Ollama's hosted web-search API rate-limits bursts (HTTP 429) -- a research
# fan-out of a dozen-plus angles hits it routinely. Back off and retry rather
# than silently returning no sources.
_WEB_SEARCH_RETRY_DELAYS = (2.0, 5.0, 12.0)


async def _ollama_web_search(client, api_key: str | None, query: str, max_results: int) -> list[dict]:
    import httpx

    for attempt, delay in enumerate((0.0, *_WEB_SEARCH_RETRY_DELAYS)):
        if delay:
            await asyncio.sleep(delay)
        try:
            resp = await client.post(
                "https://ollama.com/api/web_search",
                json={"query": query, "max_results": max_results},
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=30.0,
            )
            resp.raise_for_status()
            results = resp.json().get("results")
            return results if isinstance(results, list) else []
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 429 or attempt == len(_WEB_SEARCH_RETRY_DELAYS):
                raise
    return []


class StubLLMClient:
    """Zero-external-call, fully deterministic LLMClient."""

    async def classify_query_type(self, query: str) -> str:
        q = query.lower()
        if any(kw in q for kw in _POLICY_KEYWORDS) or query.strip().endswith("?"):
            return "policy"
        return "descriptive"

    async def suggest_framings(self, query: str, max_count: int) -> list[str]:
        # No real knowledge to draw on -- honest empty result, caller falls
        # back to searching the bare query (today's behaviour).
        return []

    async def research(
        self,
        query: str,
        known_framings: list[str],
        breadth: int,
        mode: ResearchMode,
    ) -> tuple[str, list[dict]]:
        # No real web access; DO NOT fabricate URLs -- that would be worse
        # than empty research (misleading citations). Caller sees an empty
        # sources list and the synthesis stage carries on without grounding.
        return "", []

    async def extract_place_mentions(self, text: str) -> list[str]:
        lower = text.lower()
        matches: list[tuple[int, str]] = []
        for name in _PLACE_NAMES:
            pattern = r"\b" + re.escape(name.lower()) + r"\b"
            for m in re.finditer(pattern, lower):
                matches.append((m.start(), name))
        matches.sort(key=lambda pair: pair[0])
        seen: set[str] = set()
        found: list[str] = []
        for _, name in matches:
            if name not in seen:
                seen.add(name)
                found.append(name)
        return found

    async def geolocate(self, text: str, source_hint: str) -> tuple[str | None, str]:
        # Intentionally cannot geolocate — a stub shouldn't fabricate
        # confident geography. The resolver correctly falls through to
        # state_fallback/unresolved when this returns (None, "low").
        return (None, "low")

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [_hash_embed(t) for t in texts]

    async def label_cluster(self, sample_texts: list[str]) -> tuple[str, str]:
        texts = [t for t in sample_texts if t and t.strip()]
        if not texts:
            return ("Unlabeled viewpoint", "No representative posts were available for this cluster.")

        def opening(t: str, n: int = 4) -> str:
            return " ".join(t.strip().split()[:n])

        counts = Counter(opening(t) for t in texts)
        common_phrase = counts.most_common(1)[0][0]
        representative = next((t for t in texts if opening(t) == common_phrase), texts[0])
        clean_repr = _clean_for_display(representative)
        label = f"Viewpoint: {common_phrase.rstrip('.,;:!?')}".strip()
        if len(label) > 60:
            label = label[:57].rstrip() + "…"
        summary = clean_repr[:140]
        return (label, summary)

    async def paraphrase(self, text: str) -> str:
        return _clean_for_display(text)

    async def extract_deflection(
        self,
        cluster_a_label: str,
        cluster_a_texts: list[str],
        cluster_b_label: str,
        cluster_b_texts: list[str],
    ) -> tuple[str, str]:
        point = f"Whether the core driver is best framed as '{cluster_a_label}' or '{cluster_b_label}'."
        return (point, "medium")

    async def judge_text_relevance(self, question: str) -> bool:
        # A stub has no real judgment to offer -- fail closed (False), same
        # "honest, inert default" contract every other stub method follows
        # rather than fabricating a plausible-looking "yes".
        return False

    async def synthesize_answer(
        self,
        query: str,
        query_type: str,
        clusters: list[dict],
        deflections: list[dict],
        known_framings: list[str],
        research_findings: str,
        research_documents: list[dict],
        mode: ResearchMode = "medium",
    ) -> list[dict]:
        # Stub keeps the same shape as before — the research inputs (and mode)
        # are just ignored here (this deterministic fallback has no way to
        # weigh them). `cluster.get("stateCode")` below already flows into
        # `region` for extrahigh clusters with no change needed.
        segments: list[dict] = []

        n_clusters = len(clusters)
        n_deflections = len(deflections)
        tldr = (
            f"Across {n_clusters} distinct viewpoint{'s' if n_clusters != 1 else ''} found for "
            f"'{query}', {n_deflections} point{'s' if n_deflections != 1 else ''} of deflection "
            f"{'were' if n_deflections != 1 else 'was'} identified between co-occurring perspectives."
        )
        segments.append({"text": tldr, "kind": "tldr"})

        for cluster in clusters:
            cluster_id = cluster.get("id") or cluster.get("clusterId") or cluster.get("cluster_id")
            label = cluster.get("label") or "Unnamed viewpoint"
            summary = cluster.get("summary") or ""
            region = (
                cluster.get("region")
                or cluster.get("dominant_region")
                or cluster.get("state_code")
                or cluster.get("stateCode")
                or ""
            )
            if query_type == "policy":
                rec_text = f"For the '{label}' viewpoint, prioritize action addressing: {summary or label}."
            else:
                rec_text = f"{label}: {summary or 'a distinct regional perspective on this topic.'}"
            seg: dict = {"text": rec_text, "kind": "recommendation"}
            if cluster_id:
                seg["clusterId"] = cluster_id
            if region:
                seg["region"] = region
            segments.append(seg)

        return segments

    async def answer_for_region(
        self,
        query: str,
        query_type: str,
        region_name: str,
        persona_prompt: str | None,
        research_documents: list[dict],
        clusters: list[dict],
        deflections: list[dict],
        mode: ResearchMode = "medium",
    ) -> list[dict]:
        top = sorted(clusters, key=lambda c: c.get("postCount") or 0, reverse=True)
        voice = "this region's own" if persona_prompt else "the collected"
        segments: list[dict] = [
            {
                "text": f"For '{query}', {voice} evidence centres on "
                + (top[0].get("label") or "no clear viewpoint")
                if top
                else f"No regional evidence was collected for '{query}'.",
                "kind": "tldr",
            }
        ]
        for c in top[:3]:
            seg: dict = {"text": f"{c.get('label')}: {c.get('summary') or ''}".strip(), "kind": "recommendation"}
            if c.get("id"):
                seg["clusterId"] = c["id"]
            segments.append(seg)
        return segments

    async def compare_story_vs_official(
        self,
        query: str,
        area_label: str,
        story_points: list[str],
        official_factors: list[dict],
    ) -> dict:
        # Honest, inert default: state what evidence exists, fabricate no
        # synthesis, same contract every other stub method follows.
        has_story = bool(story_points)
        has_official = bool(official_factors)
        if has_story and has_official:
            comparison = (
                f"For '{query}' in {area_label}: Story Mode gathered {len(story_points)} persona "
                f"reply/replies from social and web evidence; UIDAI/NITI data names "
                f"{len(official_factors)} dominant-factor row(s) for this area's districts. No live "
                "comparison model configured for this run -- showing both sources directly rather "
                "than a synthesized comparison."
            )
        elif has_story:
            comparison = f"Only Story Mode evidence is available for {area_label}; no UIDAI/NITI row matched this area's districts."
        elif has_official:
            comparison = f"Only UIDAI/NITI data is available for {area_label}; Story Mode produced no persona reply for this area."
        else:
            comparison = f"No Story Mode or UIDAI/NITI evidence is available for {area_label}."
        consolidated = " ".join(story_points) or (
            "; ".join(f"{f.get('factor')} ({f.get('district')})" for f in official_factors) or ""
        )
        return {"comparison": comparison, "consolidated_answer": consolidated}

    async def generate_verdict(
        self,
        area_kind: str,
        area_name: str,
        state_name: str,
        context: str,
    ) -> str:
        # No real narrative generation to offer -- honest, inert default:
        # hand back the real computed digest itself (never fabricated prose)
        # under a short, deterministic framing sentence, same "here is the
        # real data, plainly" contract every other stub method follows.
        label = f"{area_name}, {state_name}" if area_kind == "district" else area_name
        return (
            f"{label}'s dropout drivers, from its own fitted regression model (no live "
            "narrative model configured for this run -- showing the underlying computed "
            f"data directly):\n\n{context}"
        )


class OpenAILLMClient:
    """Real LLMClient backed by the OpenAI API. Falls back to StubLLMClient
    (per-call) on any error so one transient LLM failure never crashes a run.
    """

    def __init__(self, settings: Settings):
        from openai import AsyncOpenAI  # local import: keep this optional dep lazy

        self.settings = settings
        # Explicit timeout: the SDK's default (10 minutes) meant one slow/stuck
        # call could stall an entire run instead of failing fast into the
        # per-call stub fallback below.
        self.client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=20.0, max_retries=1)
        self._stub = StubLLMClient()
        self._gazetteer = self._load_gazetteer()

    @staticmethod
    def _load_gazetteer() -> dict:
        import os

        from ..karnataka import load_karnataka_gazetteer

        path = os.path.join(DATA_DIR, "district_gazetteer.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                return load_karnataka_gazetteer(json.load(f))
        except Exception as exc:  # noqa: BLE001 - defensive, gazetteer is optional here
            print(f"[OpenAILLMClient] could not load district gazetteer ({exc}); geolocate will fall back to stub")
            return {}

    async def _chat_json(self, system: str, user: str, timeout: float | None = None) -> dict:
        """`timeout` overrides the client default (20s, tuned for the many small
        per-post/per-cluster calls). Pass a larger value for the few calls with
        a big payload -- synthesis in particular ingests the whole research
        digest plus every cluster and deflection, and silently timing out there
        means the answer degrades to the deterministic stub."""
        client = self.client if timeout is None else self.client.with_options(timeout=timeout)
        resp = await client.chat.completions.create(
            model=self.settings.openai_chat_model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return json.loads(resp.choices[0].message.content)

    async def classify_query_type(self, query: str) -> str:
        try:
            data = await self._chat_json(
                "You classify a user's research query about Indian public opinion as either "
                "'descriptive' (asking what people think/believe/practice) or 'policy' (asking "
                "what should be done, seeking a recommendation or intervention). Respond with "
                'JSON: {"query_type": "descriptive" | "policy"}.',
                query,
            )
            qt = data.get("query_type")
            if qt in ("descriptive", "policy"):
                return qt
            raise ValueError(f"unexpected query_type value: {qt!r}")
        except Exception as exc:  # noqa: BLE001
            print(f"[OpenAILLMClient] classify_query_type failed, falling back to stub: {exc}", flush=True)
            return await self._stub.classify_query_type(query)

    async def suggest_framings(self, query: str, max_count: int) -> list[str]:
        try:
            data = await self._chat_json(
                "You know Karnataka's regional, cultural, and linguistic variation well -- the "
                "Mysuru-Bengaluru (Old Mysore) plateau, the Karavali coast, the Malnad hills, and "
                "North Karnataka (Kittur and Kalyana Karnataka). Given a topic, list the distinct, "
                "well-known framings or interpretations of it ACROSS KARNATAKA'S REGIONS -- the "
                "substantive differences a well-informed person from each region would actually "
                "state (e.g. for 'Dasara': the Mysuru Dasara royal procession, Navaratri Sharada "
                "worship at Sringeri, Mangaluru Dasara with tiger dances, Hampi's Vijayanagara "
                "Mahanavami heritage). Each phrase should "
                "be short and search-engine-friendly (a few words, naming the specific figure/"
                "event/community, not a generic sentence). If the topic genuinely has no such "
                "well-known regional variation (e.g. a narrow local news item, a made-up word), "
                'return an empty list -- do not invent framings that don\'t exist. Respond with '
                'JSON: {"framings": ["...", "..."]} with at most '
                f"{max_count} entries, ordered most-to-least prominent.",
                query,
            )
            framings = data.get("framings")
            if not isinstance(framings, list):
                raise ValueError(f"unexpected framings value: {framings!r}")
            cleaned = [str(f).strip() for f in framings if str(f).strip()]
            return cleaned[:max_count]
        except Exception as exc:  # noqa: BLE001
            print(f"[OpenAILLMClient] suggest_framings failed, falling back to stub: {exc}", flush=True)
            return await self._stub.suggest_framings(query, max_count)

    async def _decompose_for_research(self, query: str, breadth: int) -> list[str]:
        """When suggest_framings returns empty (typical for policy queries),
        generate `breadth` search-friendly research angles instead. Different
        prompt from suggest_framings: this one is angle-generic, doesn't
        require known regional/cultural variation."""
        try:
            data = await self._chat_json(
                "Break the user's research topic into short, distinct, search-engine-friendly "
                "sub-queries that together would surface substantive, well-sourced information "
                "across Indian regions. Cover different angles (data/statistics, policy "
                "interventions, on-the-ground reporting, regional case studies, expert analysis). "
                f'Respond with JSON: {{"angles": ["...", ...]}} with at most {breadth} entries, '
                "each 3–8 words, ordered from most to least essential.",
                query,
            )
            angles = data.get("angles")
            if not isinstance(angles, list):
                raise ValueError(f"unexpected angles value: {angles!r}")
            cleaned = [str(a).strip() for a in angles if str(a).strip()]
            return cleaned[:breadth] or [query]
        except Exception as exc:  # noqa: BLE001
            print(f"[OpenAILLMClient] _decompose_for_research failed: {exc}", flush=True)
            return [query]

    async def _research_one(self, subquery: str, wordcount_hint: str) -> tuple[str, list[dict]]:
        """One web_search-grounded call. Returns (text, docs). Uses the
        research model (gpt-4o), which — unlike gpt-4o-mini — returns
        `url_citation` annotations we can harvest into ResearchDocuments.
        `wordcount_hint` (see reasoning_modes.RESEARCH_WORDCOUNT_HINT) is the
        mode-scaled "how thorough" lever — longer requested write-ups
        correlate with more sources actually read and cited, not just more
        words."""
        try:
            # Research calls are much slower than chat calls (gpt-4o + web_search
            # is typically 20–40s), so override the client's default 20s timeout
            # for just this code path — keep chat calls tight.
            research_client = self.client.with_options(timeout=90.0)
            resp = await research_client.responses.create(
                model=self.settings.openai_research_model,
                tools=[{"type": "web_search"}],
                input=(
                    "You are researching an Indian public-affairs / cultural topic for a "
                    "dashboard that will cite your sources back to the user. Use the web_search "
                    "tool to gather substantive, current, ideally India-specific information. "
                    f"{_OFFICIAL_SOURCE_BIAS} Write a concise, factual summary ({wordcount_hint}) "
                    "grounded in what you found. Cite specific numbers, dates, and sources.\n\n"
                    f"Topic / angle: {subquery}"
                ),
            )
            text = getattr(resp, "output_text", "") or ""
            docs: list[dict] = []
            seen_urls: set[str] = set()
            for item in resp.output:
                if getattr(item, "type", None) != "message":
                    continue
                for content in getattr(item, "content", []) or []:
                    for ann in getattr(content, "annotations", []) or []:
                        if getattr(ann, "type", None) != "url_citation":
                            continue
                        url = getattr(ann, "url", None)
                        if not url or url in seen_urls:
                            continue
                        seen_urls.add(url)
                        title = (getattr(ann, "title", None) or url).strip()
                        clean_url = self._strip_tracking_params(url)
                        domain = self._domain_of(clean_url)
                        docs.append(
                            {
                                "url": clean_url,
                                "title": title[:200],
                                "domain": domain,
                                "snippet": "",  # filled in by the caller from `text` if needed
                            }
                        )
            return text, docs
        except Exception as exc:  # noqa: BLE001
            print(f"[OpenAILLMClient] research call for {subquery!r} failed: {exc}", flush=True)
            return "", []

    @staticmethod
    def _strip_tracking_params(url: str) -> str:
        """Drop utm_*/ref tracking params the search tool appends (it tags every
        citation with `utm_source=openai`), while PRESERVING real query params —
        many government URLs carry their content id in the query string
        (e.g. pib.gov.in/PressReleasePage.aspx?PRID=2242974), so a naive
        truncate-at-'?' would break the link entirely."""
        try:
            from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

            parts = urlsplit(url)
            if not parts.query:
                return url
            kept = [
                (k, v)
                for k, v in parse_qsl(parts.query, keep_blank_values=True)
                if not k.lower().startswith(("utm_", "ref_")) and k.lower() not in {"ref", "source"}
            ]
            return urlunsplit(parts._replace(query=urlencode(kept)))
        except Exception:  # noqa: BLE001 — never let URL cleanup break a citation
            return url

    @staticmethod
    def _domain_of(url: str) -> str:
        try:
            from urllib.parse import urlparse

            host = urlparse(url).hostname or ""
            return host.removeprefix("www.")
        except Exception:  # noqa: BLE001
            return ""

    @staticmethod
    def _strip_markdown_noise(text: str) -> str:
        """The research model writes markdown prose with inline links like
        `([4](https://x.gov.in/y.pdf?utm_source=openai))`. That's unreadable
        when rendered as plain text in the answer panel, and the synthesis
        model tends to copy it verbatim into its own output. Flatten links to
        their label, drop bare URLs, and strip bold/heading markers here so
        neither the digest nor anything derived from it carries the noise.
        Citations are carried structurally (AnswerSegment.citations), not as
        inline markdown, so nothing is lost by removing them."""
        # Parenthesised numeric citation links -- `([4](https://…))` -- are pure
        # noise here (the number is a research-model artifact, not one of OUR
        # document ids), so drop them whole rather than leaving a stray "(4)".
        text = re.sub(r"\(\s*\[\d+\]\([^)]*\)\s*\)", "", text)
        # [label](url) -> label   (drop the URL entirely)
        text = re.sub(r"\[([^\]]*)\]\((?:[^)]*)\)", r"\1", text)
        # Leftover bare URLs.
        text = re.sub(r"https?://\S+", "", text)
        # Bold/italic/heading/bullet markers.
        text = re.sub(r"\*\*|__|^#{1,6}\s*", "", text, flags=re.MULTILINE)
        # Empty parens/brackets left behind by the substitutions above.
        text = re.sub(r"\(\s*[),;]?\s*\)", "", text)
        text = re.sub(r"\[\s*\]", "", text)
        # Collapse the whitespace those removals opened up, including the
        # orphaned space before punctuation a removed inline citation leaves.
        text = re.sub(r"[ \t]{2,}", " ", text)
        text = re.sub(r"[ \t]+([.,;:!?])", r"\1", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    async def research(
        self,
        query: str,
        known_framings: list[str],
        breadth: int,
        mode: ResearchMode,
    ) -> tuple[str, list[dict]]:
        angles = [f.strip() for f in known_framings if f and f.strip()]
        if not angles:
            angles = await self._decompose_for_research(query, breadth)
        # Cap concurrency modestly — gpt-4o web_search calls are slow (~15–30s
        # each) but the OpenAI Responses API handles a handful of parallel
        # requests comfortably. Higher than this and one slow-searching angle
        # would just cause head-of-line blocking without buying more coverage.
        angles = angles[:breadth]
        wordcount_hint = RESEARCH_WORDCOUNT_HINT[mode]
        import asyncio as _asyncio

        results = await _asyncio.gather(
            *(
                self._research_one(
                    f"{a} · {query}" if a.lower() != query.lower() else query, wordcount_hint
                )
                for a in angles
            ),
            return_exceptions=False,
        )

        # Merge findings text (one paragraph per angle) and dedupe docs by URL,
        # renumbering to 1-based order-of-first-appearance so citations from
        # different angles map onto one canonical Sources list.
        findings_parts: list[str] = []
        merged_docs: list[dict] = []
        seen: set[str] = set()
        for angle, (raw_text, docs) in zip(angles, results):
            text = self._strip_markdown_noise(raw_text or "")
            if text:
                findings_parts.append(f"{angle}:\n{text}")
            for d in docs:
                if d["url"] in seen:
                    continue
                seen.add(d["url"])
                # Take a short snippet from the corresponding angle's findings
                # text if no page-level excerpt was provided by the tool.
                snippet = text.replace("\n", " ")
                if len(snippet) > 220:
                    snippet = snippet[:220].rstrip() + "…"
                merged_docs.append({**d, "snippet": snippet})
        # Assign 1-based ids (final ordering).
        for i, d in enumerate(merged_docs, 1):
            d["id"] = i
        findings = "\n\n".join(findings_parts).strip()
        return findings, merged_docs

    async def extract_place_mentions(self, text: str) -> list[str]:
        try:
            data = await self._chat_json(
                "Extract every Indian place name mentioned in the user's text — city, town, "
                "taluk, district, or state names, and named regions such as 'Malnad', "
                "'Karavali', 'Tulu Nadu', or 'Kalyana Karnataka'. Respond with JSON: "
                '{"places": ["...", ...]}. Return an empty list if none are mentioned.',
                text,
            )
            places = data.get("places")
            if isinstance(places, list) and all(isinstance(p, str) for p in places):
                return places
            raise ValueError("malformed places list")
        except Exception as exc:  # noqa: BLE001
            print(f"[OpenAILLMClient] extract_place_mentions failed, falling back to stub: {exc}", flush=True)
            return await self._stub.extract_place_mentions(text)

    async def geolocate(self, text: str, source_hint: str) -> tuple[str | None, str]:
        try:
            data = await self._chat_json(
                "Given a social-media post's text and its source hint (subreddit name, or "
                "'channel · video title'), infer the single most likely Indian district or "
                'city the author is posting about or from. Respond with JSON: {"place": '
                '"<district or city name>" | null, "confidence": "high"|"medium"|"low"}. Use '
                'null and "low" if there is no reasonable signal.',
                f"Source: {source_hint}\n\nText: {text}",
            )
            place = data.get("place")
            confidence = data.get("confidence", "low")
            if confidence not in ("high", "medium", "low"):
                confidence = "low"
            district_id = None
            if isinstance(place, str) and place.strip():
                entries = self._gazetteer.get(place.strip().lower())
                if entries:
                    district_id = entries[0].get("districtId")
                else:
                    confidence = "low"
            else:
                confidence = "low"
            return (district_id, confidence)
        except Exception as exc:  # noqa: BLE001
            print(f"[OpenAILLMClient] geolocate failed, falling back to stub: {exc}", flush=True)
            return await self._stub.geolocate(text, source_hint)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            resp = await self.client.embeddings.create(
                model=self.settings.openai_embedding_model,
                input=texts,
            )
            return [item.embedding for item in resp.data]
        except Exception as exc:  # noqa: BLE001
            print(f"[OpenAILLMClient] embed failed, falling back to stub: {exc}", flush=True)
            return await self._stub.embed(texts)

    async def label_cluster(self, sample_texts: list[str]) -> tuple[str, str]:
        try:
            joined = "\n".join(f"- {t}" for t in sample_texts[:10])
            data = await self._chat_json(
                "You label a cluster of social-media posts that express the same underlying "
                "viewpoint. Given sample posts, respond with JSON: "
                '{"label": "<short label, <=6 words>", "summary": "<one-line summary, <=160 '
                'chars>"}.',
                f"Sample posts:\n{joined}",
            )
            label, summary = data.get("label"), data.get("summary")
            if isinstance(label, str) and isinstance(summary, str) and label and summary:
                return (label, summary)
            raise ValueError("malformed label/summary")
        except Exception as exc:  # noqa: BLE001
            print(f"[OpenAILLMClient] label_cluster failed, falling back to stub: {exc}", flush=True)
            return await self._stub.label_cluster(sample_texts)

    async def paraphrase(self, text: str) -> str:
        try:
            data = await self._chat_json(
                "Paraphrase the given social-media post for safe public display: preserve its "
                "meaning and tone but rewrite the wording, and remove any usernames, handles, or "
                'URLs. Respond with JSON: {"paraphrase": "<rewritten text, <=140 chars>"}.',
                text,
            )
            paraphrase = data.get("paraphrase")
            if isinstance(paraphrase, str) and paraphrase.strip():
                return paraphrase.strip()
            raise ValueError("malformed paraphrase")
        except Exception as exc:  # noqa: BLE001
            print(f"[OpenAILLMClient] paraphrase failed, falling back to stub: {exc}", flush=True)
            return await self._stub.paraphrase(text)

    async def extract_deflection(
        self,
        cluster_a_label: str,
        cluster_a_texts: list[str],
        cluster_b_label: str,
        cluster_b_texts: list[str],
    ) -> tuple[str, str]:
        try:
            a_samples = "\n".join(f"- {t}" for t in cluster_a_texts[:5])
            b_samples = "\n".join(f"- {t}" for t in cluster_b_texts[:5])
            data = await self._chat_json(
                "Two clusters of posts express different viewpoints on the same topic. Identify "
                "the single 'point of deflection' — the crux where the two viewpoints diverge "
                '— in one sentence. Respond with JSON: {"point": "<one sentence>", '
                '"confidence": "high"|"medium"|"low"}.',
                f"Viewpoint A — {cluster_a_label}:\n{a_samples}\n\n"
                f"Viewpoint B — {cluster_b_label}:\n{b_samples}",
            )
            point, confidence = data.get("point"), data.get("confidence")
            if confidence not in ("high", "medium", "low"):
                confidence = "medium"
            if isinstance(point, str) and point.strip():
                return (point.strip(), confidence)
            raise ValueError("malformed deflection")
        except Exception as exc:  # noqa: BLE001
            print(f"[OpenAILLMClient] extract_deflection failed, falling back to stub: {exc}", flush=True)
            return await self._stub.extract_deflection(
                cluster_a_label, cluster_a_texts, cluster_b_label, cluster_b_texts
            )

    async def judge_text_relevance(self, question: str) -> bool:
        try:
            data = await self._chat_json(
                'Answer the user\'s yes/no question. Respond with JSON: {"answer": "yes" | "no"}.',
                question,
            )
            answer = data.get("answer")
            if isinstance(answer, str) and answer.strip().lower() in ("yes", "no"):
                return answer.strip().lower() == "yes"
            raise ValueError(f"unexpected answer value: {answer!r}")
        except Exception as exc:  # noqa: BLE001
            print(f"[OpenAILLMClient] judge_text_relevance failed, failing closed (False): {exc}", flush=True)
            return False

    async def synthesize_answer(
        self,
        query: str,
        query_type: str,
        clusters: list[dict],
        deflections: list[dict],
        known_framings: list[str],
        research_findings: str,
        research_documents: list[dict],
        mode: ResearchMode = "medium",
    ) -> list[dict]:
        try:
            # Only pass id + title + domain of research documents to the model
            # (not the full snippet) — the model already saw the findings text,
            # which is where the substance lives; the documents list here is
            # just an index it uses to attach citations by id.
            doc_index = [
                {
                    "id": d.get("id"),
                    "title": d.get("title"),
                    "domain": d.get("domain"),
                }
                for d in research_documents
                if isinstance(d, dict) and d.get("id")
            ]
            # Belt-and-braces on top of research.py's own per-job cap: this is
            # the one call that bundles evidence from EVERY region into a
            # single prompt, so it's the most exposed to a context-window
            # overflow as the region/mode count grows. A silent truncation
            # here is far better than the alternative -- this whole call
            # falling back to the generic stub overview (see the except
            # below), which is worse for every region, not just the trimmed
            # part.
            _MAX_FINDINGS_CHARS = 20_000
            findings = research_findings or ""
            if len(findings) > _MAX_FINDINGS_CHARS:
                findings = findings[:_MAX_FINDINGS_CHARS].rstrip() + "\n\n[additional findings truncated for length]"
            payload = {
                "query": query,
                "query_type": query_type,
                "clusters": clusters,
                "deflections": deflections,
                "known_framings": known_framings,
                "research_findings": findings,
                "research_documents": doc_index,
            }
            structure_instructions = (
                "REQUIRED STRUCTURE — exactly this shape, in this order:\n"
                "1. EXACTLY ONE `tldr` segment: a single sentence (max ~30 words) giving the "
                "core takeaway. This is the headline answer — make it specific and substantive, "
                "not a restatement of the question.\n"
                "2. THREE to FIVE `recommendation` segments: tight, scannable bullets, each ONE "
                "sentence (max ~35 words). For policy queries these are concrete actions or "
                "findings; for descriptive queries these are the distinct viewpoints/regional "
                "positions. Set `region` when a bullet is region-specific, `clusterId` when it "
                "maps to a specific viewpoint cluster.\n"
                "3. TWO to FOUR `detail` segments: the fuller analysis, one paragraph each "
                "(~60–90 words). These are collapsed behind a 'Full analysis' toggle, so this "
                "is where depth, numbers, and nuance belong.\n\n"
            )
            data = await self._chat_json(
                "You synthesize a consolidated answer from clustered social-media viewpoints, "
                "their points of deflection, and web-search-grounded research, for a compact "
                "dashboard panel. Inputs: the query, its type ('descriptive' or 'policy'), the "
                "viewpoint clusters (each with id/label/summary), the deflections between them, "
                "`known_framings` (well-known regional/cultural framings you already know to be "
                "true — possibly empty), `research_findings` (a plaintext digest of what the web "
                "search surfaced), and `research_documents` (ordered {id, title, domain} for the "
                "sources behind those findings; ids are 1-based).\n\n"
                'Respond with JSON: {"segments": [...]}. Each segment is {"text": str, "kind": '
                '"tldr"|"recommendation"|"detail", "clusterId": str (optional), "region": str '
                '(optional), "citations": int[] (optional)}.\n\n'
                + structure_instructions +
                "FORMATTING — strictly enforced:\n"
                "• PLAIN TEXT ONLY. No markdown whatsoever: no **bold**, no ## headings, no "
                "bullet characters, no [label](url) links, no bare URLs. The UI renders these "
                "as plain text and any markup shows up as literal garbage characters.\n"
                "• Never write source names or URLs inline — use the `citations` field instead.\n"
                "• Respect the word limits above; the panel is narrow and long segments break "
                "the layout.\n\n"
                "GROUNDING:\n"
                "• When `research_findings` has substance, USE IT — cite specific numbers, "
                "dates, policy names, agency findings. Do not hedge into vagueness.\n"
                "• Where a cluster's label/summary matches a `known_framing`, state the "
                "substance DIRECTLY (name the deity, story, event, policy) — not vague hedges "
                "like 'various perspectives'. Only introduce a framing with SOME support in the "
                "clusters or the research.\n"
                "• Attach `citations` (document ids) to every segment drawing on research. Do "
                "NOT invent ids — only use ids present in `research_documents`. Omitting "
                "citations is fine for segments sourced purely from the social-media clusters.",
                json.dumps(payload),
                timeout=150.0 if mode == "extrahigh" else 90.0,
            )
            segments = data.get("segments")
            if not isinstance(segments, list) or not segments:
                raise ValueError("malformed segments")
            valid_ids = {d.get("id") for d in doc_index}
            valid_kinds = ("tldr", "heading", "body", "recommendation", "detail")
            cleaned: list[dict] = []
            for seg in segments:
                if not isinstance(seg, dict):
                    raise ValueError("malformed segment entry")
                text, kind = seg.get("text"), seg.get("kind")
                if not isinstance(text, str) or kind not in valid_kinds:
                    raise ValueError("malformed segment fields")
                # Belt-and-braces: the prompt forbids markdown, but models slip.
                # Strip it here so the UI never renders literal ** or [x](url).
                text = self._strip_markdown_noise(text)
                if not text:
                    continue
                out: dict = {"text": text, "kind": kind}
                if isinstance(seg.get("clusterId"), str):
                    out["clusterId"] = seg["clusterId"]
                if isinstance(seg.get("region"), str):
                    out["region"] = seg["region"]
                if isinstance(seg.get("citations"), list):
                    kept = [
                        int(c)
                        for c in seg["citations"]
                        if isinstance(c, int) and c in valid_ids
                    ]
                    if kept:
                        out["citations"] = kept
                cleaned.append(out)
            return cleaned
        except Exception as exc:  # noqa: BLE001
            print(f"[OpenAILLMClient] synthesize_answer failed, falling back to stub: {exc}", flush=True)
            return await self._stub.synthesize_answer(
                query,
                query_type,
                clusters,
                deflections,
                known_framings,
                research_findings,
                research_documents,
                mode=mode,
            )

    async def answer_for_region(
        self,
        query: str,
        query_type: str,
        region_name: str,
        persona_prompt: str | None,
        research_documents: list[dict],
        clusters: list[dict],
        deflections: list[dict],
        mode: ResearchMode = "medium",
    ) -> list[dict]:
        doc_index = [
            {"id": d.get("id"), "title": d.get("title"), "domain": d.get("domain"), "snippet": d.get("snippet")}
            for d in research_documents
            if isinstance(d, dict) and d.get("id") is not None
        ]
        payload = {
            "query": query,
            "query_type": query_type,
            "region": region_name,
            "research_documents": doc_index,
            "viewpoint_clusters": clusters,
            "deflections": deflections,
        }
        task = (
            f"You answer a user's question about Karnataka, India, for ONE region: {region_name}. "
            "Ground the reply in the supplied evidence: `research_documents` (mainstream and "
            "official web sources gathered for this region -- {id, title, domain, snippet}), "
            "`viewpoint_clusters` (what is being said about the topic in this region on social "
            "media and in the news -- label, summary, postCount, sources), and `deflections` "
            "(points where this region's viewpoints disagree). If the evidence is thin, say less "
            "rather than inventing.\n\n"
            "REQUIRED STRUCTURE, in this order:\n"
            "1. EXACTLY ONE `tldr` segment: the region's one-sentence answer (max ~30 words).\n"
            "2. TWO to FOUR `recommendation` segments: the core of the reply, one sentence each "
            "(max ~40 words) -- concrete actions for policy questions, distinct positions for "
            "descriptive ones.\n"
            "3. Evidence, keeping the two source types SEPARATE: zero to two `body` segments "
            "that begin 'Official & mainstream sources:' and draw ONLY on research_documents "
            "(attach their ids as `citations`), then zero to two `body` segments that begin "
            "'Social media:' and draw ONLY on viewpoint_clusters (never cite these).\n\n"
            'Respond with JSON: {"segments": [{"text": str, "kind": "tldr"|"recommendation"|'
            '"body", "clusterId": str (optional), "citations": int[] (optional)}]}. PLAIN TEXT '
            "ONLY: no markdown, no URLs, no source names inline -- use `citations`. Only cite ids "
            "present in research_documents. Do not restate the region's name as a label; the UI "
            "already shows it."
        )
        system = f"{persona_prompt}\n\n{task}" if persona_prompt else task
        data = await self._chat_json(system, json.dumps(payload), timeout=120.0)
        segments = data.get("segments")
        if not isinstance(segments, list) or not segments:
            raise ValueError(f"malformed segments: {segments!r}")
        valid_ids = {d["id"] for d in doc_index}
        cleaned: list[dict] = []
        for seg in segments:
            if not isinstance(seg, dict) or not isinstance(seg.get("text"), str):
                continue
            text = self._strip_markdown_noise(seg["text"])
            if not text:
                continue
            kind = seg.get("kind")
            out: dict = {"text": text, "kind": kind if kind in ("tldr", "recommendation", "body") else "body"}
            if isinstance(seg.get("clusterId"), str):
                out["clusterId"] = seg["clusterId"]
            if isinstance(seg.get("citations"), list):
                kept = [int(c) for c in seg["citations"] if isinstance(c, int) and c in valid_ids]
                if kept:
                    out["citations"] = kept
            cleaned.append(out)
        if not cleaned:
            raise ValueError("no usable segments")
        return cleaned

    async def compare_story_vs_official(
        self,
        query: str,
        area_label: str,
        story_points: list[str],
        official_factors: list[dict],
    ) -> dict:
        payload = {"query": query, "area": area_label, "story_points": story_points, "official_factors": official_factors}
        system = (
            f"You compare two independent accounts of '{query}' for ONE Karnataka area: {area_label}.\n\n"
            "`story_points` -- Story Mode's own reasoning: persona-written replies grounded in "
            "social media, news and web research for this specific area (may be empty if this area "
            "had no persona reply this run).\n\n"
            "`official_factors` -- UIDAI/NITI's statistical model: each row is {district, factor, "
            "value, method} naming the factor identified as most predictive of that district's "
            "dropout rate (may be empty if no row matched this area's districts). Two DIFFERENT "
            "methods appear and must NEVER be treated as comparable to each other or averaged -- "
            "read each row's own `method` string for what its `value` actually means, and never "
            "assert a statistical meaning beyond what `method` states.\n\n"
            'Respond with JSON: {"comparison": str, "consolidated_answer": str}.\n\n'
            "`comparison` (plain text, 80-150 words): where Story Mode's account and the official "
            "factor(s) agree, where they diverge, and a plausible reason why (for example Story "
            "Mode surfacing a cause the official model can't measure, like seasonal labour or "
            "language of instruction, while the official data flags a measurable infrastructure "
            "gap). If one side is empty, say so plainly in one sentence instead of comparing.\n\n"
            "`consolidated_answer` (plain text, 80-150 words): ONE coherent answer to the query for "
            "this area that genuinely draws on BOTH sources where both exist -- not a "
            "concatenation, a real synthesis. Ground every claim in the evidence given; never "
            "invent a statistic, district, or factor not present in the payload.\n\n"
            "PLAIN TEXT ONLY in both fields: no markdown, no bullet characters, no citation "
            "markers, no source names inline."
        )
        data = await self._chat_json(system, json.dumps(payload), timeout=60.0)
        comparison = data.get("comparison")
        consolidated = data.get("consolidated_answer")
        if not isinstance(comparison, str) or not isinstance(consolidated, str):
            raise ValueError(f"malformed compare_story_vs_official response: {data!r}")
        return {
            "comparison": self._strip_markdown_noise(comparison),
            "consolidated_answer": self._strip_markdown_noise(consolidated),
        }

    async def generate_verdict(
        self,
        area_kind: str,
        area_name: str,
        state_name: str,
        context: str,
    ) -> str:
        try:
            label = f"{area_name}, {state_name}" if area_kind == "district" else area_name
            data = await self._chat_json(
                "You write the 'Verdict' narrative for an Indian secondary-school-dropout data "
                "dashboard, read by education policymakers. You are given a plaintext digest of "
                "REAL, already-computed statistics for ONE specific district or state -- "
                "regression-based factor sensitivities (each factor's real share of modeled "
                "dropout impact, or its own fit quality), a prescriptive what-if scenario (what "
                "moving which factors by how much would take to hit a modeled target reduction), "
                "and budget-priority context for its state. Ground your narrative STRICTLY in "
                "this given data -- never invent demographic, cultural, historical, or causal "
                "claims that go beyond what the given numbers actually show; if the data is thin "
                "for some point, say less rather than fabricate more.\n\n"
                "Write 3 to 5 real paragraphs of plain prose (NOT bullet points, NOT a list, NOT "
                "markdown -- no **bold**, no # headings, no bullet characters), each paragraph "
                "separated by exactly one blank line. Structure:\n"
                "1. Open by naming this specific area and stating, in plain language, what the "
                "data shows are the leading real drivers of secondary-school dropout here -- name "
                "the actual top factors given and what they represent (you may phrase a given "
                "column-style factor name in natural English, e.g. treat "
                "'total_girls_func_toilet (%)' as roughly 'the share of schools with functioning "
                "girls' toilets', but do not change what it measures or invent a factor that "
                "isn't given).\n"
                "2. Explain WHY these factors plausibly drive dropout for children in this kind of "
                "area, reasoning from the factor categories given (infrastructure, digital/ICT, "
                "teacher profile, socio-economic) -- stay grounded in the given factors, do not "
                "introduce unrelated social/cultural narratives with no support in the data.\n"
                "3. Explain the prescriptive implication: what the data shows it would take (which "
                "factors, roughly how much movement) to meaningfully reduce dropout here.\n"
                "4. Close with the budget/intervention priority context given for this area's "
                "state -- where relative funding priority should concentrate and why, per the "
                "given numbers.\n\n"
                "Be specific and quantitative where the data supports it (cite real percentages, "
                "R-squared values, or rupee figures from what's given) rather than vague hedges "
                'like "various factors contribute". Respond with JSON: {"verdict": "<the full '
                'narrative, paragraphs separated by \\n\\n>"}.',
                f"Area: {label}\nArea kind: {area_kind}\n\n{context}",
                timeout=150.0,  # generous, not a fast-fail -- a real gemma_remote call for this much reasoning/text can legitimately take 15-40+s
            )
            verdict = data.get("verdict")
            if isinstance(verdict, str) and verdict.strip():
                cleaned = self._strip_markdown_noise(verdict.strip())
                if cleaned:
                    return cleaned
            raise ValueError(f"malformed verdict value: {verdict!r}")
        except Exception as exc:  # noqa: BLE001
            print(f"[OpenAILLMClient] generate_verdict failed, falling back to stub: {exc}", flush=True)
            return await self._stub.generate_verdict(area_kind, area_name, state_name, context)


class AzureAnthropicLLMClient(OpenAILLMClient):
    """LLMClient backed by Claude (via Azure AI Foundry) instead of OpenAI.

    Subclasses OpenAILLMClient and overrides only the transport-level seams
    (`_chat_json`, `embed`, `_research_one`) rather than reimplementing every
    method — every higher-level method (classify_query_type, suggest_framings,
    extract_place_mentions, geolocate, label_cluster, paraphrase,
    extract_deflection, synthesize_answer) already goes through `_chat_json`,
    so overriding that one seam swaps the provider for all of them at once
    with the exact same prompts, instead of duplicating ~500 lines of prompt
    text that would drift out of sync over time.

    Two real differences from OpenAI, both structural, not swappable by
    prompting: Claude has no `response_format=json_object` mode (handled by
    instructing + defensively stripping code fences) and no embeddings
    endpoint at all (Anthropic doesn't offer one) -- `embed()` uses a local
    sentence-transformers model instead (see `_local_embed` below), which
    also means clustering has no dependency on any provider's API/credits.
    """

    def __init__(self, settings: Settings):
        from anthropic import AsyncAnthropicFoundry  # local import: keep this optional dep lazy

        self.settings = settings
        self.client = AsyncAnthropicFoundry(
            api_key=settings.azure_anthropic_api_key,
            base_url=settings.azure_anthropic_endpoint,
        )
        self._stub = StubLLMClient()
        self._gazetteer = self._load_gazetteer()

    async def _chat_json(self, system: str, user: str, timeout: float | None = None) -> dict:
        client = self.client if timeout is None else self.client.with_options(timeout=timeout)
        resp = await client.messages.create(
            model=self.settings.azure_anthropic_deployment,
            max_tokens=4096,
            system=system + " Respond with ONLY the raw JSON object -- no markdown code "
            "fences, no other text before or after it.",
            messages=[{"role": "user", "content": user}],
        )
        if not resp.content:
            # Empty content means the safety classifier refused the input
            # (garbled/corrupted text is a known trigger) -- `content[0]`
            # would otherwise raise a bare "list index out of range" here,
            # which is indistinguishable from any other bug when it surfaces
            # in the caller's fallback-to-stub log line.
            raise RuntimeError(f"empty response content (stop_reason={resp.stop_reason!r})")
        raw = resp.content[0].text.strip()
        # Defensive: strip ```json ... ``` / ``` ... ``` fences if the model adds
        # them anyway despite the instruction above (observed to be rare, but
        # OpenAI's response_format=json_object has no Claude equivalent to
        # enforce this structurally).
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
        return json.loads(raw)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Real semantic embeddings via a local sentence-transformers model
        (see `_get_local_embedder`) -- clustering needs actual semantic
        similarity to group posts by the REASON they express, not by
        superficial token overlap. `_hash_embed` (the stub's bag-of-tokens
        hash) is a fallback of last resort here, not the intended path: it
        was empirically the cause of incoherent clusters (posts grouped by
        shared common words rather than shared viewpoint) before this was
        wired in."""
        try:
            return await _local_semantic_embed(texts)
        except Exception as exc:  # noqa: BLE001
            print(f"[AzureAnthropicLLMClient] local embedding failed, falling back to hash: {exc}", flush=True)
            return [_hash_embed(t) for t in texts]

    async def _research_one(self, subquery: str, wordcount_hint: str) -> tuple[str, list[dict]]:
        """One web-search-grounded call via Claude's native web_search tool.
        Unlike OpenAI's url_citation annotations (harvested separately from
        the text), Claude attaches `citations` directly to each text block --
        walking every text block's citations is both the harvesting AND the
        text-collection pass."""
        try:
            research_client = self.client.with_options(timeout=90.0)
            resp = await research_client.messages.create(
                model=self.settings.azure_anthropic_deployment,
                max_tokens=1500,
                tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}],
                messages=[
                    {
                        "role": "user",
                        "content": (
                            "You are researching an Indian public-affairs / cultural topic for a "
                            "dashboard that will cite your sources back to the user. Use the "
                            "web_search tool to gather substantive, current, ideally India-specific "
                            f"information. {_OFFICIAL_SOURCE_BIAS} Write a concise, factual "
                            f"summary ({wordcount_hint}) grounded in what you found. Cite specific "
                            f"numbers, dates, and sources.\n\nTopic / angle: {subquery}"
                        ),
                    }
                ],
            )
            text_parts: list[str] = []
            docs: list[dict] = []
            seen_urls: set[str] = set()
            for block in resp.content:
                if getattr(block, "type", None) != "text":
                    continue
                text_parts.append(block.text)
                for cit in getattr(block, "citations", None) or []:
                    url = getattr(cit, "url", None)
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)
                    title = (getattr(cit, "title", None) or url).strip()
                    clean_url = self._strip_tracking_params(url)
                    docs.append(
                        {
                            "url": clean_url,
                            "title": title[:200],
                            "domain": self._domain_of(clean_url),
                            # No page body available: Claude's citation objects
                            # carry only url/title, unlike the search-API
                            # providers whose results include `content`. So
                            # there's no `geo_text` to emit here (see
                            # _GEO_TEXT_CHARS) -- research-derived posts from
                            # this provider fall back to title+snippet for
                            # place extraction, which resolves fewer of them.
                            "snippet": "",  # filled in by the caller from `text` if needed
                        }
                    )
            return "".join(text_parts), docs
        except Exception as exc:  # noqa: BLE001
            print(f"[AzureAnthropicLLMClient] research call for {subquery!r} failed: {exc}", flush=True)
            return "", []

# One function-tool offered to local models during research() -- executed
# against Ollama's own hosted web-search API (see _web_search below), since
# local models have no hosted search tool the way Claude/OpenAI do.
_OLLAMA_WEB_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Search the web for current information relevant to a query.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query."},
            },
            "required": ["query"],
        },
    },
}

# Hard cap on tool-use rounds within one _research_one call. Small local
# models are known to sometimes keep re-calling tools instead of terminating
# -- the round AFTER this cap is hit is forced into a plain-text-only turn
# (see _research_one) rather than looping indefinitely.
_RESEARCH_TOOL_ROUND_CAP = 2


class LocalOllamaLLMClient(OpenAILLMClient):
    """LLMClient backed by a local model served by Ollama (gemma4:e4b or
    mistral:7b -- see reasoning_modes.OLLAMA_MODEL_TAGS), instead of a hosted
    API. Zero per-call cost, but needs a locally-running `ollama serve` and
    the model tag already pulled.

    Subclasses OpenAILLMClient for the same reason RemoteGemmaLLMClient does
    -- every _chat_json-based method (classify_query_type, suggest_framings,
    extract_place_mentions, geolocate, label_cluster, paraphrase,
    extract_deflection, synthesize_answer) is reused unchanged.

    Uses Ollama's NATIVE `/api/chat` endpoint throughout, not its
    OpenAI-compatible `/v1/chat/completions` shim: (1) the native `format`
    param does real grammar-constrained JSON decoding, meaningfully more
    reliable for small local models than an OpenAI-style
    `response_format=json_object` soft ask, and (2) at the time this was
    written, gemma4:e4b's tool_calls were not reliably recognized when
    streamed through Ollama's OpenAI-compat layer (a known upstream issue) --
    the native endpoint's own `tools` param avoids that entirely.
    """

    # Ollama serves each local model from ONE process with concurrency 1 by
    # default -- unlike the hosted providers this class stands in for, a
    # local model can't fan out. Pipeline stages fire several _chat_json
    # calls concurrently per batch (e.g. resolve_regions' per-post
    # extract_place_mentions/geolocate, up to 10 at once) -- without a
    # client-side limit, all of them start their own httpx call (and their
    # own timeout clock) at once, so calls queued behind others on the Ollama
    # side can blow past a timeout that looked generous when the request
    # started. `_semaphore` bounds how many of THIS client's requests are
    # actually in flight at once, so a queued call's timeout clock starts
    # when it actually begins, not when every sibling call also started.
    # Every caller still has a per-call stub fallback on top of this, so a
    # genuine timeout still degrades gracefully either way.
    _DEFAULT_TIMEOUT = 120.0
    _MAX_CONCURRENT_REQUESTS = 2

    def __init__(self, settings: Settings, model_tag: str):
        import asyncio as _asyncio
        import httpx  # local import: keep this optional dep lazy, same pattern as openai/anthropic SDKs above

        self.settings = settings
        self.model_tag = model_tag
        self._client = httpx.AsyncClient(base_url=settings.ollama_base_url, timeout=self._DEFAULT_TIMEOUT)
        self._semaphore = _asyncio.Semaphore(self._MAX_CONCURRENT_REQUESTS)
        self._stub = StubLLMClient()
        self._gazetteer = self._load_gazetteer()

    async def _chat_json(self, system: str, user: str, timeout: float | None = None) -> dict:
        async with self._semaphore:
            resp = await self._client.post(
                "/api/chat",
                json={
                    "model": self.model_tag,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "format": "json",
                    "stream": False,
                    "options": {"temperature": 0.2},
                },
                timeout=timeout or self._DEFAULT_TIMEOUT,
            )
        resp.raise_for_status()
        data = resp.json()
        content = (data.get("message") or {}).get("content") or ""
        if not content.strip():
            raise RuntimeError(f"empty response content (done_reason={data.get('done_reason')!r})")
        return json.loads(content)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Local models have no embeddings endpoint wired up here either --
        same local sentence-transformers path as RemoteGemmaLLMClient."""
        try:
            return await _local_semantic_embed(texts)
        except Exception as exc:  # noqa: BLE001
            print(f"[LocalOllamaLLMClient] local embedding failed, falling back to hash: {exc}", flush=True)
            return [_hash_embed(t) for t in texts]

    async def _web_search(self, query: str, max_results: int = _WEB_SEARCH_MAX_RESULTS) -> list[dict]:
        """Ollama's own hosted web-search API -- the "real, free, reliable"
        search backend local models need since they have no built-in search
        tool. Passing an absolute URL to a client with a different base_url
        works fine in httpx (it bypasses base_url join for absolute URLs)."""
        return await _ollama_web_search(
            self._client, self.settings.ollama_web_search_api_key, query, max_results
        )

    async def _research_one(self, subquery: str, wordcount_hint: str) -> tuple[str, list[dict]]:
        """Manual tool-use loop against Ollama's native /api/chat, offering
        one `web_search` tool executed against Ollama's hosted search API.
        Capped at _RESEARCH_TOOL_ROUND_CAP rounds; the round after the cap is
        hit drops the tool entirely and forces a plain-text summary instead,
        since small models sometimes keep re-calling tools rather than
        terminating on their own."""
        if not self.settings.has_ollama_web_search:
            # No hosted-search credential configured yet -- same honest-empty
            # behavior as every other missing-credential path in this
            # codebase (never fabricate a summary/citations).
            return "", []
        try:
            messages: list[dict] = [
                {
                    "role": "system",
                    "content": (
                        "You are researching an Indian public-affairs / cultural topic for a "
                        "dashboard that will cite your sources back to the user. Use the "
                        "web_search tool (one or more times) to gather substantive, current, "
                        f"ideally India-specific information. {_OFFICIAL_SOURCE_BIAS} Once you "
                        "have enough, respond in plain text (no more tool calls) with a concise, "
                        f"factual summary ({wordcount_hint}) grounded in what you found, citing "
                        "specific numbers, dates, and sources by name."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Topic / angle: {subquery}\n\n"
                        "Call the web_search tool now to research this topic."
                    ),
                },
            ]
            docs: list[dict] = []
            seen_urls: set[str] = set()
            text = ""
            for round_num in range(_RESEARCH_TOOL_ROUND_CAP + 1):
                forced_final = round_num == _RESEARCH_TOOL_ROUND_CAP
                if forced_final:
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "Answer in plain text now, summarizing what you found so far. "
                                "Do not call any more tools."
                            ),
                        }
                    )
                async with self._semaphore:
                    resp = await self._client.post(
                        "/api/chat",
                        json={
                            "model": self.model_tag,
                            "messages": messages,
                            "tools": [] if forced_final else [_OLLAMA_WEB_SEARCH_TOOL],
                            "stream": False,
                        },
                        timeout=90.0,
                    )
                resp.raise_for_status()
                data = resp.json()
                message = data.get("message") or {}
                tool_calls = message.get("tool_calls") or []
                content = (message.get("content") or "").strip()

                if not tool_calls:
                    text = content
                    break

                messages.append(message)
                for call in tool_calls:
                    fn = call.get("function") or {}
                    args = fn.get("arguments") or {}
                    search_query = args.get("query") or subquery
                    results = await self._web_search(search_query)
                    for r in results:
                        url = r.get("url")
                        if not url or url in seen_urls:
                            continue
                        seen_urls.add(url)
                        docs.append(
                            {
                                "url": self._strip_tracking_params(url),
                                "title": (r.get("title") or url)[:200],
                                "domain": self._domain_of(url),
                                "snippet": (r.get("content") or "")[:220],
                                # Longer copy of the same content, used ONLY
                                # for geography extraction (see research.py's
                                # _posts_from_research_documents) -- `snippet`
                                # stays short because it's what the UI renders
                                # under each source. Not part of the
                                # ResearchDocument wire model, which ignores
                                # extra keys, so this never reaches the client.
                                "geo_text": (r.get("content") or "")[:_GEO_TEXT_CHARS],
                            }
                        )
                    messages.append(
                        {
                            "role": "tool",
                            "content": json.dumps(results)[:4000],
                            "name": "web_search",
                        }
                    )
            if not text:
                # The model never produced usable plain text (e.g. a
                # tool-call-only turn even on the forced-final round) -- same
                # honest-empty fallback as every other research failure path.
                return "", []
            return text, docs
        except Exception as exc:  # noqa: BLE001
            print(f"[LocalOllamaLLMClient] research call for {subquery!r} failed: {exc}", flush=True)
            return "", []


class RemoteGemmaLLMClient(OpenAILLMClient):
    """LLMClient backed by a self-hosted, genuinely OpenAI-compatible Gemma
    server (see config.Settings.remote_gemma_base_url) -- NOT Ollama-native,
    unlike LocalOllamaLLMClient above. Confirmed live: POST /v1/chat/completions
    with response_format={"type": "json_object"} returns clean, parseable JSON,
    so _chat_json below is a near-verbatim copy of OpenAILLMClient's own (just
    a different client/model) -- no fence-stripping workaround needed.

    One confirmed, structural (not transient) gap on this server, designed
    around rather than retried: POST /v1/embeddings fails server-side
    regardless of input shape ("Embedding generation failed: 'query'") --
    embed() goes straight to the same local sentence-transformers fallback
    LocalOllamaLLMClient uses, never attempting the doomed network call first.

    Also confirmed: this server itself has NO built-in web-search tool (POST
    /v1/responses 404s) -- but unlike the embeddings gap, that's not a dead
    end for research(). _research_one below runs a manual tool-use loop
    (confirmed live: this server returns well-formed OpenAI-style
    `tool_calls`, unlike the embeddings gap which is a genuine dead end) --
    same shape as LocalOllamaLLMClient's own loop, offering one `web_search`
    tool executed against Ollama's hosted web-search API (already configured
    via settings.ollama_web_search_api_key for LocalOllamaLLMClient, reused
    here verbatim) each time the model calls it, biased toward official
    Indian government/statistical sources via _OFFICIAL_SOURCE_BIAS in the
    system prompt. Capped at _RESEARCH_TOOL_ROUND_CAP rounds, same reasoning
    as LocalOllamaLLMClient's identical cap.

    Does NOT read settings.openai_chat_model / settings.openai_api_key --
    Settings is an @lru_cache singleton shared across concurrent requests, so
    a provider swap must never mutate a shared field; the model tag is an
    instance attribute instead, same as LocalOllamaLLMClient's model_tag.
    """

    # Single-box concurrency at this remote server was flagged as unvalidated
    # risk when this class was first built and left unaddressed -- research()
    # fanning out up to `breadth` (10 at extrahigh) concurrent _research_one
    # calls, layered on top of the pipeline's other per-batch/per-cluster
    # fan-outs already hitting this same box, makes that risk concrete now.
    # Bounds how many of THIS client's requests are in flight at once;
    # starts conservative, tune up once real load-tested against this box.
    _MAX_CONCURRENT_REQUESTS = 6

    def __init__(self, settings: Settings):
        import asyncio as _asyncio

        import httpx  # local import: keep this optional dep lazy, same pattern as openai/anthropic SDKs above
        from openai import AsyncOpenAI

        if not settings.remote_gemma_base_url:
            raise RuntimeError(
                "REMOTE_GEMMA_BASE_URL is not set in backend/.env. This must point "
                "at your own self-hosted, OpenAI-compatible Gemma server -- ask a "
                "team member for the address (it is intentionally not committed "
                "anywhere, since the server requires no auth)."
            )

        self.settings = settings
        self.client = AsyncOpenAI(
            base_url=f"{settings.remote_gemma_base_url}/v1",
            # Direct-to-server: any value is fine, it takes no auth. Via
            # proxy/: must be the shared passphrase (remote_gemma_api_key),
            # sent as this Bearer token and checked there.
            api_key=settings.remote_gemma_api_key or "not-needed",
            timeout=30.0,
            max_retries=1,
        )
        self._model = settings.remote_gemma_chat_model
        self._semaphore = _asyncio.Semaphore(self._MAX_CONCURRENT_REQUESTS)
        # Separate plain httpx client for Ollama's hosted web-search API --
        # unrelated host/auth scheme from self.client's AsyncOpenAI, which is
        # pinned at remote_gemma_base_url.
        self._http = httpx.AsyncClient()
        self._stub = StubLLMClient()
        self._gazetteer = self._load_gazetteer()

    async def _chat_json(self, system: str, user: str, timeout: float | None = None) -> dict:
        client = self.client if timeout is None else self.client.with_options(timeout=timeout)
        async with self._semaphore:
            resp = await client.chat.completions.create(
                model=self._model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
        return json.loads(resp.choices[0].message.content)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            return await _local_semantic_embed(texts)
        except Exception as exc:  # noqa: BLE001
            print(f"[RemoteGemmaLLMClient] local embedding failed, falling back to hash: {exc}", flush=True)
            return [_hash_embed(t) for t in texts]

    async def _web_search(self, query: str, max_results: int = _WEB_SEARCH_MAX_RESULTS) -> list[dict]:
        """Ollama's own hosted web-search API -- see LocalOllamaLLMClient's
        identical method for the full rationale. Uses this class's own httpx
        client (self._http), not Ollama's native /api/chat base_url, since
        this class has no local Ollama connection at all otherwise."""
        return await _ollama_web_search(
            self._http, self.settings.ollama_web_search_api_key, query, max_results
        )

    async def _research_one(self, subquery: str, wordcount_hint: str) -> tuple[str, list[dict]]:
        """Manual tool-use loop via native OpenAI-SDK tool-calling (confirmed
        live against this server: a `tools=[...]` request returns a
        well-formed `tool_calls` array, finish_reason="tool_calls") --
        structurally the same loop as LocalOllamaLLMClient._research_one, just
        driven through the OpenAI SDK's message/tool_call shapes instead of
        Ollama's native ones. Reuses _OLLAMA_WEB_SEARCH_TOOL/
        _RESEARCH_TOOL_ROUND_CAP (module-level, defined above
        LocalOllamaLLMClient) verbatim -- same tool, same round cap, same
        reasoning for both."""
        if not self.settings.has_ollama_web_search:
            # No hosted-search credential configured -- same honest-empty
            # behavior as every other missing-credential path in this codebase
            # (never fabricate a summary/citations).
            return "", []
        try:
            messages: list[dict] = [
                {
                    "role": "system",
                    "content": (
                        "You are researching an Indian public-affairs / cultural topic for a "
                        "dashboard that will cite your sources back to the user. Use the "
                        "web_search tool (one or more times) to gather substantive, current, "
                        f"ideally India-specific information. {_OFFICIAL_SOURCE_BIAS} Once you "
                        "have enough, respond in plain text (no more tool calls) with a concise, "
                        f"factual summary ({wordcount_hint}) grounded in what you found, citing "
                        "specific numbers, dates, and sources by name."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Topic / angle: {subquery}\n\n"
                        "Call the web_search tool now to research this topic."
                    ),
                },
            ]
            docs: list[dict] = []
            seen_urls: set[str] = set()
            text = ""
            research_client = self.client.with_options(timeout=90.0)
            for round_num in range(_RESEARCH_TOOL_ROUND_CAP + 1):
                forced_final = round_num == _RESEARCH_TOOL_ROUND_CAP
                if forced_final:
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "Answer in plain text now, summarizing what you found so far. "
                                "Do not call any more tools."
                            ),
                        }
                    )
                async with self._semaphore:
                    resp = await research_client.chat.completions.create(
                        model=self._model,
                        messages=messages,
                        tools=[] if forced_final else [_OLLAMA_WEB_SEARCH_TOOL],
                    )
                message = resp.choices[0].message
                tool_calls = message.tool_calls or []
                content = (message.content or "").strip()

                if not tool_calls:
                    text = content
                    break

                messages.append(
                    {
                        "role": "assistant",
                        "content": message.content,
                        "tool_calls": [
                            {
                                "id": call.id,
                                "type": "function",
                                "function": {
                                    "name": call.function.name,
                                    "arguments": call.function.arguments,
                                },
                            }
                            for call in tool_calls
                        ],
                    }
                )
                for call in tool_calls:
                    try:
                        args = json.loads(call.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    search_query = args.get("query") or subquery
                    results = await self._web_search(search_query)
                    for r in results:
                        url = r.get("url")
                        if not url or url in seen_urls:
                            continue
                        seen_urls.add(url)
                        docs.append(
                            {
                                "url": self._strip_tracking_params(url),
                                "title": (r.get("title") or url)[:200],
                                "domain": self._domain_of(url),
                                "snippet": (r.get("content") or "")[:220],
                                # Longer copy of the same content, used ONLY
                                # for geography extraction (see research.py's
                                # _posts_from_research_documents) -- `snippet`
                                # stays short because it's what the UI renders
                                # under each source. Not part of the
                                # ResearchDocument wire model, which ignores
                                # extra keys, so this never reaches the client.
                                "geo_text": (r.get("content") or "")[:_GEO_TEXT_CHARS],
                            }
                        )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": json.dumps(results)[:4000],
                        }
                    )
            if not text:
                # The model never produced usable plain text (e.g. a
                # tool-call-only turn even on the forced-final round) -- same
                # honest-empty fallback as every other research failure path.
                return "", []
            return text, docs
        except Exception as exc:  # noqa: BLE001
            print(f"[RemoteGemmaLLMClient] research call for {subquery!r} failed: {exc}", flush=True)
            return "", []


def get_llm_client(settings: Settings, provider: LlmProvider | None = None) -> LLMClient:
    """`provider` overrides `settings.llm_provider` for this one call --
    constructs a fresh client instance every time (no singleton/caching), so
    making the provider a per-request value has no concurrency implications.
    """
    resolved = provider or settings.llm_provider
    if resolved in OLLAMA_MODEL_TAGS:
        return LocalOllamaLLMClient(settings, OLLAMA_MODEL_TAGS[resolved])
    if resolved == "gemma_remote":
        # Checked before has_llm below on purpose -- this provider needs no
        # credential (has_llm only checks the OpenAI key), so a fresh install
        # with zero keys configured must still be able to select it.
        return RemoteGemmaLLMClient(settings)
    if resolved == "azure_anthropic":
        # Gated on has_azure_anthropic, NOT the generic has_llm: has_llm
        # resolves against settings.llm_provider (the env DEFAULT), not the
        # per-request `resolved` provider, so with a non-Claude default it
        # reports on the OpenAI key instead -- selecting Claude per-request
        # would then be admitted (or refused) based on entirely the wrong
        # credential. Check this provider's own credential directly.
        if settings.has_azure_anthropic:
            return AzureAnthropicLLMClient(settings)
        if settings.allow_stub_fallback:
            return StubLLMClient()
        raise RuntimeError(
            "Provider 'azure_anthropic' was selected but AZURE_ANTHROPIC_API_KEY / "
            "AZURE_ANTHROPIC_ENDPOINT are not both set in backend/.env."
        )
    if settings.has_llm:
        return OpenAILLMClient(settings)
    if settings.allow_stub_fallback:
        return StubLLMClient()
    # Unlike Reddit/YouTube (additive data sources), the LLM drives clustering,
    # resolution, and synthesis -- there's no meaningful way to "skip" it, so
    # fail loudly rather than silently degrade to fabricated stub reasoning.
    raise RuntimeError(
        "OPENAI_API_KEY is not set and ALLOW_STUB_FALLBACK is false. "
        "Set OPENAI_API_KEY in backend/.env, or set ALLOW_STUB_FALLBACK=true "
        "to run on the deterministic stub LLM instead."
    )
