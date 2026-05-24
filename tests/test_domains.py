"""Tests for the Domain registry and domain-aware validation/runtime/prompt."""

from datetime import datetime

import pytest

from dtaifm.cli import main
from dtaifm.core.constraint import Constraint, ConstraintType
from dtaifm.core.rule import Action, Condition, Rule, Trigger
from dtaifm.domains.base import Domain
from dtaifm.domains.registry import (
    UnknownDomainError,
    domain_is_registered,
    get_domain,
    list_domains,
    register_domain,
)
from dtaifm.runtimes.python_runtime import PythonRuntime
from dtaifm.student.validator import Validator
from dtaifm.teacher.contract import PromptContext, TeacherRequest
from dtaifm.teacher.prompt import render_teacher_prompt


# ----------------------------------------------------------------------
# Registry
# ----------------------------------------------------------------------

def test_built_in_domains_are_registered():
    domains = list_domains()
    assert "smart_home" in domains
    assert "network_automation" in domains


def test_get_domain_returns_domain_object():
    smart = get_domain("smart_home")
    assert isinstance(smart, Domain)
    assert smart.id == "smart_home"
    assert smart.version == "0.1"
    assert "motion_detected" in smart.trigger_events
    assert "turn_on" in smart.action_kinds


def test_get_unknown_domain_raises_clear_error():
    with pytest.raises(UnknownDomainError, match="Unknown domain 'nope'"):
        get_domain("nope")


def test_register_domain_then_lookup():
    test_domain = Domain(
        id="__test_domain__",
        version="0.0",
        trigger_events=frozenset({"e1"}),
        condition_types=frozenset({"time_range"}),
        action_kinds=frozenset({"do_thing"}),
    )
    register_domain(test_domain)
    try:
        assert domain_is_registered("__test_domain__")
        assert get_domain("__test_domain__") is test_domain
    finally:
        # Remove the test domain so it doesn't pollute other tests.
        from dtaifm.domains.registry import _DOMAINS
        _DOMAINS.pop("__test_domain__", None)


def test_cli_unknown_domain_fails_clearly(capsys, tmp_path):
    from pathlib import Path
    examples = Path(__file__).resolve().parent.parent / "examples" / "smart_rules"
    exit_code = main([
        "validate",
        str(examples / "constraints.yaml"),
        str(examples / "rules.yaml"),
        "--domain", "nope",
    ])
    assert exit_code == 2
    assert "Unknown domain 'nope'" in capsys.readouterr().err


# ----------------------------------------------------------------------
# Domain-aware validator
# ----------------------------------------------------------------------

def _smart_home_constraint() -> Constraint:
    return Constraint(
        id="no_auto_unlock",
        description="Never unlock doors automatically.",
        type=ConstraintType.ABSOLUTE_PROHIBITION,
        parameters={"applies_to": ["front_door"], "action": "unlock"},
    )


def test_validator_without_domain_keeps_legacy_behavior():
    # Validator(constraints) without a domain must continue working — no domain check applied.
    rule = Rule(
        id="r_alien",
        name="Uses an action no domain knows",
        trigger=Trigger(device="alien_sensor", event="alien_event"),
        conditions=[],
        actions=[Action(device="alien_device", action="alien_action")],
        satisfies_constraints=["x"],
        explanation="legacy",
        rationale="legacy",
    )
    validator = Validator([_smart_home_constraint()])
    result = validator.validate_rule(rule)
    assert result.is_valid


def test_validator_with_domain_rejects_out_of_vocabulary_action():
    domain = get_domain("smart_home")
    rule = Rule(
        id="r_apply_config_in_home",
        name="Wrong-domain action",
        trigger=Trigger(device="motion_sensor", event="motion_detected"),
        conditions=[],
        actions=[Action(device="router1", action="apply_config")],  # apply_config not in smart_home
        satisfies_constraints=["x"],
        explanation="x",
        rationale="x",
    )
    validator = Validator([], domain=domain)
    result = validator.validate_rule(rule)
    assert not result.is_valid
    assert any(v.constraint_id == "__domain__" for v in result.violations)
    assert any("apply_config" in v.reason for v in result.violations)


