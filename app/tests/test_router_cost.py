"""Cost rule (#13): local model -> rules by default; a cloud model only after an explicit RADAR_LLM_ALLOW_CLOUD=1."""

import httpx
import respx

from radar.config import get_settings


def _router(monkeypatch, providers: str, **env):
    monkeypatch.setenv("RADAR_LLM_PROVIDERS", providers)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    from radar.llm.router import LLMRouter

    return LLMRouter()


def test_cloud_is_skipped_unless_explicitly_allowed(monkeypatch):
    r = _router(monkeypatch, "local,anthropic,openai,mock", RADAR_ANTHROPIC_API_KEY="k", RADAR_OPENAI_API_KEY="k",
                RADAR_LOCAL_LLM_URL="http://llm:8080/v1")
    assert [p.name for p in r.providers] == ["local", "mock"] and r.blocked == ["anthropic", "openai"]
    out, prov = _router(monkeypatch, "anthropic,mock", RADAR_ANTHROPIC_API_KEY="k").complete_json("s", "TEKST ŹRÓDŁOWY:\nTytuł: x\nOpis: y")
    assert prov["provider"] == "mock"  # a key alone does not enable the cloud

    r = _router(monkeypatch, "local,anthropic,mock", RADAR_LLM_ALLOW_CLOUD="1", RADAR_ANTHROPIC_API_KEY="k")
    assert [p.name for p in r.providers] == ["local", "anthropic", "mock"] and r.blocked == []


def test_self_hosted_openai_compatible_server_is_not_cloud(monkeypatch):
    r = _router(monkeypatch, "openai,mock", RADAR_OPENAI_BASE_URL="http://localhost:11434/v1")
    assert [p.name for p in r.providers] == ["openai", "mock"]


@respx.mock
def test_local_provider_sends_json_grammar(monkeypatch):
    route = respx.post("http://llm:8080/v1/chat/completions").mock(return_value=httpx.Response(
        200, json={"choices": [{"message": {"content": '{"ok": true}'}}], "usage": {"prompt_tokens": 3, "completion_tokens": 2}}))
    r = _router(monkeypatch, "local,mock", RADAR_LOCAL_LLM_URL="http://llm:8080/v1")
    out, prov = r.complete_json("s", "u")
    assert out == {"ok": True} and prov["provider"] == "local"
    body = __import__("json").loads(route.calls[0].request.content)
    assert body["grammar"].startswith("root") and "response_format" not in body


def test_api_config_shows_effective_chain(monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("RADAR_LLM_PROVIDERS", "local,anthropic,mock")
    get_settings.cache_clear()
    import radar.llm.router as R

    R._router = None
    from radar.api.main import app

    with TestClient(app) as c:
        cfg = c.get("/api/config").json()
    assert cfg["llm_providers"] == ["local", "mock"] and cfg["llm_cloud_blocked"] == ["anthropic"]
    assert cfg["llm_allow_cloud"] is False


@respx.mock
def test_pregen_slogan_uses_local_model_and_is_logged(monkeypatch):
    from types import SimpleNamespace

    from sqlalchemy import select

    from radar import pregen
    from radar.db import session
    from radar.models import LlmCall

    route = respx.post("http://llm:8080/v1/chat/completions").mock(return_value=httpx.Response(
        200, json={"choices": [{"message": {"content": '{"haslo": "Czujnik światłowodowy dla przemysłu"}'}}],
                   "usage": {"prompt_tokens": 140, "completion_tokens": 12}}))
    monkeypatch.setenv("RADAR_LOCAL_LLM_URL", "http://llm:8080/v1")
    get_settings.cache_clear()
    rec = SimpleNamespace(title="Czujnik odkształceń", abstract="Opracowano czujnik światłowodowy dla przemysłu.")
    card = SimpleNamespace(solution_name=None, problem_solved=None, summary_pl=None)
    assert pregen.slogan(rec, card, pregen.local_slogan()) == ("Czujnik światłowodowy dla przemysłu", "local-llm")
    import json

    assert json.loads(route.calls[0].request.content)["grammar"] == pregen.SLOGAN_GBNF
    with session() as s:
        call = s.scalars(select(LlmCall)).one()
        assert (call.provider, call.purpose, call.ok, call.tokens_out) == ("local", "slogan", True, 12)

    monkeypatch.delenv("RADAR_LOCAL_LLM_URL")
    get_settings.cache_clear()
    assert pregen.local_slogan() is None  # not configured: rules only
