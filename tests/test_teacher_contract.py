"""Tests for the provider-neutral teacher contract types and prompt template."""


from dtaifm.core.constraint import Constraint, ConstraintType
from dtaifm.core.ruleset import RuleSet
from dtaifm.schema import SCHEMA_VERSION
from dtaifm.teacher import MockTeacher
from dtaifm.teacher.contract import PromptContext, TeacherRequest, TeacherResponse
from dtaifm.teacher.prompt import render_teacher_prompt


def _sample_constraints() -> list[Constraint]:
    return [
        Constraint(
            id="no_auto_unlock",
            description="Never unlock doors automatically.",
            type=ConstraintType.ABSOLUTE_PROHIBITION,
            parameters={"applies_to": ["front_door"], "action": "unlock"},
        ),
        Constraint(
            id="security_override",
            description="Security mode overrides comfort automation.",
            type=ConstraintType.MODE_OVERRIDE,
            parameters={"overriding_mode": "security", "comfort_devices": ["heating"]},
        ),
    ]


# ----------------------------------------------------------------------
# Contract dataclasses
# ----------------------------------------------------------------------

def test_prompt_context_defaults():
    ctx = PromptContext()
    assert ctx.domain == ""
    assert ctx.metadata == {}


def test_teacher_request_carries_schema_version():
    request = TeacherRequest(constraints=_sample_constraints())
    assert request.schema_version == SCHEMA_VERSION
    assert isinstance(request.context, PromptContext)


def test_teacher_response_carries_ruleset_and_raw_output():
    rs = RuleSet(source="test")
    resp = TeacherResponse(ruleset=rs, raw_provider_output="raw blob")
    assert resp.ruleset is rs
    assert resp.raw_provider_output == "raw blob"


# ----------------------------------------------------------------------
# MockTeacher implements the new contract
# ----------------------------------------------------------------------

def test_mock_teacher_propose_returns_teacher_response():
    teacher = MockTeacher()
    request = TeacherRequest(constraints=_sample_constraints(), context=PromptContext(domain="smart_home"))
    response = teacher.propose(request)
    assert isinstance(response, TeacherResponse)
    assert len(response.ruleset) == 3
    # The mock teacher does not validate or execute anything; rules with empty
    # satisfies_constraints are still in the artifact, awaiting the validator.
    ids = {r.id for r in response.ruleset}
    assert "r_auto_unlock_door" in ids


def test_mock_teacher_render_prompt_returns_text():
    teacher = MockTeacher()
    request = TeacherRequest(constraints=_sample_constraints(), context=PromptContext(domain="smart_home"))
    prompt = teacher.render_prompt(request)
    assert isinstance(prompt, str)
    assert "smart_home" in prompt


# ----------------------------------------------------------------------
# Shared prompt rendering
# ----------------------------------------------------------------------

def test_prompt_includes_all_constraint_ids():
    request = TeacherRequest(constraints=_sample_constraints(), context=PromptContext(domain="smart_home"))
    prompt = render_teacher_prompt(request)
    assert "no_auto_unlock" in prompt
    assert "security_override" in prompt


def test_prompt_includes_domain_and_schema_version():
    request = TeacherRequest(
        constraints=_sample_constraints(),
        context=PromptContext(domain="telecom"),
    )
    prompt = render_teacher_prompt(request)
    assert "telecom" in prompt
    assert SCHEMA_VERSION in prompt


def test_prompt_mentions_required_fields():
    request = TeacherRequest(constraints=_sample_constraints())
    prompt = render_teacher_prompt(request)
    for required in ("satisfies_constraints", "rationale", "trigger", "actions"):
        assert required in prompt


def test_prompt_specifies_top_level_json_envelope():
    request = TeacherRequest(constraints=_sample_constraints())
    prompt = render_teacher_prompt(request)
    # Must explicitly describe the top-level envelope shape so non-tool-use
    # local providers don't wrap output in arbitrary keys.
    assert "schema_version" in prompt
    assert "rules" in prompt
    # Must warn against wrapping in other keys; lower-case is fine.
    assert "do not wrap" in prompt.lower()


def test_prompt_is_provider_neutral_and_does_not_mention_submit_ruleset():
    # The shared prompt is sent verbatim by ollama/lemonade/anthropic adapters.
    # The Anthropic adapter still uses tool-use internally, but the literal
    # tool name must not leak into the prompt body — that caused local LLMs to
    # wrap their output in a `submit_ruleset` key.
    request = TeacherRequest(constraints=_sample_constraints())
    prompt = render_teacher_prompt(request)
    assert "submit_ruleset" not in prompt
    assert "submit_ruleset" not in prompt.lower()


def test_prompt_lists_known_condition_types():
    request = TeacherRequest(constraints=_sample_constraints())
    prompt = render_teacher_prompt(request)
    for cond_type in ("time_range", "mode_not", "device_state"):
        assert cond_type in prompt


def test_prompt_states_artifact_principle():
    request = TeacherRequest(constraints=_sample_constraints())
    prompt = render_teacher_prompt(request)
    # The prompt must communicate that output is an artifact, not an action.
    assert "ARTIFACT" in prompt or "artifact" in prompt
    assert "REJECT" in prompt or "reject" in prompt
