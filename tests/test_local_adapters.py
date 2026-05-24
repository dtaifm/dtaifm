"""Tests for the Ollama and Lemonade local teacher adapters.

All tests inject a FakeHttpClient — no real network calls are made.
"""

import json
from typing import Any

import pytest

from dtaifm.core.constraint import Constraint, ConstraintType
from dtaifm.schema import SCHEMA_VERSION
from dtaifm.teacher.adapters.lemonade_adapter import LemonadeTeacher
from dtaifm.teacher.adapters.ollama_adapter import OllamaTeacher
from dtaifm.teacher.contract import PromptContext, TeacherRequest
from dtaifm.teacher.parser import ProviderResponseError


# ----------------------------------------------------------------------
# Test helpers
# ----------------------------------------------------------------------

class FakeHttpClient:
    """Records calls; pops queued responses; raises a queued exception if set."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, Any]] = []
        self._responses: list[Any] = []
        self._exception: Exception | None = None

    def queue(self, response: Any) -> None:
        self._responses.append(response)

    def raise_on_next(self, exc: Exception) -> None:
        self._exception = exc

    def post_json(self, url: str, payload: dict, *, headers: dict | None = None) -> Any:
        self.calls.append(("POST", url, payload))
        if self._exception is not None:
            exc, self._exception = self._exception, None
            raise exc
        if not self._responses:
            raise RuntimeError("FakeHttpClient: no queued response")
        return self._responses.pop(0)

    def get(self, url: str, *, headers: dict | None = None) -> Any:
        self.calls.append(("GET", url, None))
        if self._exception is not None:
            exc, self._exception = self._exception, None
            raise exc
        if not self._responses:
            raise RuntimeError("FakeHttpClient: no queued response")
        return self._responses.pop(0)


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
                "actions": [{"device": "hallway_light", "action": "turn_on"}],
                "satisfies_constraints": ["motion_light_hours"],
                "rationale": "Demonstrates a valid local-teacher proposal.",
                "explanation": "Turns on the hallway light.",
            }
        ],
    }


def _ollama_response(content: str) -> dict:
    return {"message": {"role": "assistant", "content": content}}


def _openai_response(content: str) -> dict:
    return {
        "choices": [
            {"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
        ]
    }


def _request() -> TeacherRequest:
    return TeacherRequest(
        constraints=_sample_constraints(),
        context=PromptContext(domain="smart_home"),
    )


# ----------------------------------------------------------------------
# Ollama: base URL resolution
# ----------------------------------------------------------------------

class TestOllamaBaseUrl:
    def test_default_localhost(self, monkeypatch):
        monkeypatch.delenv("DTAIFM_OLLAMA_BASE_URL", raising=False)
        client = FakeHttpClient()
        client.queue(_ollama_response(json.dumps(_valid_ruleset_payload())))
        teacher = OllamaTeacher(client=client)
        teacher.propose(_request())
        assert client.calls[0][1] == "http://localhost:11434/api/chat"

    def test_env_var_override(self, monkeypatch):
        monkeypatch.setenv("DTAIFM_OLLAMA_BASE_URL", "http://from-env:11434")
        client = FakeHttpClient()
        client.queue(_ollama_response(json.dumps(_valid_ruleset_payload())))
        teacher = OllamaTeacher(client=client)
        teacher.propose(_request())
        assert client.calls[0][1] == "http://from-env:11434/api/chat"

    def test_explicit_base_url_beats_env_var(self, monkeypatch):
        monkeypatch.setenv("DTAIFM_OLLAMA_BASE_URL", "http://env:11434")
        client = FakeHttpClient()
        client.queue(_ollama_response(json.dumps(_valid_ruleset_payload())))
        teacher = OllamaTeacher(base_url="http://explicit:11434", client=client)
        teacher.propose(_request())
        assert client.calls[0][1] == "http://explicit:11434/api/chat"

    def test_trailing_slash_stripped(self, monkeypatch):
        monkeypatch.delenv("DTAIFM_OLLAMA_BASE_URL", raising=False)
        client = FakeHttpClient()
        client.queue(_ollama_response(json.dumps(_valid_ruleset_payload())))
        teacher = OllamaTeacher(base_url="http://localhost:11434/", client=client)
        teacher.propose(_request())
        assert client.calls[0][1] == "http://localhost:11434/api/chat"

    def test_accepts_ip_style_url(self, monkeypatch):
        monkeypatch.delenv("DTAIFM_OLLAMA_BASE_URL", raising=False)
        client = FakeHttpClient()
        client.queue(_ollama_response(json.dumps(_valid_ruleset_payload())))
        teacher = OllamaTeacher(base_url="http://192.0.2.10:11434", client=client)
        teacher.propose(_request())
        assert client.calls[0][1] == "http://192.0.2.10:11434/api/chat"


# ----------------------------------------------------------------------
# Ollama: model resolution + payload shape
# ----------------------------------------------------------------------

class TestOllamaPayload:
    def test_default_model(self, monkeypatch):
        monkeypatch.delenv("DTAIFM_OLLAMA_MODEL", raising=False)
        client = FakeHttpClient()
        client.queue(_ollama_response(json.dumps(_valid_ruleset_payload())))
        teacher = OllamaTeacher(client=client)
        teacher.propose(_request())
        assert client.calls[0][2]["model"] == "llama3.2"

    def test_env_model_override(self, monkeypatch):
        monkeypatch.setenv("DTAIFM_OLLAMA_MODEL", "qwen3:0.6b")
        client = FakeHttpClient()
        client.queue(_ollama_response(json.dumps(_valid_ruleset_payload())))
        teacher = OllamaTeacher(client=client)
        teacher.propose(_request())
        assert client.calls[0][2]["model"] == "qwen3:0.6b"

    def test_explicit_model_beats_env(self, monkeypatch):
        monkeypatch.setenv("DTAIFM_OLLAMA_MODEL", "env-model")
        client = FakeHttpClient()
        client.queue(_ollama_response(json.dumps(_valid_ruleset_payload())))
        teacher = OllamaTeacher(model="explicit-model", client=client)
        teacher.propose(_request())
        assert client.calls[0][2]["model"] == "explicit-model"

    def test_payload_includes_format_json_hint(self):
        client = FakeHttpClient()
        client.queue(_ollama_response(json.dumps(_valid_ruleset_payload())))
        teacher = OllamaTeacher(client=client)
        teacher.propose(_request())
        payload = client.calls[0][2]
        assert payload["format"] == "json"
        assert payload["stream"] is False
        assert payload["messages"][0]["role"] == "user"
        # The prompt body must include constraints from the request
        assert "no_auto_unlock" in payload["messages"][0]["content"]


# ----------------------------------------------------------------------
# Ollama: response parsing
# ----------------------------------------------------------------------

class TestOllamaResponseParsing:
    def test_parses_valid_json_content(self):
        client = FakeHttpClient()
        client.queue(_ollama_response(json.dumps(_valid_ruleset_payload())))
        teacher = OllamaTeacher(client=client)
        response = teacher.propose(_request())
        assert len(response.ruleset) == 1
        assert next(iter(response.ruleset)).id == "r_safe"

    def test_parses_fenced_json_content(self):
        content = (
            "Sure, here are the rules:\n\n"
            f"```json\n{json.dumps(_valid_ruleset_payload())}\n```\n\nLet me know!"
        )
        client = FakeHttpClient()
        client.queue(_ollama_response(content))
        teacher = OllamaTeacher(client=client)
        response = teacher.propose(_request())
        assert len(response.ruleset) == 1

    def test_rejects_non_json_content(self):
        client = FakeHttpClient()
        client.queue(_ollama_response("I refuse to comply."))
        teacher = OllamaTeacher(client=client)
        with pytest.raises(ProviderResponseError, match="contains no JSON object"):
            teacher.propose(_request())

    def test_propagates_parser_errors_for_missing_rationale(self):
        bad = _valid_ruleset_payload()
        del bad["rules"][0]["rationale"]
        client = FakeHttpClient()
        client.queue(_ollama_response(json.dumps(bad)))
        teacher = OllamaTeacher(client=client)
        with pytest.raises(ProviderResponseError, match="rationale"):
            teacher.propose(_request())

    def test_missing_message_object_fails_clearly(self):
        client = FakeHttpClient()
        client.queue({"unexpected": "shape"})
        teacher = OllamaTeacher(client=client)
        with pytest.raises(ProviderResponseError, match="missing 'message'"):
            teacher.propose(_request())

    def test_empty_message_content_fails_clearly(self):
        client = FakeHttpClient()
        client.queue({"message": {"content": ""}})
        teacher = OllamaTeacher(client=client)
        with pytest.raises(ProviderResponseError, match="message.content"):
            teacher.propose(_request())


# ----------------------------------------------------------------------
# Ollama: connection failure surfaces clearly
# ----------------------------------------------------------------------

def test_ollama_connection_failure_surfaces_runtime_error():
    client = FakeHttpClient()
    client.raise_on_next(OSError("Connection refused"))
    teacher = OllamaTeacher(client=client)
    with pytest.raises(RuntimeError, match="failed to reach"):
        teacher.propose(_request())


# ======================================================================
# Lemonade
# ======================================================================

class TestLemonadeBaseUrl:
    def test_default_localhost(self, monkeypatch):
        monkeypatch.delenv("DTAIFM_LEMONADE_BASE_URL", raising=False)
        client = FakeHttpClient()
        client.queue(_openai_response(json.dumps(_valid_ruleset_payload())))
        teacher = LemonadeTeacher(client=client)
        teacher.propose(_request())
        assert client.calls[0][1] == "http://localhost:13305/v1/chat/completions"

    def test_env_var_override(self, monkeypatch):
        monkeypatch.setenv("DTAIFM_LEMONADE_BASE_URL", "http://192.0.2.10:13305")
        client = FakeHttpClient()
        client.queue(_openai_response(json.dumps(_valid_ruleset_payload())))
        teacher = LemonadeTeacher(client=client)
        teacher.propose(_request())
        assert client.calls[0][1] == "http://192.0.2.10:13305/v1/chat/completions"

    def test_explicit_base_url_beats_env_var(self, monkeypatch):
        monkeypatch.setenv("DTAIFM_LEMONADE_BASE_URL", "http://env-host:13305")
        client = FakeHttpClient()
        client.queue(_openai_response(json.dumps(_valid_ruleset_payload())))
        teacher = LemonadeTeacher(base_url="http://192.0.2.10:13305", client=client)
        teacher.propose(_request())
        assert client.calls[0][1] == "http://192.0.2.10:13305/v1/chat/completions"

    def test_trailing_slash_stripped(self, monkeypatch):
        monkeypatch.delenv("DTAIFM_LEMONADE_BASE_URL", raising=False)
        client = FakeHttpClient()
        client.queue(_openai_response(json.dumps(_valid_ruleset_payload())))
        teacher = LemonadeTeacher(base_url="http://192.0.2.10:13305///", client=client)
        teacher.propose(_request())
        assert client.calls[0][1] == "http://192.0.2.10:13305/v1/chat/completions"


class TestLemonadePayload:
    def test_default_model_is_qwen(self, monkeypatch):
        monkeypatch.delenv("DTAIFM_LEMONADE_MODEL", raising=False)
        client = FakeHttpClient()
        client.queue(_openai_response(json.dumps(_valid_ruleset_payload())))
        teacher = LemonadeTeacher(client=client)
        teacher.propose(_request())
        assert client.calls[0][2]["model"] == "Qwen3-0.6B-GGUF"

    def test_payload_uses_openai_response_format_json(self):
        client = FakeHttpClient()
        client.queue(_openai_response(json.dumps(_valid_ruleset_payload())))
        teacher = LemonadeTeacher(model="custom-model", client=client)
        teacher.propose(_request())
        payload = client.calls[0][2]
        assert payload["model"] == "custom-model"
        assert payload["stream"] is False
        assert payload["response_format"] == {"type": "json_object"}
        assert "no_auto_unlock" in payload["messages"][0]["content"]


class TestLemonadeResponseParsing:
    def test_parses_valid_openai_response(self):
        client = FakeHttpClient()
        client.queue(_openai_response(json.dumps(_valid_ruleset_payload())))
        teacher = LemonadeTeacher(client=client)
        response = teacher.propose(_request())
        assert len(response.ruleset) == 1

    def test_parses_fenced_json_inside_openai_response(self):
        content = f"```json\n{json.dumps(_valid_ruleset_payload())}\n```"
        client = FakeHttpClient()
        client.queue(_openai_response(content))
        teacher = LemonadeTeacher(client=client)
        assert len(teacher.propose(_request()).ruleset) == 1

    def test_rejects_response_with_empty_choices(self):
        client = FakeHttpClient()
        client.queue({"choices": []})
        teacher = LemonadeTeacher(client=client)
        with pytest.raises(ProviderResponseError, match="'choices'"):
            teacher.propose(_request())

    def test_rejects_response_with_no_message_content(self):
        client = FakeHttpClient()
        client.queue({"choices": [{"message": {"content": ""}}]})
        teacher = LemonadeTeacher(client=client)
        with pytest.raises(ProviderResponseError, match="content"):
            teacher.propose(_request())

    def test_propagates_parser_errors_for_missing_satisfies_constraints(self):
        bad = _valid_ruleset_payload()
        bad["rules"][0]["satisfies_constraints"] = []
        client = FakeHttpClient()
        client.queue(_openai_response(json.dumps(bad)))
        teacher = LemonadeTeacher(client=client)
        with pytest.raises(ProviderResponseError, match="satisfies_constraints"):
            teacher.propose(_request())


def test_lemonade_connection_failure_surfaces_runtime_error():
    client = FakeHttpClient()
    client.raise_on_next(OSError("Connection refused"))
    teacher = LemonadeTeacher(client=client)
    with pytest.raises(RuntimeError, match="failed to reach"):
        teacher.propose(_request())


# ======================================================================
# Configurable HTTP timeout (v0.1.1)
# ======================================================================

class TestOllamaTimeout:
    def test_default_timeout_when_neither_arg_nor_env(self, monkeypatch):
        monkeypatch.delenv("DTAIFM_HTTP_TIMEOUT", raising=False)
        teacher = OllamaTeacher(client=FakeHttpClient())
        assert teacher.timeout == 60.0

    def test_env_timeout_used_when_no_explicit_value(self, monkeypatch):
        monkeypatch.setenv("DTAIFM_HTTP_TIMEOUT", "300")
        teacher = OllamaTeacher(client=FakeHttpClient())
        assert teacher.timeout == 300.0

    def test_explicit_timeout_beats_env(self, monkeypatch):
        monkeypatch.setenv("DTAIFM_HTTP_TIMEOUT", "300")
        teacher = OllamaTeacher(client=FakeHttpClient(), timeout=600.0)
        assert teacher.timeout == 600.0

    def test_negative_explicit_timeout_rejected(self):
        with pytest.raises(ValueError, match="positive"):
            OllamaTeacher(client=FakeHttpClient(), timeout=-1.0)

    def test_zero_explicit_timeout_rejected(self):
        with pytest.raises(ValueError, match="positive"):
            OllamaTeacher(client=FakeHttpClient(), timeout=0.0)

    def test_non_numeric_env_value_fails_clearly(self, monkeypatch):
        monkeypatch.setenv("DTAIFM_HTTP_TIMEOUT", "not-a-number")
        with pytest.raises(ValueError, match="DTAIFM_HTTP_TIMEOUT"):
            OllamaTeacher(client=FakeHttpClient())

    def test_negative_env_value_rejected(self, monkeypatch):
        monkeypatch.setenv("DTAIFM_HTTP_TIMEOUT", "-10")
        with pytest.raises(ValueError, match="positive"):
            OllamaTeacher(client=FakeHttpClient())

    def test_real_http_client_receives_configured_timeout(self, monkeypatch):
        # When the adapter constructs its own HttpJsonClient (no client= injected),
        # that client must use the resolved timeout.
        monkeypatch.delenv("DTAIFM_HTTP_TIMEOUT", raising=False)
        teacher = OllamaTeacher(timeout=180.0)
        # The internal client is our HttpJsonClient with the timeout attribute.
        assert teacher._client.timeout == 180.0


class TestLemonadeTimeout:
    def test_default_timeout_when_neither_arg_nor_env(self, monkeypatch):
        monkeypatch.delenv("DTAIFM_HTTP_TIMEOUT", raising=False)
        teacher = LemonadeTeacher(client=FakeHttpClient())
        assert teacher.timeout == 60.0

    def test_env_timeout_used_when_no_explicit_value(self, monkeypatch):
        monkeypatch.setenv("DTAIFM_HTTP_TIMEOUT", "600")
        teacher = LemonadeTeacher(client=FakeHttpClient())
        assert teacher.timeout == 600.0

    def test_explicit_timeout_beats_env(self, monkeypatch):
        monkeypatch.setenv("DTAIFM_HTTP_TIMEOUT", "300")
        teacher = LemonadeTeacher(client=FakeHttpClient(), timeout=900.0)
        assert teacher.timeout == 900.0

    def test_invalid_env_fails_clearly(self, monkeypatch):
        monkeypatch.setenv("DTAIFM_HTTP_TIMEOUT", "garbage")
        with pytest.raises(ValueError, match="DTAIFM_HTTP_TIMEOUT"):
            LemonadeTeacher(client=FakeHttpClient())

    def test_real_http_client_receives_configured_timeout(self, monkeypatch):
        monkeypatch.delenv("DTAIFM_HTTP_TIMEOUT", raising=False)
        teacher = LemonadeTeacher(timeout=240.0)
        assert teacher._client.timeout == 240.0


# ======================================================================
# Registry integration
# ======================================================================

class TestRegistryThreadsOptions:
    def test_ollama_registered_in_default_registry(self):
        from dtaifm.teacher.registry import available_teachers
        assert "ollama" in available_teachers()
        assert "lemonade" in available_teachers()

    def test_get_teacher_passes_base_url_and_model_to_lemonade(self, monkeypatch):
        monkeypatch.delenv("DTAIFM_LEMONADE_BASE_URL", raising=False)
        monkeypatch.delenv("DTAIFM_LEMONADE_MODEL", raising=False)
        from dtaifm.teacher.registry import get_teacher
        teacher = get_teacher(
            "lemonade",
            base_url="http://192.0.2.10:13305",
            model="Qwen3-0.6B-GGUF",
        )
        assert teacher.base_url == "http://192.0.2.10:13305"
        assert teacher.model == "Qwen3-0.6B-GGUF"

    def test_get_teacher_ignores_irrelevant_options_for_mock(self):
        from dtaifm.teacher.registry import get_teacher
        # Mock teacher should accept (and silently ignore) the extra kwargs.
        teacher = get_teacher(
            "mock",
            base_url="http://nowhere",
            model="anything",
            timeout=300.0,
        )
        from dtaifm.teacher.mock_teacher import MockTeacher
        assert isinstance(teacher, MockTeacher)

    def test_get_teacher_threads_timeout_to_lemonade(self, monkeypatch):
        monkeypatch.delenv("DTAIFM_HTTP_TIMEOUT", raising=False)
        from dtaifm.teacher.registry import get_teacher
        teacher = get_teacher("lemonade", timeout=420.0)
        assert teacher.timeout == 420.0

    def test_get_teacher_threads_timeout_to_ollama(self, monkeypatch):
        monkeypatch.delenv("DTAIFM_HTTP_TIMEOUT", raising=False)
        from dtaifm.teacher.registry import get_teacher
        teacher = get_teacher("ollama", timeout=420.0)
        assert teacher.timeout == 420.0
