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
    # Which backend get_llm_client() wires up. "azure_anthropic" is a same-shape
    # swap-in for testing/comparison — see connectors/llm.py's AzureAnthropicLLMClient.
    llm_provider: Literal["openai", "azure_anthropic"] = Field(default="openai")

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
    # same deterministic hash embedding the stub uses regardless of provider.
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

    # ── Reddit (PRAW) ────────────────────────────────────────────────────────────
    reddit_client_id: str | None = Field(default=None)
    reddit_client_secret: str | None = Field(default=None)
    reddit_user_agent: str = Field(default="worldview-explorer/0.1 (by u/worldview-bot)")

    # ── YouTube Data API v3 ──────────────────────────────────────────────────────
    youtube_api_key: str | None = Field(default=None)

    # ── Stub behavior ─────────────────────────────────────────────────────────
    allow_stub_fallback: bool = Field(default=False)

    # ── Server ────────────────────────────────────────────────────────────────────
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:8080"])
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


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # pydantic-settings fills from env/.env


def is_stub_mode() -> bool:
    """True if every external credential is absent — pure fixture-data mode."""
    s = get_settings()
    return not (s.has_llm or s.has_reddit or s.has_youtube)


# Repo-relative paths to the frontend's own geo files, so the district
# gazetteer and subreddit map can be derived from (and stay aligned with) the
# same district IDs the map renders. Overridable for non-standard checkouts.
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(BACKEND_DIR)
FRONTEND_DISTRICTS_GEOJSON = os.path.join(REPO_ROOT, "public", "geo", "india-districts.geojson")
DATA_DIR = os.path.join(BACKEND_DIR, "app", "data")
