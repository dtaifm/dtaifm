"""Tests for the OpenAI teacher adapter — no live network calls.

All tests inject a fake client via the ``client=`` constructor argument, so the
OpenAI SDK does not need to be installed for these tests to run. The fake mimics
the Responses API surface the adapter uses: ``client.responses.create(...)``
returning an object with an ``output_text`` attribute.
"""

import json
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from dtaifm.core.constraint import Constraint, ConstraintType
from dtaifm.schema import SCHEMA_VERSION
from dtaifm.teacher.adapters.openai_adapter import OpenAITeacher, RULESET_TEXT_FORMAT
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


def _valid_ruleset_payload() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "rules": [
            {
                "id": "r_safe",
                "name": "Safe Rule",
                "trigger": {"device": "motion_sensor", "event": "motion_detected"},
                "conditions": [{"type": "mode_not", "mode": "security"}],
                "actions": [{"device": "hallway_light", "action": "turn_on", "parameters": {"duration": 300}}],
                "satisfies_constraints": ["motion_light_hours"],
                "rationale": "Demonstrates a valid teacher proposal.",
                "explanation": "A safe motion light.",
            }
        ],
    }


def _build_fake_client(output_text: str) -> MagicMock:
    response = SimpleNamespace(output_text=output_text)
    client = MagicMock()
    client.responses.create.return_value = response
    return client


def _request() -> TeacherRequest:
    return TeacherRequest(
        constraints=_sample_constraints(),
        context=PromptContext(domain="smart_home"),
    )


# ----------------------------------------------------------------------
# Happy path
# ----------------------------------------------------------------------

def test_adapter_parses_valid_structured_output():
    client = _build_fake_client(json.dumps(_valid_ruleset_payload()))
    teacher = OpenAITeacher(client=client)
    response = teacher.propose(_request())
    assert len(response.ruleset) == 1
    rule = next(iter(response.ruleset))
    assert rule.id == "r_safe"
    assert rule.rationale.startswith("Demonstrates")


def test_adapter_tolerates_narration_around_json():
    # strict=False structured output is a guide, not a guarantee; the shared
    # parser still extracts the JSON object from any surrounding narration.
    content = (
        "Here is the ruleset you asked for:\n\n"
        f"```json\n{json.dumps(_valid_ruleset_payload())}\n```\n\nHope that helps!"
    )
    client = _build_fake_client(content)
    teacher = OpenAITeacher(client=client)
    assert len(teacher.propose(_request()).ruleset) == 1


def test_adapter_sends_prompt_and_text_format_to_provider():
    client = _build_fake_client(json.dumps(_valid_ruleset_payload()))
    teacher = OpenAITeacher(client=client, model="gpt-test-model")
    teacher.propose(_request())

    _, kwargs = client.responses.create.call_args
    assert kwargs["model"] == "gpt-test-model"
    assert kwargs["text"] == RULESET_TEXT_FORMAT
    assert kwargs["text"]["format"]["type"] == "json_schema"
    # max_output_tokens is omitted unless explicitly configured.
    assert "max_output_tokens" not in kwargs
    sent_prompt = kwargs["input"][0]["content"]
    assert kwargs["input"][0]["role"] == "user"
    assert "no_auto_unlock" in sent_prompt
    assert "smart_home" in sent_prompt


def test_adapter_passes_max_output_tokens_when_set():
    client = _build_fake_client(json.dumps(_valid_ruleset_payload()))
    teacher = OpenAITeacher(client=client, max_output_tokens=2048)
    teacher.propose(_request())
    _, kwargs = client.responses.create.call_args
    assert kwargs["max_output_tokens"] == 2048


def test_adapter_default_model_is_gpt_5_5(monkeypatch):
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    client = _build_fake_client(json.dumps(_valid_ruleset_payload()))
    teacher = OpenAITeacher(client=client)
    teacher.propose(TeacherRequest(constraints=_sample_constraints()))
    _, kwargs = client.responses.create.call_args
    assert kwargs["model"] == "gpt-5.5"


