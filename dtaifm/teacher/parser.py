"""Strict parser for provider responses.

Every provider adapter routes its output through this parser so the framework
never trusts unstructured model output. The parser converts a dict payload into
a RuleSet only after asserting:

  - schema_version matches the supported version
  - the top-level shape is correct
  - every rule has all required fields, including provenance (rationale) and
    a non-empty satisfies_constraints list
  - condition types are from the known set
  - trigger and actions are well-formed

Any deviation raises ProviderResponseError with a precise location and reason.
"""

import json
import re
from typing import Any

from dtaifm.core.rule import Rule
from dtaifm.core.ruleset import RuleSet
from dtaifm.schema import SCHEMA_VERSION


class ProviderResponseError(ValueError):
    """Raised when a provider returns an unparseable or non-compliant response."""


KNOWN_CONDITION_TYPES: frozenset[str] = frozenset(
    {"time_range", "mode_not", "mode_is", "device_state"}
)


def parse_provider_payload(data: Any, *, source: str) -> RuleSet:
    """Strictly validate a provider's parsed payload and return a RuleSet."""
    if not isinstance(data, dict):
        raise ProviderResponseError(f"{source}: response must be a JSON object, got {type(data).__name__}")

    version = data.get("schema_version")
    if version is None:
        raise ProviderResponseError(f"{source}: response missing 'schema_version' field")
    if version != SCHEMA_VERSION:
        raise ProviderResponseError(
            f"{source}: response schema_version is {version!r}; expected {SCHEMA_VERSION!r}"
        )

    rules_data = data.get("rules")
    if not isinstance(rules_data, list):
        raise ProviderResponseError(f"{source}: response 'rules' must be a list")

    rules = [_parse_rule(rd, source=source, index=i) for i, rd in enumerate(rules_data)]
    return RuleSet(rules=rules, source=source)


def parse_provider_text(text: str, *, source: str) -> RuleSet:
    """Extract a JSON object from arbitrary provider text and parse it.

    Provider narration outside the JSON block is ignored. If no JSON object is
    found, ProviderResponseError is raised.
    """
    payload = _extract_json_object(text)
    if payload is None:
        raise ProviderResponseError(f"{source}: response contains no JSON object")
    return parse_provider_payload(payload, source=source)


# ----------------------------------------------------------------------
# internal
# ----------------------------------------------------------------------

_REQUIRED_RULE_FIELDS = ("id", "name", "trigger", "actions", "satisfies_constraints", "rationale")


def _parse_rule(data: Any, *, source: str, index: int) -> Rule:
    ctx = f"{source}: rule[{index}]"
    if not isinstance(data, dict):
        raise ProviderResponseError(f"{ctx} must be an object")

    for field_name in _REQUIRED_RULE_FIELDS:
        if field_name not in data:
            raise ProviderResponseError(f"{ctx} missing required field '{field_name}'")

    if not isinstance(data["satisfies_constraints"], list) or not data["satisfies_constraints"]:
        raise ProviderResponseError(
            f"{ctx} 'satisfies_constraints' must be a non-empty list — every rule must declare "
            f"which constraints it honors"
        )

    if not isinstance(data["rationale"], str) or not data["rationale"].strip():
        raise ProviderResponseError(
            f"{ctx} 'rationale' must be a non-empty string — every rule must explain why "
            f"the teacher proposed it"
        )

    trigger = data["trigger"]
    if not isinstance(trigger, dict) or "device" not in trigger or "event" not in trigger:
        raise ProviderResponseError(f"{ctx} 'trigger' must be an object with 'device' and 'event'")

    actions = data["actions"]
    if not isinstance(actions, list) or not actions:
        raise ProviderResponseError(f"{ctx} 'actions' must be a non-empty list")
    for j, action in enumerate(actions):
        if not isinstance(action, dict):
            raise ProviderResponseError(f"{ctx} actions[{j}] must be an object")
        if "device" not in action or "action" not in action:
            raise ProviderResponseError(f"{ctx} actions[{j}] must have 'device' and 'action'")

    conditions = data.get("conditions", [])
    if not isinstance(conditions, list):
        raise ProviderResponseError(f"{ctx} 'conditions' must be a list")
    for j, condition in enumerate(conditions):
        if not isinstance(condition, dict) or "type" not in condition:
            raise ProviderResponseError(f"{ctx} conditions[{j}] must be an object with 'type'")
        if condition["type"] not in KNOWN_CONDITION_TYPES:
            raise ProviderResponseError(
                f"{ctx} conditions[{j}] has unknown type {condition['type']!r}. "
                f"Known: {sorted(KNOWN_CONDITION_TYPES)}"
            )

    return Rule.from_dict(data)


_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _extract_json_object(text: str) -> dict | None:
    """Find the first JSON object in `text`. Supports fenced or bare JSON."""
    fence = _FENCE_RE.search(text)
    if fence:
        try:
            return json.loads(fence.group(1))
        except json.JSONDecodeError:
            pass

    decoder = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(text[i:])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return None
