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

import hashlib
import json
import re
from collections import Counter

from ..config import DATA_DIR, Settings
from ..reasoning_modes import OLLAMA_MODEL_TAGS, RESEARCH_WORDCOUNT_HINT, LlmProvider, ResearchMode
from .base import LLMClient

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


def _get_local_embedder():
    """Loaded once per process -- constructing a SentenceTransformer parses
    model weights from disk and is too slow to redo per call. Used by
    AzureAnthropicLLMClient.embed() since Anthropic has no embeddings
    endpoint of its own; running the model locally means clustering has no
    dependency on any provider's API being up or funded, unlike routing
    embeddings through a second LLM provider's account."""
    global _local_embedder
    if _local_embedder is None:
        from sentence_transformers import SentenceTransformer  # local import: keep this optional dep lazy

        _local_embedder = SentenceTransformer("all-MiniLM-L6-v2")
    return _local_embedder


async def _local_semantic_embed(texts: list[str]) -> list[list[float]]:
    """Shared body for every embed() override with no hosted embeddings
    endpoint of its own (Claude, and now the local Ollama providers) -- one
    lazy-loaded sentence-transformers singleton (_get_local_embedder) instead
    of duplicating this per class. Raises on failure; callers catch and fall
    back to `_hash_embed`."""
    import asyncio as _asyncio

    model = _get_local_embedder()
    # .encode() is a synchronous, CPU-bound call -- run it off the event loop
    # rather than blocking every other in-flight request.
    vectors = await _asyncio.to_thread(model.encode, texts)
    return [vec.tolist() for vec in vectors]


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

        path = os.path.join(DATA_DIR, "district_gazetteer.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
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
                "You know Indian regional, cultural, and religious variation well. Given a "
                "topic, list the distinct, well-known regional/cultural/religious framings or "
                "interpretations of it across India -- the kind of substantive differences a "
                "well-informed person from each region would actually state (e.g. for 'Diwali': "
                "Rama's return to Ayodhya in the North, Krishna defeating Narakasura in the "
                "South, Kali Puja in Bengal, Lakshmi puja marking the new year in Gujarat, "
                "Bandi Chhor Divas for Sikhs, Mahavira's nirvana for Jains). Each phrase should "
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
                    "tool to gather substantive, current, ideally India-specific information "
                    "from reputable sources (government reports, major news outlets, NGO briefs, "
                    f"academic sources). Write a concise, factual summary ({wordcount_hint}) "
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
                "Extract every Indian place name mentioned in the user's text — city, district, "
                'or state names only. Respond with JSON: {"places": ["...", ...]}. Return an '
                "empty list if none are mentioned.",
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
            payload = {
                "query": query,
                "query_type": query_type,
                "clusters": clusters,
                "deflections": deflections,
                "known_framings": known_framings,
                "research_findings": research_findings,
                "research_documents": doc_index,
            }
            if mode == "extrahigh":
                # Each cluster entry in `clusters` now carries a `stateCode`
                # (None for every other mode) since extrahigh clusters each
                # state's posts independently instead of pooling them into one
                # global set — widen the requested structure accordingly so
                # the answer actually reflects that much larger, state-grouped
                # input instead of collapsing it into today's ~3-5 bullets.
                structure_instructions = (
                    "REQUIRED STRUCTURE — exactly this shape, in this order:\n"
                    "1. EXACTLY ONE `tldr` segment: a single sentence (max ~30 words) giving the "
                    "core takeaway. This is the headline answer — make it specific and substantive, "
                    "not a restatement of the question.\n"
                    "2. SIX to TWELVE `recommendation` segments: tight, scannable bullets, each ONE "
                    "sentence (max ~35 words). Each cluster below carries a `stateCode` — name "
                    "specific states/regions directly (e.g. 'In Kerala...', 'In Punjab...') rather "
                    "than defaulting to one national-average framing; prioritize genuinely "
                    "different positions across regions over repeating a dominant one, since this "
                    "mode exists to surface the broadest plural view, not a condensed summary. Set "
                    "`region` to the relevant state/region name, `clusterId` when it maps to a "
                    "specific cluster.\n"
                    "3. FOUR to SIX `detail` segments: the fuller analysis, one paragraph each "
                    "(~60–90 words). These are collapsed behind a 'Full analysis' toggle, so this "
                    "is where depth, numbers, and regional nuance belong.\n\n"
                )
            else:
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
                            "information from reputable sources (government reports, major news "
                            "outlets, NGO briefs, academic sources). Write a concise, factual "
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

    Subclasses OpenAILLMClient for the same reason AzureAnthropicLLMClient
    does -- every _chat_json-based method (classify_query_type,
    suggest_framings, extract_place_mentions, geolocate, label_cluster,
    paraphrase, extract_deflection, synthesize_answer) is reused unchanged.

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
    # calls concurrently per batch (e.g. resolve_district's per-post
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
        same local sentence-transformers path as AzureAnthropicLLMClient."""
        try:
            return await _local_semantic_embed(texts)
        except Exception as exc:  # noqa: BLE001
            print(f"[LocalOllamaLLMClient] local embedding failed, falling back to hash: {exc}", flush=True)
            return [_hash_embed(t) for t in texts]

    async def _web_search(self, query: str, max_results: int = 5) -> list[dict]:
        """Ollama's own hosted web-search API -- the "real, free, reliable"
        search backend local models need since they have no built-in search
        tool. Passing an absolute URL to a client with a different base_url
        works fine in httpx (it bypasses base_url join for absolute URLs)."""
        resp = await self._client.post(
            "https://ollama.com/api/web_search",
            json={"query": query, "max_results": max_results},
            headers={"Authorization": f"Bearer {self.settings.ollama_web_search_api_key}"},
            timeout=30.0,
        )
        resp.raise_for_status()
        results = resp.json().get("results")
        return results if isinstance(results, list) else []

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
                        "ideally India-specific information from reputable sources (government "
                        "reports, major news outlets, NGO briefs, academic sources). Once you "
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


def get_llm_client(settings: Settings, provider: LlmProvider | None = None) -> LLMClient:
    """`provider` overrides `settings.llm_provider` for this one call --
    constructs a fresh client instance every time (no singleton/caching), so
    making the provider a per-request value has no concurrency implications.
    """
    resolved = provider or settings.llm_provider
    if resolved in OLLAMA_MODEL_TAGS:
        return LocalOllamaLLMClient(settings, OLLAMA_MODEL_TAGS[resolved])
    if settings.has_llm:
        if resolved == "azure_anthropic":
            return AzureAnthropicLLMClient(settings)
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
