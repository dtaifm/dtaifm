"""Tests for the Anthropic teacher adapter — no live network calls.

All tests inject a fake client via the ``client=`` constructor argument, so the
Anthropic SDK does not need to be installed for these tests to run.
"""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from dtaifm.core.constraint import Constraint, ConstraintType
from dtaifm.schema import SCHEMA_VERSION
from dtaifm.teacher.adapters.anthropic_adapter import AnthropicTeacher, SUBMIT_RULESET_TOOL
from dtaifm.teacher.contract import PromptContext, TeacherRequest
from dtaifm.teacher.parser import ProviderResponseError


def _sample_constraints() -> list[Constraint]:
    return [
        Constraint(
            id="no_auto_unlock",
            description="Never unlock doors automatically.",
            type=ConstraintType.ABSOLUTE_PROHIBITION,
            parameters={"applies_to": ["front_door"], "action": "unlock"},
        ),
    ]


def _valid_tool_use_block():
    block = SimpleNamespace()
    block.type = "tool_use"
    block.name = "submit_ruleset"
    block.input = {
        "schema_version": SCHEMA_VERSION,
        "rules": [
            {
                "id": "r_safe",
                "name": "Safe Rule",
                "trigger": {"device": "motion_sensor", "event": "motion_detected"},
                "conditions": [{"type": "mode_not", "mode": "security"}],
                "actions": [{"device": "hallway_light", "action": "turn_on"}],
                "satisfies_constraints": ["motion_light_hours"],
                "rationale": "Demonstrates a valid teacher proposal.",
                "explanation": "A safe motion light.",
            }
        ],
    }
    return block


def _build_fake_client(content_blocks):
    response = SimpleNamespace(content=content_blocks)
    client = MagicMock()
    client.messages.create.return_value = response
    return client


# ----------------------------------------------------------------------
# Happy path
# ----------------------------------------------------------------------

def test_adapter_parses_valid_tool_use_response():
    client = _build_fake_client([_valid_tool_use_block()])
    teacher = AnthropicTeacher(client=client)
    request = TeacherRequest(constraints=_sample_constraints(), context=PromptContext(domain="smart_home"))
    response = teacher.propose(request)
    assert len(response.ruleset) == 1
    rule = next(iter(response.ruleset))
    assert rule.id == "r_safe"
    assert rule.rationale.startswith("Demonstrates")


def test_adapter_sends_prompt_and_tool_to_provider():
    client = _build_fake_client([_valid_tool_use_block()])
    teacher = AnthropicTeacher(client=client, model="claude-test-model")
    request = TeacherRequest(constraints=_sample_constraints(), context=PromptContext(domain="smart_home"))
    teacher.propose(request)

    _, kwargs = client.messages.create.call_args
    assert kwargs["model"] == "claude-test-model"
    assert kwargs["tools"] == [SUBMIT_RULESET_TOOL]
    assert kwargs["tool_choice"] == {"type": "tool", "name": "submit_ruleset"}
    sent_prompt = kwargs["messages"][0]["content"]
    assert "no_auto_unlock" in sent_prompt
    assert "smart_home" in sent_prompt


def test_adapter_default_model_is_claude_sonnet_4_6():
    client = _build_fake_client([_valid_tool_use_block()])
    teacher = AnthropicTeacher(client=client)
    teacher.propose(TeacherRequest(constraints=_sample_constraints()))
    _, kwargs = client.messages.create.call_args
    assert kwargs["model"] == "claude-sonnet-4-6"


def test_adapter_does_not_validate_or_execute():
    # An unsafe rule (empty satisfies_constraints) would normally be rejected by
    # the strict parser. Confirm the adapter never reaches downstream gates: the
    # raw provider output is preserved and execution is not attempted.
    block = _valid_tool_use_block()
    block.input["rules"][0]["satisfies_constraints"] = ["c"]  # keep parser happy
    client = _build_fake_client([block])
    teacher = AnthropicTeacher(client=client)
    response = teacher.propose(TeacherRequest(constraints=_sample_constraints()))
    # No validator, no runtime — just a portable artifact.
    assert response.raw_provider_output  # preserved in-memory (diagnostic only; never serialized)
    assert len(response.ruleset) == 1


# ----------------------------------------------------------------------
# Failure modes
# ----------------------------------------------------------------------

def test_adapter_fails_when_response_has_no_tool_use_block():
    text_block = SimpleNamespace(type="text", text="I cannot comply.")
    client = _build_fake_client([text_block])
    teacher = AnthropicTeacher(client=client)
    with pytest.raises(ProviderResponseError, match="did not include the submit_ruleset"):
        teacher.propose(TeacherRequest(constraints=_sample_constraints()))


def test_adapter_fails_when_tool_use_has_wrong_name():
    other = SimpleNamespace(type="tool_use", name="some_other_tool", input={})
    client = _build_fake_client([other])
    teacher = AnthropicTeacher(client=client)
    with pytest.raises(ProviderResponseError, match="did not include the submit_ruleset"):
        teacher.propose(TeacherRequest(constraints=_sample_constraints()))


def test_adapter_propagates_parser_errors_for_malformed_payload():
    block = _valid_tool_use_block()
    del block.input["rules"][0]["rationale"]
    client = _build_fake_client([block])
    teacher = AnthropicTeacher(client=client)
    with pytest.raises(ProviderResponseError, match="rationale"):
        teacher.propose(TeacherRequest(constraints=_sample_constraints()))


def test_adapter_propagates_parser_error_for_unknown_condition_type():
    block = _valid_tool_use_block()
    block.input["rules"][0]["conditions"] = [{"type": "wildcard_kind"}]
    client = _build_fake_client([block])
    teacher = AnthropicTeacher(client=client)
    with pytest.raises(ProviderResponseError, match="unknown type 'wildcard_kind'"):
        teacher.propose(TeacherRequest(constraints=_sample_constraints()))


def test_adapter_constructor_fails_clearly_when_sdk_missing(monkeypatch):
    # Force `import anthropic` to fail even if the SDK is installed in the test env.
    monkeypatch.setitem(sys.modules, "anthropic", None)
    with pytest.raises(ImportError, match=r"dtaifm\[anthropic\]"):
        AnthropicTeacher._build_real_client()


def test_adapter_constructor_fails_clearly_when_api_key_missing(monkeypatch):
    # Pretend the SDK is installed so the API-key check is reached.
    fake_sdk = SimpleNamespace(Anthropic=lambda api_key: MagicMock())
    monkeypatch.setitem(sys.modules, "anthropic", fake_sdk)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        AnthropicTeacher._build_real_client()
