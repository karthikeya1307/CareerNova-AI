"""P3: the optional local Ollama provider (no real network: urlopen is replaced)."""

import io
import json
import socket
import urllib.error

import pytest

from backend.services import llm
from backend.services.llm import base, ollama_provider
from backend.services.llm.base import LLMError, get_llm_provider, llm_status


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def calls(monkeypatch):
    recorded = []

    def install(reply=None, error=None):
        def urlopen(request, timeout=None):
            recorded.append({"url": request.full_url, "body": json.loads(request.data), "timeout": timeout})
            if error:
                raise error
            return FakeResponse(json.dumps(reply).encode())
        monkeypatch.setattr(ollama_provider.urllib.request, "urlopen", urlopen)
        return recorded
    return install


@pytest.fixture
def use_env(monkeypatch):
    def apply(**env):
        llm.set_llm_provider(None, override=False)
        for key in ("LLM_PROVIDER", "OLLAMA_URL", "OLLAMA_MODEL", "OLLAMA_TIMEOUT_SECONDS", "GROQ_API_KEY"):
            monkeypatch.delenv(key, raising=False)
        for key, value in env.items():
            monkeypatch.setenv(key, value)
    yield apply
    llm.set_llm_provider(None, override=True)


def test_selected_by_environment_with_defaults(use_env):
    use_env(LLM_PROVIDER="ollama")
    provider = get_llm_provider()
    assert provider.name == "ollama" and provider.model == "gemma3"
    assert provider.base_url == "http://127.0.0.1:11434" and provider.timeout == 120
    status = llm_status()
    assert status["available"] and status["provider"] == "ollama" and status["location"] == "local"
    # The privacy notice must not call a model on this server an external provider.
    assert "running on this server" in status["disclosure"] and "external" not in status["disclosure"]


def test_custom_url_and_model(use_env):
    use_env(LLM_PROVIDER="ollama", OLLAMA_URL="http://gpu-box.lan:11434/", OLLAMA_MODEL="gemma3:12b",
            OLLAMA_TIMEOUT_SECONDS="45")
    provider = get_llm_provider()
    assert (provider.base_url, provider.model, provider.timeout) == ("http://gpu-box.lan:11434", "gemma3:12b", 45)
    assert llm_status()["location"] == "external"
    assert "an external language-model provider (ollama)" in llm_status()["disclosure"]


def test_invalid_url_turns_ai_off_instead_of_failing(use_env):
    use_env(LLM_PROVIDER="ollama", OLLAMA_URL="file:///etc/passwd")
    assert get_llm_provider() is None and llm_status()["available"] is False


def test_groq_is_unchanged(use_env):
    use_env(LLM_PROVIDER="groq", GROQ_API_KEY="test-key-not-real")
    provider = get_llm_provider()
    assert provider.name == "groq" and "test-key" not in repr(provider)
    assert "an external language-model provider (groq)" in llm_status()["disclosure"]
    use_env(LLM_PROVIDER="none")
    assert get_llm_provider() is None


def test_chat_request_and_json_answer(calls):
    recorded = calls({"message": {"role": "assistant", "content": '{"answer": "ok"}'}, "done": True})
    provider = ollama_provider.OllamaProvider(timeout=7)
    assert provider.complete_json("system text", "user text") == {"answer": "ok"}
    [call] = recorded
    assert call["url"] == "http://127.0.0.1:11434/api/chat" and call["timeout"] == 7
    body = call["body"]
    assert body["model"] == "gemma3" and body["format"] == "json" and body["stream"] is False
    assert body["messages"] == [{"role": "system", "content": "system text"}, {"role": "user", "content": "user text"}]


@pytest.mark.parametrize("reply, error, message", [
    (None, urllib.error.URLError("refused"), "could not be reached"),
    (None, socket.timeout("slow"), "could not be reached"),
    (None, urllib.error.HTTPError("u", 404, "not found", {}, None), "ollama pull gemma3"),
    (None, urllib.error.HTTPError("u", 500, "boom", {}, None), "HTTP 500"),
    ({"message": {"content": "not json"}}, None, "not valid JSON"),
    ({"message": {"content": "[1, 2]"}}, None, "not a JSON object"),
    ({"error": "model failed"}, None, "returned an error"),
])
def test_failures_raise_llm_error_so_callers_fall_back(calls, reply, error, message):
    calls(reply, error)
    with pytest.raises(LLMError, match=message):
        ollama_provider.OllamaProvider().complete_json("s", "u")


def test_assistant_falls_back_to_the_standard_answer_when_ollama_is_down(client, create_user, calls):
    calls(error=urllib.error.URLError("refused"))
    llm.set_llm_provider(ollama_provider.OllamaProvider(), override=True)
    user = create_user()
    cid = client.post("/assistant/conversations", headers=user["headers"], json={}).json()["conversation_id"]
    answer = client.post(f"/assistant/conversations/{cid}/messages", headers=user["headers"],
                         json={"message": "How do I upload my resume?", "use_llm": True, "llm_consent": True}).json()
    reply = answer["assistant_message"]
    assert reply["generation_method"] == "deterministic"
    assert reply["content"].startswith("Here is what the CareerNova AI guide says:")      # the guide's own text
    assert any(w["code"] in ("llm_unavailable", "llm_unverified") for w in reply["warnings"])


def test_assistant_disclosure_names_a_local_model_as_local(client, create_user):
    llm.set_llm_provider(ollama_provider.OllamaProvider(), override=True)
    caps = client.get("/assistant/capabilities", headers=create_user()["headers"]).json()["llm"]
    assert caps["location"] == "local"
    assert "a language model running on this server (ollama)" in caps["assistant_disclosure"]
    assert "running on this server" in caps["disclosure"]
    assert "external language-model" not in caps["assistant_disclosure"]
    assert "external language-model" not in caps["disclosure"]
