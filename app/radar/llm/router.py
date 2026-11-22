"""Provider chain with fallback and a simple circuit breaker.

RADAR_LLM_PROVIDERS="local,mock" (default in compose/helm): small CPU model on the VPS first, then the rules
(offline heuristic). Cloud providers listed there (anthropic, openai on a non-local URL) are skipped unless
RADAR_LLM_ALLOW_CLOUD=1 is set explicitly; then they are tried in the listed order. A provider that failed
is skipped for `cooldown_s`, so a dead API does not add its timeout to every record. The agent (`assess`) excludes `mock` and falls back to its rules instead.

Every attempt (success or failure) is logged to the `llm_calls` table with its latency, so `/metrics` on the API
shows latency, errors and fallbacks per provider for all worker processes.
"""

from __future__ import annotations

import logging
import time

import httpx

from radar.config import get_settings
from radar.llm.providers import PROVIDERS, BadOutput, Provider, ProviderError, is_cloud

log = logging.getLogger(__name__)
MIN_CALL_S = 5.0  # less budget than this left: do not start another LLM call


class AllProvidersFailed(RuntimeError):
    def __init__(self, msg: str, only_bad_output: bool = False):
        super().__init__(msg)
        self.only_bad_output = only_bad_output  # a model answered, just not in JSON: worth asking again


def _record(db, provider: str, model: str | None, purpose: str, ok: bool, latency_ms: float,
            error: str | None = None, usage: dict | None = None) -> None:
    """Best effort: metrics must never break the pipeline (e.g. classification without a DB).
    `db`: the caller's open session (the agent runs inside the score transaction; a second writer would wait
    on SQLite's lock), else a short session of our own."""
    try:
        from radar.models import LlmCall

        row = LlmCall(provider=provider, model=(model or "")[:120], purpose=purpose[:30], ok=ok,
                      latency_ms=round(latency_ms, 1), error=(error or None) and error[:300],
                      tokens_in=(usage or {}).get("in"), tokens_out=(usage or {}).get("out"))
        if db is not None:
            db.add(row)
            return
        from radar.db import session

        with session() as s:
            s.add(row)
    except Exception as e:  # pragma: no cover - only without a database
        log.debug("llm call not recorded: %s", e)


class LLMRouter:
    def __init__(self, names: list[str] | None = None, cooldown_s: float = 120.0):
        names = names or [n.strip() for n in get_settings().llm_providers.split(",") if n.strip()]
        unknown = [n for n in names if n not in PROVIDERS]
        if unknown:
            raise ValueError(f"unknown LLM providers: {unknown}")
        providers: list[Provider] = [PROVIDERS[n]() for n in names]
        # Cost rule: local model -> rules (mock heuristic) by default; a cloud model joins the chain only when
        # RADAR_LLM_ALLOW_CLOUD=1 is set explicitly, in the position RADAR_LLM_PROVIDERS gives it.
        self.blocked = [] if get_settings().llm_allow_cloud else [p.name for p in providers if is_cloud(p)]
        if self.blocked:
            log.info("cloud LLM providers %s skipped: set RADAR_LLM_ALLOW_CLOUD=1 to enable them", self.blocked)
        self.providers = [p for p in providers if p.name not in self.blocked]
        self.cooldown_s = cooldown_s
        self._open_until: dict[str, float] = {}

    def real_available(self) -> bool:
        """True when a non-heuristic model is configured (and its circuit is closed)."""
        now = time.monotonic()
        return any(p.name != "mock" and p.available() and self._open_until.get(p.name, 0) <= now for p in self.providers)

    def complete_json(self, system: str, user: str, purpose: str = "other",
                      exclude: tuple[str, ...] = (), db=None, deadline: float | None = None) -> tuple[dict, dict]:
        """Returns (result, provenance). Provenance names the provider and model that answered and its latency.

        `deadline` (time.monotonic()): the caller's time budget. Each provider's HTTP timeout is capped to what is
        left, and a provider is skipped when less than MIN_CALL_S is left. A timeout caused by that cap is the
        caller's budget running out, not a dead server, so it does not open the circuit."""
        errors = []
        for p in self.providers:
            if p.name in exclude:
                continue
            if not p.available():
                errors.append(f"{p.name}: not configured")
                continue
            if self._open_until.get(p.name, 0) > time.monotonic():
                errors.append(f"{p.name}: circuit open")
                continue
            own = getattr(p, "timeout", None)
            capped = False
            if deadline is not None:
                left = deadline - time.monotonic()
                if left < MIN_CALL_S:
                    errors.append(f"{p.name}: budget exhausted")
                    continue
                if own is not None and left < own:
                    p.timeout, capped = left, True
            t0 = time.perf_counter()
            p.last_usage = None
            try:
                out = p.complete_json(system, user)
            except ProviderError as e:
                ms = (time.perf_counter() - t0) * 1000
                log.warning("LLM provider %s failed: %s", p.name, e, extra={"provider": p.name})
                _record(db, p.name, p.model, purpose, False, ms, str(e))
                budget_cut = capped and isinstance(e.__cause__, httpx.TimeoutException)
                # BadOutput: the server answered; budget_cut: we cut the call short. Neither means it is down.
                if not isinstance(e, BadOutput) and not budget_cut:
                    self._open_until[p.name] = time.monotonic() + self.cooldown_s
                errors.append(f"{p.name}: budget exhausted ({e})" if budget_cut else f"{p.name}: {e}")
                continue
            finally:
                if capped:
                    p.timeout = own
            ms = (time.perf_counter() - t0) * 1000
            _record(db, p.name, p.model, purpose, True, ms, usage=p.last_usage)
            return out, {"provider": p.name, "model": p.model, "fallbacks": errors, "latency_ms": round(ms, 1)}
        raise AllProvidersFailed("; ".join(errors) or "no provider", only_bad_output=bool(errors) and all(
            "invalid JSON" in e or "no JSON" in e or "not configured" in e or "circuit open" in e for e in errors)
            and any("JSON" in e for e in errors))


_router: LLMRouter | None = None


def router() -> LLMRouter:
    global _router
    if _router is None:
        _router = LLMRouter()
    return _router
