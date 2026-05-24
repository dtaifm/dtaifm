"""Anthropic Claude teacher adapter — translator, not trusted component.

Install with: ``pip install 'dtaifm[anthropic]'``
Requires:     ``ANTHROPIC_API_KEY`` environment variable for live calls.
Optional:     ``ANTHROPIC_MODEL`` to override the default model.

This adapter:
  - calls Claude with the shared teacher prompt and a structured-output tool
  - parses the tool's input strictly via dtaifm.teacher.parser
  - returns a portable RuleSet artifact, NEVER validates or executes

A test can inject a fake client via the ``client=`` constructor argument; in that
case the SDK import and API key check are both skipped.
"""

from __future__ import annotations

import os
from typing import Any

from dtaifm.schema import SCHEMA_VERSION
from dtaifm.teacher.base import Teacher
from dtaifm.teacher.contract import TeacherRequest, TeacherResponse
from dtaifm.teacher.parser import ProviderResponseError, parse_provider_payload


# Tool input_schema mirrors the published RULES_SCHEMA, trimmed to what Anthropic
# tool-use accepts. Keeping the structural requirements here gives Claude the
# best chance of returning a payload the parser will accept on the first try.
_RULESET_TOOL_INPUT_SCHEMA: dict = {
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

SUBMIT_RULESET_TOOL: dict = {
    "name": "submit_ruleset",
    "description": (
        "Submit your candidate RuleSet. Each rule MUST include a non-empty "
        "satisfies_constraints list and a non-empty rationale explaining why "
        "you chose it. A deterministic Validator will reject rules that violate "
        "any constraint — your output is an artifact, not an action."
    ),
    "input_schema": _RULESET_TOOL_INPUT_SCHEMA,
}


class AnthropicTeacher(Teacher):
    """Translates Anthropic Claude output into a portable RuleSet artifact."""

    DEFAULT_MODEL = "claude-sonnet-4-6"

    def __init__(
        self,
        model: str | None = None,
        client: Any = None,
        max_tokens: int = 4096,
    ) -> None:
        self._client = client if client is not None else self._build_real_client()
        self._model = model or os.environ.get("ANTHROPIC_MODEL") or self.DEFAULT_MODEL
        self._max_tokens = max_tokens

    # ----- public API -------------------------------------------------

    def propose(self, request: TeacherRequest) -> TeacherResponse:
        prompt = self.render_prompt(request)
        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            messages=[{"role": "user", "content": prompt}],
            tools=[SUBMIT_RULESET_TOOL],
            tool_choice={"type": "tool", "name": "submit_ruleset"},
        )
        tool_use = self._extract_tool_use(response)
        if tool_use is None:
            raise ProviderResponseError(
                "anthropic: response did not include the submit_ruleset tool call"
            )
        ruleset = parse_provider_payload(tool_use.input, source="anthropic")
        return TeacherResponse(
            ruleset=ruleset,
            raw_provider_output=str(getattr(response, "content", "")),
        )

    # ----- internals --------------------------------------------------

    @staticmethod
    def _build_real_client():
        try:
            import anthropic  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ImportError(
                "Anthropic SDK not installed. Install with: pip install 'dtaifm[anthropic]'"
            ) from exc
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY environment variable not set. "
                "Get a key at https://console.anthropic.com/ and export it before running."
            )
        return anthropic.Anthropic(api_key=api_key)

    @staticmethod
    def _extract_tool_use(response: Any):
        for block in getattr(response, "content", []) or []:
            if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == "submit_ruleset":
                return block
        return None
