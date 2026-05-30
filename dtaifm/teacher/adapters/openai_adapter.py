"""OpenAI teacher adapter — translator, not trusted component.

Install with: ``pip install 'dtaifm[openai]'``
Requires:     ``OPENAI_API_KEY`` environment variable for live calls.
Optional:     ``OPENAI_MODEL`` to override the default model.

This adapter:
  - calls OpenAI's Responses API with the shared teacher prompt and a
    Structured-Outputs JSON schema (``text.format`` = ``json_schema``)
  - parses the returned text strictly via dtaifm.teacher.parser
  - returns a portable RuleSet artifact, NEVER validates or executes

A test can inject a fake client via the ``client=`` constructor argument; in that
case the SDK import and API key check are both skipped.

Why ``strict`` is False
-----------------------
OpenAI Structured Outputs in *strict* mode require ``additionalProperties: false``
on every object and every property listed in ``required``. dtaifm rules are
deliberately open-ended in two places: action ``parameters`` (e.g.
``{"duration": 300}``) and per-type condition parameters (``time_range`` carries
``start_hour``/``end_hour``; ``device_state`` carries ``device``/``state``).
Forcing strict mode would forbid exactly those fields and flatten the rule
vocabulary. So the schema below is a non-strict guide that mirrors the Anthropic
adapter's tool schema, and the deterministic parser
(``parse_provider_text`` -> ``parse_provider_payload``) remains the authoritative
gate — the adapter never validates, it only translates.
"""

from __future__ import annotations

import os
from typing import Any

from dtaifm.schema import SCHEMA_VERSION
from dtaifm.teacher.base import Teacher
from dtaifm.teacher.contract import TeacherRequest, TeacherResponse
from dtaifm.teacher.parser import ProviderResponseError, parse_provider_text


# Mirrors the Anthropic adapter's tool input_schema, trimmed to the structural
# requirements the parser enforces. Used as a non-strict Structured-Outputs guide
# (see module docstring): inner objects intentionally omit additionalProperties so
# action `parameters` and type-specific condition params can flow through.
_RULESET_JSON_SCHEMA: dict = {
    "type": "object",
    "required": ["schema_version", "rules"],
    "properties": {
        "schema_version": {"const": SCHEMA_VERSION},
        "rules": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": [
                    "id", "name", "trigger", "actions",
                    "satisfies_constraints", "rationale",
                ],
                "properties": {
                    "id": {"type": "string", "minLength": 1},
                    "name": {"type": "string"},
                    "trigger": {
                        "type": "object",
                        "required": ["device", "event"],
                        "properties": {
                            "device": {"type": "string"},
                            "event": {"type": "string"},
                        },
                    },
                    "conditions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["type"],
                            "properties": {"type": {"type": "string"}},
                        },
                    },
                    "actions": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "object",
                            "required": ["device", "action"],
                            "properties": {
                                "device": {"type": "string"},
                                "action": {"type": "string"},
                            },
                        },
                    },
                    "satisfies_constraints": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "string"},
                    },
                    "explanation": {"type": "string"},
                    "rationale": {"type": "string", "minLength": 1},
                },
            },
        },
    },
}

# Responses-API ``text`` argument carrying the Structured-Outputs format.
RULESET_TEXT_FORMAT: dict = {
    "format": {
        "type": "json_schema",
        "name": "dtaifm_ruleset",
        "schema": _RULESET_JSON_SCHEMA,
        "strict": False,
    }
}


class OpenAITeacher(Teacher):
    """Translates OpenAI Responses API output into a portable RuleSet artifact."""

    DEFAULT_MODEL = "gpt-5.5"
    MODEL_ENV = "OPENAI_MODEL"

    def __init__(
        self,
        model: str | None = None,
        client: Any = None,
        max_output_tokens: int | None = None,
    ) -> None:
        self._client = client if client is not None else self._build_real_client()
        self._model = model or os.environ.get(self.MODEL_ENV) or self.DEFAULT_MODEL
        self._max_output_tokens = max_output_tokens

    @property
    def model(self) -> str:
        return self._model

    # ----- public API -------------------------------------------------

    def propose(self, request: TeacherRequest) -> TeacherResponse:
        prompt = self.render_prompt(request)
        kwargs: dict[str, Any] = {
            "model": self._model,
            "input": [{"role": "user", "content": prompt}],
            "text": RULESET_TEXT_FORMAT,
        }
        if self._max_output_tokens is not None:
            kwargs["max_output_tokens"] = self._max_output_tokens

        response = self._client.responses.create(**kwargs)
        content = _extract_output_text(response)
        ruleset = parse_provider_text(content, source="openai")
        return TeacherResponse(ruleset=ruleset, raw_provider_output=content)

    # ----- internals --------------------------------------------------

    @staticmethod
    def _build_real_client():
        try:
            import openai  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ImportError(
                "OpenAI SDK not installed. Install with: pip install 'dtaifm[openai]'"
            ) from exc
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY environment variable not set. "
                "Get a key at https://platform.openai.com/api-keys and export it before running."
            )
        return openai.OpenAI(api_key=api_key)


def _extract_output_text(response: Any) -> str:
    """Pull the aggregated assistant text out of a Responses API result.

    The SDK exposes ``response.output_text`` as the convenience accessor that
    concatenates the model's message text. A response that carries no text
    (e.g. reasoning-only or a refusal) fails clearly.
    """
    text = getattr(response, "output_text", None)
    if not isinstance(text, str) or not text.strip():
        raise ProviderResponseError(
            "openai: response did not include any output text (expected response.output_text)"
        )
    return text
