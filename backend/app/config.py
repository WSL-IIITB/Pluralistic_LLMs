"""
Environment-driven settings.

By default (`ALLOW_STUB_FALLBACK=false`, the default) a source with no
credentials is simply SKIPPED — it contributes zero posts rather than
fabricating fixture data, and a missing LLM key fails the run outright with a
clear error, since the LLM is not optional (it drives clustering, resolution,
and synthesis). Set `ALLOW_STUB_FALLBACK=true` to restore the old offline-demo
behavior (every connector falls back to its deterministic stub), useful for
local testing with zero accounts configured.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── LLM provider selector ────────────────────────────────────────────────────
    # Which backend get_llm_client() wires up by default (a request can still
    # override per-call via ?provider=). Matches reasoning_modes.LlmProvider's
    # full set. "azure_anthropic" (Claude via Azure AI Foundry) is selectable
    # again after having been removed and then restored on request;
    # gemma_remote (self-hosted, no credential needed) remains the DEFAULT.
    llm_provider: Literal[
        "openai", "azure_anthropic", "gemma_local", "mistral_local", "gemma_remote"
    ] = Field(default="gemma_remote")

    # ── LLM (OpenAI) ───────────────────────────────────────────────────────────
    openai_api_key: str | None = Field(default=None)
    openai_chat_model: str = Field(default="gpt-4o-mini")
    # Model used ONLY for the research stage's web_search tool calls. gpt-4o
    # returns URL citation annotations on responses.create — gpt-4o-mini does
    # not (verified empirically). Keep this bigger model narrowly scoped to
    # research so the many small per-cluster / per-post / per-district calls
    # elsewhere stay on the cheap mini model.
    openai_research_model: str = Field(default="gpt-4o")
    openai_embedding_model: str = Field(default="text-embedding-3-small")

    # ── LLM (Claude via Azure AI Foundry) ────────────────────────────────────────
    # Foundry's Claude endpoint is the Anthropic Messages API surface (not an
    # OpenAI-compatible one) — reached via the `anthropic` SDK's AnthropicFoundry
    # client. Anthropic has no embeddings endpoint, so embed() falls back to the
    # same local sentence-transformers model the other no-embeddings providers use.
    azure_anthropic_api_key: str | None = Field(default=None)
    azure_anthropic_endpoint: str | None = Field(default=None)
    azure_anthropic_deployment: str = Field(default="claude-sonnet-4-5")

    # ── LLM (local, via Ollama) ──────────────────────────────────────────────────
    # Local providers (gemma_local/mistral_local, see reasoning_modes.OLLAMA_MODEL_TAGS)
    # need no API key to reason -- only the research() stage's web_search tool call
    # needs a credential, since local models have no hosted search tool the way
    # Claude/OpenAI do. Ollama's own hosted web-search API fills that gap.
    ollama_base_url: str = Field(default="http://localhost:11434")
    ollama_web_search_api_key: str | None = Field(default=None)

    # ── LLM (self-hosted Gemma, OpenAI-compatible) ───────────────────────────────
    # A separate self-hosted inference server (confirmed genuinely OpenAI-
    # compatible at /v1/chat/completions, including response_format=json_object
    # -- unlike Ollama's native-only providers above). Needs no API key. Its
    # /v1/embeddings route is confirmed broken server-side (a 'query' KeyError
    # regardless of input shape) and it has no /v1/responses endpoint at all
    # (confirmed 404) -- see RemoteGemmaLLMClient, which never attempts either
    # network call and goes straight to the same local-embedding/no-research
    # fallbacks the other credential-free providers use.
    # No default on purpose: this is an internal, unauthenticated server --
    # anyone who has the address can use it for free, so it must never be
    # hardcoded or committed. Two ways to reach it, both via this same
    # setting: (1) direct, for whoever owns the server -- the real
    # http://host:port, no API key needed; (2) through proxy/ (see its
    # README), for anyone else -- the proxy's own URL + "/gemma", paired with
    # remote_gemma_api_key set to the shared passphrase the proxy checks.
    # Direct access has moved before (host and port both changed on
    # 2026-09-03) without notice, so don't assume a value you have is still
    # current -- re-verify via GET /v1/models if unsure.
    remote_gemma_base_url: str | None = Field(default=None)
    # Sent as this client's OpenAI-style api_key -- ignored (server takes no
    # auth) when talking to the real server directly; when remote_gemma_base_url
    # instead points at proxy/, this must be the shared passphrase it checks.
    remote_gemma_api_key: str | None = Field(default=None)
    remote_gemma_chat_model: str = Field(default="Firworks/gemma-4-26B-A4B-it-fp8")

    # ── Reddit (PRAW) ────────────────────────────────────────────────────────────
    reddit_client_id: str | None = Field(default=None)
    reddit_client_secret: str | None = Field(default=None)
    reddit_user_agent: str = Field(default="worldview-explorer/0.1 (by u/worldview-bot)")

    # ── YouTube Data API v3 ──────────────────────────────────────────────────────
    youtube_api_key: str | None = Field(default=None)

    # ── YouTube provider selector ───────────────────────────────────────────────
    # "ytdlp" (default since 2026-09-06): yt-dlp scraping — no key, no daily quota,
    # reply threads included. Costs: ~5-7s per search plus per-video comment crawl
    # (extrahigh's 42-search fan-out measured at ~6 min sourcing; see decisions.md
    # 2026-09-06 for the speedup plan: max_comments 100->50 + dead-ID seen-set),
    # and no native regionCode geo-filter. "api": YouTube Data API v3 — needs
    # YOUTUBE_API_KEY, burns daily quota (search.list = flat 100 units/call; quota
    # exhaustion was the dominant real-world failure mode) — kept as opt-in fallback.
    youtube_provider: Literal["api", "ytdlp"] = Field(default="ytdlp")

    # ── NITI Aayog district-indicator CSVs ─────────────────────────────────────
    # Directory containing the CSVs NitiCsvConnector sources (the two
    # RUN00{676,677}_ALL_INDIA_CASEFILE_MATCHING.csv files ship in the repo's
    # /niti folder). Searched as-is -- every *.csv in the directory becomes
    # part of the searchable corpus. Override per-deployment to point at a
    # different export; leave unset to use the repo's own /niti folder.
    # Needs no key -- the data is local.
    csv_data_dir: str | None = Field(default=None)

    # ── Stub behavior ─────────────────────────────────────────────────────────
    allow_stub_fallback: bool = Field(default=False)

    # ── Server ────────────────────────────────────────────────────────────────────
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:8080", "http://localhost:3000"])
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8001)

    @property
    def has_llm(self) -> bool:
        if self.llm_provider == "azure_anthropic":
            return self.has_azure_anthropic
        return bool(self.openai_api_key)

    @property
    def has_azure_anthropic(self) -> bool:
        return bool(self.azure_anthropic_api_key and self.azure_anthropic_endpoint)

    @property
    def has_reddit(self) -> bool:
        return bool(self.reddit_client_id and self.reddit_client_secret)

    @property
    def has_youtube(self) -> bool:
        return bool(self.youtube_api_key)

    @property
    def has_ollama_web_search(self) -> bool:
        return bool(self.ollama_web_search_api_key)

    @property
    def has_remote_gemma(self) -> bool:
        # Unlike has_llm, this provider needs no API key -- only a reachable
        # base_url, which has no default (see remote_gemma_base_url) and so
        # must be set explicitly in each developer's own untracked .env.
        return bool(self.remote_gemma_base_url)

    def niti_csv_dir(self) -> str:
        """Resolved path to the NITI CSV directory (env override, else the
        repo's checked-out /niti folder -- see the csv_data_dir field)."""
        return self.csv_data_dir or os.path.join(REPO_ROOT, "niti")

    @property
    def has_niti_csv(self) -> bool:
        """True if the NITI CSV directory exists and holds at least one .csv.
        Mirrors the has_reddit/has_youtube contract: the connector is only
        constructed when data is actually present."""
        d = self.niti_csv_dir()
        return os.path.isdir(d) and any(name.lower().endswith(".csv") for name in os.listdir(d))


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # pydantic-settings fills from env/.env


def is_stub_mode() -> bool:
    """True if every external credential is absent — pure fixture-data mode."""
    s = get_settings()
    return not (s.has_llm or s.has_reddit or s.has_youtube or s.has_remote_gemma)


# Repo-relative paths to the frontend's own geo files, so the district
# gazetteer and subreddit map can be derived from (and stay aligned with) the
# same district IDs the map renders. Overridable for non-standard checkouts.
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(BACKEND_DIR)
FRONTEND_DISTRICTS_GEOJSON = os.path.join(REPO_ROOT, "public", "geo", "india-districts.geojson")
DATA_DIR = os.path.join(BACKEND_DIR, "app", "data")
