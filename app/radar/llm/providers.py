"""Swappable LLM providers (D-003). Each one implements `complete_json(system, user) -> dict`.

* anthropic      — Anthropic Messages API
* openai         — any OpenAI-compatible Chat Completions API (OpenAI, Azure, vLLM, Ollama, LM Studio, Bielik
                   behind an OpenAI-compatible server) via RADAR_OPENAI_BASE_URL
* mock           — deterministic, offline; used in demo mode and tests, and as the last fallback.
                   Its output is labelled `provider: mock` on every card, so nobody mistakes it for a model.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod

import httpx

from radar.config import get_settings


class ProviderError(RuntimeError):
    pass


def _parse_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ProviderError("no JSON object in model output")
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError as e:
        raise ProviderError(f"invalid JSON from model: {e}") from e


class Provider(ABC):
    name: str
    model: str

    def available(self) -> bool:
        return True

    @abstractmethod
    def complete_json(self, system: str, user: str) -> dict: ...


class AnthropicProvider(Provider):
    name = "anthropic"

    def __init__(self):
        s = get_settings()
        self.key, self.model, self.timeout = s.anthropic_api_key, s.anthropic_model, s.llm_timeout_s

    def available(self) -> bool:
        return bool(self.key)

    def complete_json(self, system: str, user: str) -> dict:
        try:
            r = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": self.key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={"model": self.model, "max_tokens": 2000, "system": system,
                      "messages": [{"role": "user", "content": user}]},
                timeout=self.timeout,
            )
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise ProviderError(f"anthropic: {e}") from e
        text = "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")
        return _parse_json(text)


class OpenAICompatProvider(Provider):
    name = "openai"

    def __init__(self):
        s = get_settings()
        self.key, self.base, self.model, self.timeout = s.openai_api_key, s.openai_base_url, s.openai_model, s.llm_timeout_s

    def available(self) -> bool:
        return bool(self.key) or "localhost" in self.base or "ollama" in self.base

    def complete_json(self, system: str, user: str) -> dict:
        headers = {"Authorization": f"Bearer {self.key}"} if self.key else {}
        try:
            r = httpx.post(
                self.base.rstrip("/") + "/chat/completions",
                headers=headers,
                json={"model": self.model, "response_format": {"type": "json_object"},
                      "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
                timeout=self.timeout,
            )
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise ProviderError(f"openai: {e}") from e
        return _parse_json(r.json()["choices"][0]["message"]["content"])


SENT = re.compile(r"(?<=[.!?])\s+")
SIGNALS = ("opracowan", "wdroż", "prototyp", "metod", "system", "program", "pilota", "model", "rozwiązani",
           "develop", "method", "prototype", "implement", "platform", "tool", "narzędz", "aplikac")


class MockProvider(Provider):
    """Offline heuristic 'model'. Quotes are copied verbatim from the input, so validation passes honestly."""

    name = "mock"
    model = "heuristic-v1"

    def complete_json(self, system: str, user: str) -> dict:
        text = user.split("TEKST ŹRÓDŁOWY:", 1)[-1].strip()
        title = text.splitlines()[0].removeprefix("Tytuł:").strip() if text else ""
        body = text.split("Opis:", 1)[-1].strip()
        sentences = [s.strip() for s in SENT.split(body) if len(s.strip()) > 20] or [body[:300]]
        low = body.lower()
        is_innov = any(k in low for k in SIGNALS)
        problem = next((s for s in sentences if any(w in s.lower() for w in ("problem", "wyzwan", "potrzeb", "brak", "need"))), sentences[0])
        new = next((s for s in sentences if any(k in s.lower() for k in SIGNALS)), sentences[-1])
        itype = "technologiczna"
        if any(w in low for w in ("szkoł", "uczni", "edukac", "nauczyc")):
            itype = "edukacyjna"
        elif any(w in low for w in ("gmin", "mieszkańc", "senior", "społeczn")):
            itype = "społeczna"
        elif any(w in low for w in ("procedur", "proces", "organizac", "urzęd")):
            itype = "organizacyjna"
        return {
            "is_innovation": "tak" if is_innov else "niejasne",
            "is_innovation_quote": new,
            "solution_name": {"value": title[:120], "quote": title[:120], "confidence": 0.6},
            "problem_solved": {"value": problem, "quote": problem, "confidence": 0.5},
            "what_is_new": {"value": new, "quote": new, "confidence": 0.5},
            "target_users": {"value": ["instytucje publiczne"], "quote": sentences[0], "confidence": 0.3},
            "innovation_type": {"value": itype, "quote": sentences[0], "confidence": 0.4},
            "summary_pl": " ".join(sentences[:2])[:500],
        }


PROVIDERS = {"anthropic": AnthropicProvider, "openai": OpenAICompatProvider, "mock": MockProvider}
