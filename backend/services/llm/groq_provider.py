"""Groq chat-completions provider (OpenAI-compatible HTTP API).

Uses only the Python standard library (no extra dependency). The API key
is sent only in the Authorization header; it is never logged or included
in error messages, and response/request bodies are never logged.
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from typing import Any

from backend.services.llm.base import LLMError

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
MAX_RESPONSE_BYTES = 200_000


class GroqProvider:
    name = "groq"

    def __init__(self, api_key: str, model: str, timeout: float = 30.0, max_tokens: int = 1500):
        if not api_key:
            raise LLMError("Groq is not configured.")
        self._api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_tokens = max_tokens

    def __repr__(self) -> str:  # never expose the key
        return f"GroqProvider(model={self.model!r})"

    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        body = json.dumps({
            "model": self.model,
            "temperature": 0.2,
            "max_tokens": self.max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }).encode("utf-8")

        request = urllib.request.Request(
            GROQ_CHAT_URL,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            raise LLMError(f"The language-model provider returned HTTP {exc.code}.") from None
        except (urllib.error.URLError, socket.timeout, TimeoutError, OSError):
            raise LLMError("The language-model provider could not be reached.") from None

        if len(raw) > MAX_RESPONSE_BYTES:
            raise LLMError("The language-model response was too large.")

        try:
            data = json.loads(raw.decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
        except (ValueError, KeyError, IndexError, TypeError):
            raise LLMError("The language-model response was not valid JSON.") from None

        if not isinstance(parsed, dict):
            raise LLMError("The language-model response was not a JSON object.")
        return parsed
