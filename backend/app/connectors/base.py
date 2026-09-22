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
    platform: str  # "reddit" | "youtube" | "niti"
    text: str
    source_hint: str  # subreddit name, "channel · video title" for YouTube, or the NITI dataset label
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

    async def propose_regions(self, groups: list[dict]) -> list[dict]:
        """
        extrahigh-mode-only, region-inference stage (see
        graph/nodes/infer_regions.py). `groups` are NUMERIC partitions of
        resolved districts (silhouette-swept district-averaged-embedding
        clusters, computed with zero LLM involvement) -- this call's ONLY job
        is to name and justify each group, never to repartition districts
        itself. Each entry: {"group_index": int, "districts": [{"district_id",
        "district_name", "state_name", "state_code", "centroid": [lng, lat]},
        ...], "sample_texts": [str, ...]}.

        Return exactly one entry per input group (same group_index set, no
        additions/omissions): {"group_index": int, "name": str (short,
        e.g. "Deccan Plateau belt"), "justification": str (one sentence,
        grounded in sample_texts and/or shared geography, not just
        "these districts are near each other")}.

        The caller code-validates the group_index set matches exactly and
        falls back to an auto-generated name for any group this call drops or
        can't be matched back to -- never trust this call alone to account
        for every district.
        """
        ...

    async def critique_regions(self, regions: list[dict]) -> dict:
        """
        Holistic pass over the FULL proposed region set (not one call per
        region -- cheaper, and lets the model compare regions against each
        other for e.g. "region X is basically empty next to region Y").
        `regions`: [{"region_id": str, "name": str, "justification": str,
        "districts": [{"district_id", "district_name", "state_name"}, ...]},
        ...].

        Check three things: (1) thematic coherence -- does the justification
        actually track shared content, not just proximity; (2) geographic
        sanity -- cross-state regions are EXPECTED and fine, but flag wild,
        implausible scatter; (3) granularity -- no singleton-fragmented
        regions, no one region swallowing nearly every district.

        Return {"approved": bool, "notes": str (brief reasoning either way),
        "flagged_district_ids": list[str] (districts that seem misplaced --
        empty if approved or if nothing specific stood out)}.
        """
        ...

    async def revise_regions(self, regions: list[dict], critique: dict) -> list[dict]:
        """
        Called only when critique_regions returned approved=False, and only
        once (see reasoning_modes.REGION_REVISION_ROUND_CAP) -- the caller
        never re-critiques a revision, so this is the one chance to act on
        `critique`. May ONLY rename a region, merge two regions together, or
        move a `flagged_district_ids` district to a different existing
        region -- must NEVER invent a new region or drop a district; the
        caller code-validates that the returned district-id set exactly
        equals the input's (same districts, just possibly regrouped/renamed/
        merged) and that no region ends up empty, discarding the whole
        revision (keeping the pre-revision `regions`) if that invariant is
        violated.

        Return the full revised region list, same shape as `regions` but with
        `district_ids: list[str]` in place of the fuller `districts` list:
        [{"region_id": str, "name": str, "justification": str,
        "district_ids": list[str]}, ...].
        """
        ...

    async def judge_text_relevance(self, question: str) -> bool:
        """Generic yes/no judgment call, phrased as a plain question expecting
        exactly "yes" or "no". Used by region_kb.py to decide whether a past
        region's inferred worldview still usefully conditions reasoning about
        a new region/query -- kept generic (not region-specific) rather than
        a region_kb-only method, in case a later caller needs the same
        yes/no-judgment shape for something else.

        Implementations should fail CLOSED (return False) on any error -- a
        false "yes" risks conditioning reasoning on stale/irrelevant context,
        whereas a false "no" only costs one skipped (but harmless) reuse
        opportunity. Mirrors research_cache.py's `_judge_reusable` in spirit,
        but goes through the run's own LLMClient instead of a hardcoded local
        model, since callers here already have `llm` in hand.
        """
        ...

    async def condition_answer_for_region(
        self,
        query: str,
        query_type: str,
        baseline_segments: list[dict],
        region_name: str,
        region_clusters: list[dict],
        region_deflections: list[dict],
        past_worldview: str | None,
        mode: ResearchMode = "extrahigh",
    ) -> list[dict]:
        """
        Two-pass synthesis, PASS 2 (see synthesize_answer for pass 1, which
        graph/nodes/deflection_and_synthesis.py calls in a region-BLIND way
        for extrahigh runs -- clusters_payload has state/region fields
        stripped and `mode` downgraded to a non-extrahigh value specifically
        so pass 1 can't condition on region at all). `baseline_segments` is
        that region-blind pass-1 output (AnswerSegment-shaped dicts).

        Given THIS region's own actual clusters/deflections (which may agree
        with or diverge from the baseline) and, if graph/region_kb.py found a
        match, `past_worldview` -- a blended digest of this region's
        previously-inferred worldview/priorities from past runs on OTHER
        queries -- produce a SMALL set of segments stating specifically how
        this region's real discourse differs from (or notably reinforces)
        the national baseline, and why. Frame each as an explicit contrast:
        "Nationally X, but in {region_name}, Y, because Z." This is a
        targeted diff, not an independent full re-synthesis -- cheaper and
        more focused than resynthesizing from scratch per region.

        Never invent a difference that isn't supported by region_clusters/
        region_deflections/past_worldview -- if this region's discourse
        genuinely agrees with the baseline, returning fewer segments (even
        just one, or none) is correct; do not manufacture contrast for its
        own sake.

        `past_worldview` is None when no knowledge-base match was found or
        the lookup failed -- must degrade gracefully (condition purely off
        region_clusters/region_deflections in that case), never treat it as
        required.

        Return AnswerSegment-shaped dicts: {"text": str, "kind": "body"|
        "recommendation" (optional), "clusterId": str (optional),
        "citations": int[] (optional)}. The caller (not this method) attaches
        `region`/`regionId` -- there's no need to restate which region this
        is inside the segment text or fields.
        """
        ...

    async def condition_answer_for_state(
        self,
        query: str,
        query_type: str,
        baseline_segments: list[dict],
        state_name: str,
        state_research_documents: list[dict],
        state_clusters: list[dict],
        state_deflections: list[dict],
        state_districts: list[dict],
        mode: ResearchMode = "extrahigh",
    ) -> list[dict]:
        """
        Two-pass synthesis, PASS 3 (extrahigh-mode only) -- runs AFTER
        `condition_answer_for_region` (pass 2) in
        graph/nodes/deflection_and_synthesis.py's `condition_states` node.
        `baseline_segments` is the SAME region-blind pass-1 baseline
        `condition_answer_for_region` was given (from
        `state["baseline_answer_segments"]`, a stable snapshot -- NOT the
        ever-growing `answer_segments`, which by this point also holds pass
        2's region-conditioned output).

        Unlike `condition_answer_for_region`, this call is given TWO
        DISTINCT, SEPARATELY-SOURCED inputs rather than one blended context,
        per the product requirement that a state's narrative keep these
        visibly apart, never blended into one undifferentiated paragraph:
          - `state_research_documents`: mainstream/official media and
            government web sources gathered SPECIFICALLY for this state (from
            graph/nodes/research.py's `gather_research_per_state`, filtered by
            each document's `source_state_code` -- these carry the SAME `id`s
            as the run's overall Sources list, since they're a filtered slice
            of `state["research_documents"]`, not a re-numbered one).
          - `state_clusters` / `state_deflections`: this state's own
            User-Generated, social-media viewpoint clusters and the points of
            disagreement among them (from
            graph/nodes/deflection_and_synthesis.py's
            `_state_clusters_payload`/`_state_deflections_payload` -- a
            cluster's `postCount` here is this state's own TRUE share of that
            cluster's volume, re-aggregated from each district's real
            state_code, not a cluster's own only-representative-in-region-mode
            one).
        `state_districts` is a per-district volume breakdown for this state,
        for naming specific districts when the source data supports it.

        Your job: produce SEPARATE segments for each source type -- one or
        more grounded ONLY in `state_research_documents` (citing them), then
        one or more grounded ONLY in `state_clusters`/`state_deflections` --
        each stating specifically how that source's picture of this state
        differs from, or reinforces, the national baseline, and why. Never
        blend the two source types into one segment. Never invent a
        difference with no support in the given data -- if a source type
        genuinely agrees with the baseline (or is empty/thin for this state),
        return fewer segments for it (even zero) rather than manufacturing
        contrast.

        `state_research_documents`/`state_clusters` may each independently be
        empty (a state can have social-media signal with thin research
        coverage, or vice versa) -- degrade gracefully, producing segments
        only for whichever source type actually has content, never fail or
        fabricate the missing side.

        Return AnswerSegment-shaped dicts: {"text": str, "kind": "body"|
        "recommendation" (optional), "clusterId": str (optional), "citations":
        int[] (optional -- only for segments grounded in
        state_research_documents, using THOSE documents' own `id` fields; do
        NOT invent ids, and never attach citations to a social-media-grounded
        segment, which has no source list to cite). The caller (not this
        method) attaches `state`/`stateCode` -- there's no need to restate
        which state this is inside the segment text or fields.
        """
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