def test_adapter_env_model_override(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL", "gpt-from-env")
    client = _build_fake_client(json.dumps(_valid_ruleset_payload()))
    teacher = OpenAITeacher(client=client)
    teacher.propose(_request())
    _, kwargs = client.responses.create.call_args
    assert kwargs["model"] == "gpt-from-env"


def test_adapter_explicit_model_beats_env(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL", "gpt-from-env")
    client = _build_fake_client(json.dumps(_valid_ruleset_payload()))
    teacher = OpenAITeacher(client=client, model="gpt-explicit")
    teacher.propose(_request())
    _, kwargs = client.responses.create.call_args
    assert kwargs["model"] == "gpt-explicit"


def test_adapter_does_not_validate_or_execute():
    # The adapter never reaches downstream gates: it preserves the raw provider
    # output (diagnostic only; never serialized) and attempts no execution.
    client = _build_fake_client(json.dumps(_valid_ruleset_payload()))
    teacher = OpenAITeacher(client=client)
    response = teacher.propose(_request())
    assert response.raw_provider_output  # preserved in-memory
    assert len(response.ruleset) == 1


# ----------------------------------------------------------------------
# Failure modes
# ----------------------------------------------------------------------

def test_adapter_fails_when_output_text_empty():
    client = _build_fake_client("   ")
    teacher = OpenAITeacher(client=client)
    with pytest.raises(ProviderResponseError, match="did not include any output text"):
        teacher.propose(_request())


def test_adapter_fails_when_output_text_missing():
    response = SimpleNamespace()  # no output_text attribute at all
    client = MagicMock()
    client.responses.create.return_value = response
    teacher = OpenAITeacher(client=client)
    with pytest.raises(ProviderResponseError, match="output text"):
        teacher.propose(_request())


def test_adapter_fails_when_text_has_no_json():
    client = _build_fake_client("I cannot comply with that request.")
    teacher = OpenAITeacher(client=client)
    with pytest.raises(ProviderResponseError, match="contains no JSON object"):
        teacher.propose(_request())


def test_adapter_propagates_parser_errors_for_malformed_payload():
    bad = _valid_ruleset_payload()
    del bad["rules"][0]["rationale"]
    client = _build_fake_client(json.dumps(bad))
    teacher = OpenAITeacher(client=client)
    with pytest.raises(ProviderResponseError, match="rationale"):
        teacher.propose(_request())


def test_adapter_accepts_custom_domain_condition_type():
    # BUG-1 / #21: the parser is domain-agnostic about vocabulary, so a custom
    # domain's condition type (host_class for ttek2_crawler_gate) must be accepted
    # by the adapter. The Validator — not the parser — decides domain legality.
    payload = _valid_ruleset_payload()
    payload["rules"][0]["conditions"] = [{"type": "host_class", "class": "search_engine"}]
    client = _build_fake_client(json.dumps(payload))
    teacher = OpenAITeacher(client=client)
    response = teacher.propose(_request())
    rule = next(iter(response.ruleset))
    assert [c.type for c in rule.conditions] == ["host_class"]


def test_adapter_propagates_parser_error_for_empty_satisfies_constraints():
    bad = _valid_ruleset_payload()
    bad["rules"][0]["satisfies_constraints"] = []
    client = _build_fake_client(json.dumps(bad))
    teacher = OpenAITeacher(client=client)
    with pytest.raises(ProviderResponseError, match="satisfies_constraints"):
        teacher.propose(_request())


def test_adapter_constructor_fails_clearly_when_sdk_missing(monkeypatch):
    # Force `import openai` to fail even if the SDK is installed in the test env.
    monkeypatch.setitem(sys.modules, "openai", None)
    with pytest.raises(ImportError, match=r"dtaifm\[openai\]"):
        OpenAITeacher._build_real_client()


def test_adapter_constructor_fails_clearly_when_api_key_missing(monkeypatch):
    # Pretend the SDK is installed so the API-key check is reached.
    fake_sdk = SimpleNamespace(OpenAI=lambda api_key: MagicMock())
    monkeypatch.setitem(sys.modules, "openai", fake_sdk)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        OpenAITeacher._build_real_client()


# ----------------------------------------------------------------------
# Registry integration
# ----------------------------------------------------------------------

def test_openai_registered_in_default_registry():
    from dtaifm.teacher.registry import available_teachers
    assert "openai" in available_teachers()


def test_get_teacher_passes_model_and_ignores_irrelevant_options(monkeypatch):
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    # Stub the real-client build so the registry path needs no SDK or API key.
    monkeypatch.setattr(OpenAITeacher, "_build_real_client", staticmethod(lambda: MagicMock()))
    from dtaifm.teacher.registry import get_teacher
    # base_url/timeout are irrelevant to a cloud SDK adapter and must be ignored.
    teacher = get_teacher("openai", model="gpt-explicit", base_url="http://nowhere", timeout=300.0)
    assert isinstance(teacher, OpenAITeacher)
    assert teacher.model == "gpt-explicit"
