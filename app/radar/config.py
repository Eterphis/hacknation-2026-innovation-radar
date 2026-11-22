"""Runtime settings, all from environment variables (12-factor; Helm sets them from values/secrets)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RADAR_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./radar.db"
    broker_url: str = "memory://"
    # When true, Celery runs tasks inline (no broker needed): tests and `radar demo` on a laptop.
    eager: bool = False

    sources_file: str = "sources.yaml"
    # Demo mode: only connectors marked `demo: true` (snapshots) run, so the jury never depends on our keys.
    demo_mode: bool = False

    # Comma-separated provider chain, first healthy one wins. See radar/llm/router.py.
    llm_providers: str = "mock"
    # Cloud models (anthropic; openai on a non-local base URL) are dropped from the chain unless this is set
    # explicitly: new records go to rules and the small local model, never to a cloud model by default.
    llm_allow_cloud: bool = False
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5-5"
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    # Local CPU model behind llama.cpp server (OpenAI-compatible), e.g. Bielik 1.5B GGUF. Empty = disabled.
    local_llm_url: str = ""
    local_llm_model: str = "bielik-1.5b-v3.0-instruct"
    local_llm_json_mode: bool = False
    # send a JSON GBNF grammar to llama.cpp (a 1.5B model ignores "JSON only" in the prompt)
    local_llm_grammar: bool = True
    # pregeneration asks the local model for the slogan (GBNF-constrained, validated, rule fallback)
    pregen_local_slogan: bool = True
    # a 1.5B model on a few vCPU needs ~1 min per agent step; a separate, longer timeout than the cloud APIs
    local_llm_timeout_s: float = 300.0
    llm_timeout_s: float = 60.0
    # Wall-time budget of one assessment's LLM work (agent steps + reviewer). It must end before the Celery limit
    # of the `score` task (derived from it in pipeline/tasks.py), so a slow CPU model degrades to the rules
    # instead of being killed and retried from scratch.
    agent_budget_s: float = 420.0
    # the LLM reviewer runs only if at least this much budget is left (else the rule-based reviewer)
    agent_review_min_s: float = 60.0
    # Prices for the cost metric, USD per million tokens: {"anthropic": [in, out], "openai": [in, out]}.
    # Not hard-coded (they change); unset = cost 0, the token counters are still exported. Local model = 0.
    llm_prices: str = ""

    # Shared secrets for webhook sources are looked up as RADAR_WEBHOOK_SECRET_<SOURCE_ID_UPPER>.
    http_user_agent: str = "innovation-radar/0.1 (+https://github.com/Eterphis/hacknation-2026-innovation-radar)"
    http_timeout_s: float = 30.0
    max_pages_per_run: int = 50


@lru_cache
def get_settings() -> Settings:
    return Settings()
