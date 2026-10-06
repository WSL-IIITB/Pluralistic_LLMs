"""
Connector interfaces — the frozen contract every source/LLM connector
implements. Each has a `Stub*` implementation (deterministic fixture data, zero
external calls) and a real implementation gated by `config.Settings.has_*`;
`connectors/__init__.py` picks the real one automatically when credentials are
present and falls back to the stub otherwise.
"""

from __future__ import annotations

from typing import Protocol, TypedDict

from ..reasoning_modes import ResearchMode


class SourcedPost(TypedDict):
    id: str
    platform: str  # "reddit" | "youtube"
    text: str
    source_hint: str  # subreddit name, or "channel · video title" for YouTube
    permalink: str | None


class SourceConnector(Protocol):
    """A post source (Reddit, YouTube, ...)."""

    async def search(self, query: str, limit: int) -> list[SourcedPost]:
        """Return up to `limit` posts/comments relevant to `query`."""
        ...


class LLMClient(Protocol):
    """
    Every LLM-touching operation the pipeline needs, behind one seam so the
    provider (OpenAI today) or a deterministic stub can be swapped freely.
    Confidence values returned must be one of ConfidenceTier ("high"|"medium"|"low").
    """

    async def classify_query_type(self, query: str) -> str:
        """Return "descriptive" or "policy"."""
        ...

    async def suggest_framings(self, query: str, max_count: int) -> list[str]:
        """
        Return up to `max_count` short, search-friendly phrases capturing the
        distinct, well-known regional/cultural/ideological framings or
        interpretations of `query` in the Indian context -- e.g. for "Diwali":
        ["Ram Ayodhya return", "Narakasura Krishna", "Kali Puja Bengal",
        "Lakshmi puja Gujarat new year", "Bandi Chhor Divas Sikh", "Mahavira
        nirvana Jain"]. This is what makes the sourcing stage search for the
        SUBSTANCE of regional variation, not just the bare topic + a place
        name -- without it, a generic query mostly surfaces generic reactions/
        opinions rather than content that actually articulates why regions
        differ. Return an empty list if the topic has no well-known distinct
        regional framings (the caller then falls back to the bare query).
        """
        ...

    async def extract_place_mentions(self, text: str) -> list[str]:
        """Return place names mentioned in `text` (district/city/state names)."""
        ...

    async def geolocate(self, text: str, source_hint: str) -> tuple[str | None, str]:
        """
        Last-resort LLM geolocation. Returns (district_id_or_none, confidence).
        `district_id_or_none` should be a real id from the gazetteer, or None.
        """
        ...

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embeddings for clustering, one vector per input text."""
        ...

    async def label_cluster(self, sample_texts: list[str]) -> tuple[str, str]:
        """Return (label, one-line summary) for a cluster given sample post texts."""
        ...

    async def paraphrase(self, text: str) -> str:
        """Paraphrase a post for safe display (never show verbatim user text)."""
        ...

    async def research(
        self,
        query: str,
        known_framings: list[str],
        breadth: int,
        mode: ResearchMode,
    ) -> tuple[str, list[dict]]:
        """
        Web-search-grounded research on `query`. Runs before clustering so the
        synthesis stage can ground its answer in citable external sources
        (essential for policy queries where social-media chatter alone is
        thin: e.g. "high-school dropouts: where should government intervene?"
        has almost no rich signal in Reddit/YouTube comments, but has a wealth
        of government reports, news articles, and NGO briefs on the open web).

        `known_framings` (from suggest_framings, possibly empty) act as
        angles/subqueries -- if non-empty, the implementation should fire one
        research call per framing; if empty, it should decompose `query`
        internally into `breadth` search-friendly sub-questions first.

        `mode` (basic/medium/high, see reasoning_modes.py) does NOT change how
        many angles get searched (that's `breadth`/`known_framings`) -- it
        scales how thorough each individual angle's write-up is asked to be
        (reasoning_modes.RESEARCH_WORDCOUNT_HINT), since longer requested
        write-ups correlate with more sources actually read and cited.

        Returns (findings_summary, documents) where `documents` is a list of
        ResearchDocument-shaped dicts {id, url, title, domain, snippet}, with
        `id` a 1-based ordering within this call. The findings_summary is a
        compact plaintext digest the synthesis stage can ground on directly
        without re-reading every source; documents carry the URL citations
        the UI renders.

        Stub implementations MUST return ("", []) — do not fabricate URLs
        (that would be far more misleading than empty research for a stub).
        """
        ...

    async def extract_deflection(
        self,
        cluster_a_label: str,
        cluster_a_texts: list[str],
        cluster_b_label: str,
        cluster_b_texts: list[str],
    ) -> tuple[str, str]:
        """Return (point_of_deflection, confidence) for a co-occurring cluster pair."""
        ...

    async def judge_text_relevance(self, question: str) -> bool:
        """Generic yes/no judgment call, phrased as a plain question expecting
        exactly "yes" or "no" (build.py's per-post relevance gate). Fails
        CLOSED (returns False) on any error."""
        ...

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
        """
        `known_framings` (from suggest_framings, possibly empty) are well-known
        regional/cultural framings of the topic -- ground the answer in these
        where they're consistent with what the clusters actually found, so the
        synthesis can state real regional/religious substance directly rather
        than only whatever hedged phrasing the noisy scraped clusters produced.
        Never state a framing the clustered data contradicts or that has no
        support in `clusters`/`deflections`.

        `research_findings` is a plaintext digest from the web-search stage;
        `research_documents` is the ordered list of ResearchDocument-shaped
        dicts (with 1-based `id`s) that produced it. When a claim comes
        primarily from web research, set `citations` on the AnswerSegment to
        the relevant document ids so the UI can render them. Prefer answering
        from BOTH the clustered social-media viewpoints AND the researched
        sources: the clusters tell you what people actually SAY, the sources
        tell you what's TRUE / OFFICIAL / MEASURED -- combine them.

        `mode` is additive/defaulted so every implementation keeps working
        without overriding this method -- "extrahigh" clusters carry a
        `stateCode` key (None for every other mode) and implementations may
        use `mode` to ask for a broader, more region-explicit answer shape.

        Return a list of AnswerSegment-shaped dicts:
        {"text": str, "kind": "heading"|"body"|"recommendation", "clusterId"?: str, "region"?: str, "citations"?: list[int]}
        """
        ...

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
        """One Karnataka region's persona reply to `query` (`persona_prompt`
        from data/personas via karnataka.build_persona_prompt), grounded in
        that region's evidence. Returns AnswerSegment-shaped dicts
        ({text, kind: "tldr"|"recommendation"|"body", clusterId?, citations?}).
        Raises on failure instead of falling back to stub text: a fabricated
        reply would silently misrepresent what that persona actually said."""
        ...

    async def compare_story_vs_official(
        self,
        query: str,
        area_label: str,
        story_points: list[str],
        official_factors: list[dict],
    ) -> dict:
        """Compares Story Mode's own reasoning (`story_points` -- this area's
        persona reply texts, or the Karnataka-wide overview for the statewide
        call) against the UIDAI/NITI official dominant-factor rows for this
        area's districts (`official_factors`, each {district, factor, value,
        method} -- see ../niti_factors.py for what `method` means; NEVER treat
        the two methods' `value`s as comparable to each other, and never
        invent a statistical meaning for `value` beyond what `method` states).

        Either list may be empty (no persona reply yet for a region, or no
        NITI row matched its districts) -- work with whichever evidence is
        actually present rather than fabricating the other side.

        Return {"comparison": str, "consolidated_answer": str}:
        - `comparison`: a short, plain-language account of where Story Mode's
          social/persona-driven account and the official statistical factor(s)
          agree, where they diverge, and why that might be (e.g. Story Mode
          surfaces a cause the official model can't measure, like cane-harvest
          labour, while the official data flags a measurable infrastructure
          gap). If one side is empty, say so plainly instead of comparing.
        - `consolidated_answer`: one coherent answer to `query` for this area
          that actually draws on BOTH sources where both exist -- not a
          concatenation of the two, a genuine synthesis. Ground every claim in
          the evidence given; never invent a statistic beyond it.
        Raises on failure -- a fabricated comparison would misrepresent both
        sources."""
        ...

    async def generate_verdict(
        self,
        area_kind: str,
        area_name: str,
        state_name: str,
        context: str,
    ) -> str:
        """Data View's "verdict" narrative (see dataview/router.py's
        `/district/{id}/verdict` and `/state/{code}/verdict`). `area_kind` is
        "district" or "state"; `context` is a plaintext digest (built by
        dataview/verdict.py, ZERO LLM involvement in building it) of that
        area's own real computed regression/prescriptive/budget numbers --
        the SAME numbers the Verdict page's Major-factors table and the
        Intervention & Budget tab already show for this area.

        Return a detailed, multi-paragraph natural-language narrative (plain
        text, paragraphs separated by "\\n\\n") explaining WHY children in
        this area are dropping out of secondary school, grounded STRICTLY in
        `context` -- never fabricate demographic/cultural claims beyond what
        the given numbers show. This is a real, possibly slow (15-40+s) LLM
        call; implementations must use a generous timeout on their own HTTP
        client rather than fast-failing (see OpenAILLMClient.generate_verdict's
        explicit `timeout=` override on `_chat_json`, mirroring
        synthesize_answer's own pattern for its large-payload call)."""
        ...
