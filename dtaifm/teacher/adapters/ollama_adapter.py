"""Ollama local teacher adapter.

Talks to a local Ollama server via ``POST /api/chat``. Default endpoint is
``http://localhost:11434``; override via the ``--teacher-base-url`` CLI flag
or the ``DTAIFM_OLLAMA_BASE_URL`` environment variable.

Returns a portable RuleSet by routing the model's text response through the
shared strict parser (parse_provider_text). Provider narration outside the
JSON block is tolerated; malformed output fails clearly.

Local models improve privacy and adoption, but they are still untrusted teachers.
"""

from __future__ import annotations

import os
from typing import Any

from dtaifm.teacher.adapters._http import HttpJsonClient
from dtaifm.teacher.base import Teacher
from dtaifm.teacher.contract import TeacherRequest, TeacherResponse
from dtaifm.teacher.parser import ProviderResponseError, parse_provider_text


class OllamaTeacher(Teacher):
    """Translator for a local Ollama server. Never validates or executes."""

    DEFAULT_BASE_URL = "http://localhost:11434"
    DEFAULT_MODEL = "llama3.2"
    BASE_URL_ENV = "DTAIFM_OLLAMA_BASE_URL"
    MODEL_ENV = "DTAIFM_OLLAMA_MODEL"
    CHAT_PATH = "/api/chat"

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        client: Any | None = None,
        timeout: float = 60.0,
    ) -> None:
        self._client = client if client is not None else HttpJsonClient(timeout=timeout)
        self._base_url = _resolve_base_url(base_url, self.BASE_URL_ENV, self.DEFAULT_BASE_URL)
        self._model = model or os.environ.get(self.MODEL_ENV) or self.DEFAULT_MODEL

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def model(self) -> str:
        return self._model

    def propose(self, request: TeacherRequest) -> TeacherResponse:
        prompt = self.render_prompt(request)
        body = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            # Ollama's JSON-mode hint; the parser still tolerates narration.
            "format": "json",
        }
        url = f"{self._base_url}{self.CHAT_PATH}"
        try:
            response = self._client.post_json(url, body)
        except OSError as exc:
            raise RuntimeError(f"ollama: failed to reach {url}: {exc}") from exc

        content = _extract_ollama_content(response)
        ruleset = parse_provider_text(content, source="ollama")
        return TeacherResponse(ruleset=ruleset, raw_provider_output=content)


def _extract_ollama_content(response: Any) -> str:
    """Pull the assistant's text out of an Ollama /api/chat response."""
    if not isinstance(response, dict):
        raise ProviderResponseError(f"ollama: expected JSON object response, got {type(response).__name__}")
    message = response.get("message")
    if not isinstance(message, dict):
        raise ProviderResponseError("ollama: response missing 'message' object")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ProviderResponseError("ollama: response missing 'message.content' text")
    return content


def _resolve_base_url(provided: str | None, env_var: str, default: str) -> str:
    """CLI arg > env var > default, with trailing slash stripped."""
    url = provided or os.environ.get(env_var) or default
    return url.rstrip("/")
