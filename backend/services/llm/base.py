"""LLM provider interface and configuration.

LLM generation is OFF unless the environment sets either
``LLM_PROVIDER=groq`` with ``GROQ_API_KEY`` (external), or ``LLM_PROVIDER=ollama`` with optional
``OLLAMA_URL`` / ``OLLAMA_MODEL`` (a local model such as Gemma 3). Even then, it is used only
for documents where the student explicitly opts in and confirms consent.

Rules enforced here and in the generators:
* Only content facts are sent; contact details are never included
  (``assert_no_contact`` checks every payload before sending).
* Neither API keys nor resume content are logged.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Protocol

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[3] / ".env")

PRIVACY_DISCLOSURE = (
    "With AI-assisted writing, the content of your resume that is relevant to this "
    "document (summary, skills, education, experience and project descriptions) and the "
    "internship details are sent to {destination} ({provider}). "
    "Your name, e-mail address, phone number, links, location, postal address and PIN code "
    "are never sent: they are removed from the request first. "
    "Every generated statement is checked against your resume; unsupported statements "
    "are replaced automatically."
)


class LLMError(RuntimeError):
    """The provider could not produce a usable response (message is safe to show)."""


class LLMProvider(Protocol):
    name: str
    model: str

    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        """Return the model's JSON object response."""


_provider: LLMProvider | None = None
_override = False
_lock = threading.Lock()


def get_llm_provider() -> LLMProvider | None:
    """Configured provider, or None when LLM generation is not configured."""
    if _override:
        return _provider

    choice = os.getenv("LLM_PROVIDER", "none").strip().lower()
    timeout = float(os.getenv("LLM_TIMEOUT_SECONDS", "30"))
    if choice == "ollama":
        from backend.services.llm.ollama_provider import DEFAULT_MODEL, DEFAULT_URL, OllamaProvider

        try:
            return OllamaProvider(
                base_url=os.getenv("OLLAMA_URL", DEFAULT_URL).strip() or DEFAULT_URL,
                model=os.getenv("OLLAMA_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL,
                # Local models on a CPU can need over a minute for the first answer (model load).
                timeout=float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120")),
            )
        except LLMError:
            return None                      # misconfigured: AI stays off (reported by llm_status)
    if choice != "groq":
        return None
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        return None

    from backend.services.llm.groq_provider import GroqProvider

    return GroqProvider(
        api_key=api_key,
        model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        timeout=timeout,
    )


def set_llm_provider(provider: LLMProvider | None, override: bool = True) -> None:
    """Install a provider explicitly (tests); ``override=False`` restores env config."""
    global _provider, _override
    with _lock:
        _provider = provider
        _override = override


DESTINATIONS = {
    "local": "a language model running on this server",
    "external": "an external language-model provider",
}


def disclosure_for(provider: LLMProvider) -> str:
    """Privacy notice naming where the data actually goes (local model vs external service)."""
    location = "local" if getattr(provider, "is_local", False) else "external"
    return PRIVACY_DISCLOSURE.format(destination=DESTINATIONS[location], provider=provider.name)


def llm_status() -> dict[str, Any]:
    provider = get_llm_provider()
    status = {
        "available": provider is not None,
        "provider": provider.name if provider else None,
        "model": provider.model if provider else None,
        "disclosure": disclosure_for(provider) if provider else None,
    }
    if provider is not None:
        # "local" when the model runs on this machine (Ollama on localhost), else "external".
        status["location"] = "local" if getattr(provider, "is_local", False) else "external"
    return status


def assert_no_contact(payload: Any, contact: dict[str, str | None]) -> None:
    """Raise if any contact detail appears anywhere in the payload."""
    serialized = json.dumps(payload, ensure_ascii=False).casefold()
    for key, value in contact.items():
        if not value or not isinstance(value, str) or len(value.strip()) < 3:
            continue
        if key == "location":
            continue  # a city name may legitimately appear in internship data
        if value.strip().casefold() in serialized:
            raise LLMError("Refusing to send personal contact information to the LLM provider.")