def test_validator_with_domain_rejects_out_of_vocabulary_trigger():
    domain = get_domain("smart_home")
    rule = Rule(
        id="r_bad_trigger",
        name="Wrong-domain trigger",
        trigger=Trigger(device="x", event="bgp_session_flap"),  # not in smart_home
        conditions=[],
        actions=[Action(device="light", action="turn_on")],
        satisfies_constraints=["x"],
        explanation="x",
        rationale="x",
    )
    validator = Validator([], domain=domain)
    result = validator.validate_rule(rule)
    assert not result.is_valid
    assert any("trigger event 'bgp_session_flap'" in v.reason for v in result.violations)


def test_validator_with_domain_accepts_in_vocabulary_rule():
    domain = get_domain("smart_home")
    rule = Rule(
        id="r_ok",
        name="Allowed everything",
        trigger=Trigger(device="motion_sensor", event="motion_detected"),
        conditions=[Condition(type="mode_not", parameters={"mode": "security"})],
        actions=[Action(device="hallway_light", action="turn_on")],
        satisfies_constraints=["x"],
        explanation="x",
        rationale="x",
    )
    validator = Validator([], domain=domain)
    assert validator.validate_rule(rule).is_valid


# ----------------------------------------------------------------------
# Runtime defense-in-depth
# ----------------------------------------------------------------------

def test_runtime_refuses_action_outside_active_domain():
    domain = get_domain("smart_home")
    # Construct a rule that somehow bypassed validation (we feed it directly to runtime).
    rule = Rule(
        id="r_smuggled",
        name="Smuggled router action",
        trigger=Trigger(device="motion_sensor", event="motion_detected"),
        conditions=[],
        actions=[Action(device="router1", action="apply_config")],
        satisfies_constraints=["x"],
        explanation="x",
        rationale="x",
    )
    runtime = PythonRuntime([rule], domain=domain)
    result = runtime.fire("motion_sensor", "motion_detected", {"time": datetime(2024, 1, 1, 12, 0)})
    assert "r_smuggled" not in result.triggered_rule_ids
    trace = next(t for t in result.trace if t.rule_id == "r_smuggled")
    assert not trace.fired
    assert "outside domain" in trace.reason


def test_runtime_without_domain_executes_any_action():
    # Without a domain, defense-in-depth is off and the runtime runs whatever it's given.
    rule = Rule(
        id="r_freeform",
        name="No-domain rule",
        trigger=Trigger(device="d", event="e"),
        conditions=[],
        actions=[Action(device="x", action="anything_at_all")],
        satisfies_constraints=["x"],
        explanation="x",
        rationale="x",
    )
    runtime = PythonRuntime([rule])  # no domain
    result = runtime.fire("d", "e", {})
    assert "r_freeform" in result.triggered_rule_ids


# ----------------------------------------------------------------------
# Prompt vocabulary
# ----------------------------------------------------------------------

def test_prompt_includes_domain_vocabulary_smart_home():
    domain = get_domain("smart_home")
    request = TeacherRequest(constraints=[], context=PromptContext(domain="smart_home"), domain=domain)
    prompt = render_teacher_prompt(request)
    assert "DOMAIN VOCABULARY" in prompt
    assert "motion_detected" in prompt
    assert "turn_on" in prompt
    assert "time_range" in prompt
    # The domain id and version appear in the prompt header.
    assert "smart_home" in prompt
    assert "v0.1" in prompt


def test_prompt_includes_domain_vocabulary_network_automation():
    domain = get_domain("network_automation")
    request = TeacherRequest(constraints=[], context=PromptContext(domain="network_automation"), domain=domain)
    prompt = render_teacher_prompt(request)
    assert "apply_config" in prompt
    assert "rollback" in prompt
    assert "config_change_requested" in prompt
    # Smart-home-only verbs must NOT leak into a network_automation prompt.
    assert "motion_detected" not in prompt
    assert "unlock" not in prompt


def test_prompt_without_domain_uses_placeholder():
    request = TeacherRequest(constraints=[], context=PromptContext(domain="someplace"))
    prompt = render_teacher_prompt(request)
    assert "no domain attached" in prompt
