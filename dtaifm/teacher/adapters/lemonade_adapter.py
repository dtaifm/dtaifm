"""Lemonade local teacher adapter (OpenAI-compatible surface).

Talks to a local Lemonade server via ``POST /v1/chat/completions``. Default
endpoint is ``http://localhost:13305``; override via the ``--teacher-base-url``
CLI flag or the ``DTAIFM_LEMONADE_BASE_URL`` environment variable.

Returns a portable RuleSet by routing the model's text response through the
shared strict parser. Local models are still untrusted teachers.
"""

from __future__ import annotations

import os
from typing import Any

from dtaifm.teacher.adapters._http import HttpJsonClient
from dtaifm.teacher.base import Teacher
from dtaifm.teacher.contract import TeacherRequest, TeacherResponse
from dtaifm.teacher.parser import ProviderResponseError, parse_provider_text


class LemonadeTeacher(Teacher):
    """Translator for a local Lemonade server. Never validates or executes."""

    DEFAULT_BASE_URL = "http://localhost:13305"
    DEFAULT_MODEL = "Qwen3-0.6B-GGUF"
    BASE_URL_ENV = "DTAIFM_LEMONADE_BASE_URL"
    MODEL_ENV = "DTAIFM_LEMONADE_MODEL"
    CHAT_PATH = "/v1/chat/completions"

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
            # OpenAI JSON-mode hint; parse_provider_text still tolerates narration.
            "response_format": {"type": "json_object"},
        }
        url = f"{self._base_url}{self.CHAT_PATH}"
        try:
            response = self._client.post_json(url, body)
        except OSError as exc:
            raise RuntimeError(f"lemonade: failed to reach {url}: {exc}") from exc

        content = _extract_openai_content(response, source="lemonade")
        ruleset = parse_provider_text(content, source="lemonade")
        return TeacherResponse(ruleset=ruleset, raw_provider_output=content)


def _extract_openai_content(response: Any, *, source: str) -> str:
    if not isinstance(response, dict):
        raise ProviderResponseError(
            f"{source}: expected JSON object response, got {type(response).__name__}"
        )
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ProviderResponseError(f"{source}: response missing 'choices' list")
    first = choices[0]
    if not isinstance(first, dict):
        raise ProviderResponseError(f"{source}: response 'choices[0]' is not an object")
    message = first.get("message")
    if not isinstance(message, dict):
        raise ProviderResponseError(f"{source}: response 'choices[0].message' missing")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ProviderResponseError(f"{source}: response 'choices[0].message.content' missing or empty")
    return content


def _resolve_base_url(provided: str | None, env_var: str, default: str) -> str:
    url = provided or os.environ.get(env_var) or default
    return url.rstrip("/")
