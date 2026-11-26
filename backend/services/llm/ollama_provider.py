"""Optional local LLM provider: Ollama (e.g. Gemma 3) via its HTTP API.

Enabled with ``LLM_PROVIDER=ollama``. Settings:
    OLLAMA_URL    base URL of the Ollama server (default http://127.0.0.1:11434)
    OLLAMA_MODEL  model name as listed by ``ollama list`` (default gemma3)
    LLM_TIMEOUT_SECONDS  request timeout (default 30; local models can be slow on CPU)

The same safety rules as for Groq apply: the provider only ever receives the already-filtered,
consented payloads built by the generators, and every answer is fact-checked before use. If the
server is unreachable, the model is missing or the answer is not valid JSON, ``LLMError`` is raised
and the caller falls back to the deterministic answer - nothing is faked.
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

from backend.services.llm.base import LLMError

MAX_RESPONSE_BYTES = 200_000
DEFAULT_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "gemma3"


class OllamaProvider:
    name = "ollama"

    def __init__(self, base_url: str = DEFAULT_URL, model: str = DEFAULT_MODEL, timeout: float = 30.0,
                 max_tokens: int = 1500):
        parsed = urlparse(base_url or "")
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise LLMError("OLLAMA_URL must be an http(s) URL such as http://127.0.0.1:11434.")
        if not model or not model.strip():
            raise LLMError("OLLAMA_MODEL is not set.")
        self.base_url = base_url.rstrip("/")
        self.model = model.strip()
        self.timeout = timeout
        self.max_tokens = max_tokens

    @property
    def is_local(self) -> bool:
        return urlparse(self.base_url).hostname in ("127.0.0.1", "localhost", "::1")

    def __repr__(self) -> str:
        return f"OllamaProvider(model={self.model!r}, local={self.is_local})"

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{self.base_url}{path}", data=json.dumps(payload).encode("utf-8"), method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise LLMError(f"The local model '{self.model}' is not available in Ollama "
                               f"(run: ollama pull {self.model}).") from None
            raise LLMError(f"The Ollama server returned HTTP {exc.code}.") from None
        except (urllib.error.URLError, socket.timeout, TimeoutError, OSError):
            raise LLMError("The Ollama server could not be reached (is it running?).") from None
        if len(raw) > MAX_RESPONSE_BYTES:
            raise LLMError("The language-model response was too large.")
        try:
            return json.loads(raw.decode("utf-8"))
        except ValueError:
            raise LLMError("The Ollama server returned an invalid response.") from None

    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        data = self._post("/api/chat", {
            "model": self.model,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.2, "num_predict": self.max_tokens},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        })
        if data.get("error"):
            raise LLMError("The local model returned an error.")
        try:
            parsed = json.loads(data["message"]["content"])
        except (ValueError, KeyError, TypeError):
            raise LLMError("The language-model response was not valid JSON.") from None
        if not isinstance(parsed, dict):
            raise LLMError("The language-model response was not a JSON object.")
        return parsed
