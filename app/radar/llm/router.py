"""Provider chain with fallback and a simple circuit breaker.

RADAR_LLM_PROVIDERS="anthropic,openai,mock": try in order; a provider that failed is skipped for
`cooldown_s`, so a dead API does not add its timeout to every record.
"""

from __future__ import annotations

import logging
import time

from radar.config import get_settings
from radar.llm.providers import PROVIDERS, Provider, ProviderError

log = logging.getLogger(__name__)


class AllProvidersFailed(RuntimeError):
    pass


class LLMRouter:
    def __init__(self, names: list[str] | None = None, cooldown_s: float = 120.0):
        names = names or [n.strip() for n in get_settings().llm_providers.split(",") if n.strip()]
        unknown = [n for n in names if n not in PROVIDERS]
        if unknown:
            raise ValueError(f"unknown LLM providers: {unknown}")
        self.providers: list[Provider] = [PROVIDERS[n]() for n in names]
        self.cooldown_s = cooldown_s
        self._open_until: dict[str, float] = {}

    def complete_json(self, system: str, user: str) -> tuple[dict, dict]:
        """Returns (result, provenance). Provenance names the provider and model that answered."""
        errors = []
        for p in self.providers:
            if not p.available():
                errors.append(f"{p.name}: not configured")
                continue
            if self._open_until.get(p.name, 0) > time.monotonic():
                errors.append(f"{p.name}: circuit open")
                continue
            try:
                out = p.complete_json(system, user)
                return out, {"provider": p.name, "model": p.model, "fallbacks": errors}
            except ProviderError as e:
                log.warning("LLM provider %s failed: %s", p.name, e)
                self._open_until[p.name] = time.monotonic() + self.cooldown_s
                errors.append(f"{p.name}: {e}")
        raise AllProvidersFailed("; ".join(errors))


_router: LLMRouter | None = None


def router() -> LLMRouter:
    global _router
    if _router is None:
        _router = LLMRouter()
    return _router
