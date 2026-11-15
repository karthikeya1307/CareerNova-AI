"""Phase 5: Groq provider and LLM configuration (all network calls mocked)."""

import io
import json
import socket
import urllib.error

import pytest

from backend.services import llm
from backend.services.llm import groq_provider
from backend.services.llm.base import LLMError
from backend.services.llm.groq_provider import GROQ_CHAT_URL, GroqProvider

SECRET = "gsk_test_secret_key_value"


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def install_urlopen(monkeypatch, handler):
    seen = {}

    def fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["headers"] = dict(request.header_items())
        seen["body"] = json.loads(request.data.decode("utf-8"))
        seen["timeout"] = timeout
        return handler()

    monkeypatch.setattr(groq_provider.urllib.request, "urlopen", fake_urlopen)
    return seen


def ok(content):
    return lambda: FakeResponse(json.dumps({"choices": [{"message": {"content": json.dumps(content)}}]}).encode())


def test_request_format_and_response_parsing(monkeypatch):
    seen = install_urlopen(monkeypatch, ok({"summary": {"text": "x", "fact_ids": ["sum-1"]}}))
    provider = GroqProvider(SECRET, "llama-3.3-70b-versatile", timeout=12)

    result = provider.complete_json("system rules", '{"facts": []}')

    assert result == {"summary": {"text": "x", "fact_ids": ["sum-1"]}}
    assert seen["url"] == GROQ_CHAT_URL
    assert seen["headers"]["Authorization"] == f"Bearer {SECRET}"
    assert seen["body"]["model"] == "llama-3.3-70b-versatile"
    assert seen["body"]["response_format"] == {"type": "json_object"}
    assert [m["role"] for m in seen["body"]["messages"]] == ["system", "user"]
    assert seen["timeout"] == 12


@pytest.mark.parametrize("handler, message", [
    (lambda: (_ for _ in ()).throw(urllib.error.HTTPError(GROQ_CHAT_URL, 401, "Unauthorized", {}, None)),
     "HTTP 401"),
    (lambda: (_ for _ in ()).throw(socket.timeout("timed out")), "could not be reached"),
    (lambda: (_ for _ in ()).throw(urllib.error.URLError("dns")), "could not be reached"),
    (lambda: FakeResponse(b"not json"), "not valid JSON"),
    (lambda: FakeResponse(json.dumps({"choices": [{"message": {"content": "[1, 2]"}}]}).encode()),
     "not a JSON object"),
])
def test_errors_are_safe(monkeypatch, handler, message):
    install_urlopen(monkeypatch, handler)
    with pytest.raises(LLMError) as error:
        GroqProvider(SECRET, "m").complete_json("s", "u")
    assert message in str(error.value)
    assert SECRET not in str(error.value)


def test_repr_never_shows_key():
    assert SECRET not in repr(GroqProvider(SECRET, "m"))


def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    llm.set_llm_provider(None, override=False)
    assert llm.get_llm_provider() is None
    assert llm.llm_status() == {"available": False, "provider": None, "model": None, "disclosure": None}


def test_requires_both_provider_and_key(monkeypatch):
    llm.set_llm_provider(None, override=False)
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert llm.get_llm_provider() is None

    monkeypatch.setenv("GROQ_API_KEY", SECRET)
    monkeypatch.setenv("GROQ_MODEL", "some-model")
    provider = llm.get_llm_provider()
    assert isinstance(provider, GroqProvider) and provider.model == "some-model"

    status = llm.llm_status()
    assert status["available"] and status["provider"] == "groq"
    assert "never sent" in status["disclosure"] and SECRET not in json.dumps(status)
