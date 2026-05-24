"""Test stub for the support domain template.

This file is NOT auto-discovered by the main test suite (pytest's
``testpaths`` is limited to ``tests/``). Run it explicitly:

    pytest examples/custom_domain_template/test_my_domain.py

Or copy this directory into your own project and adapt the tests there.
"""

import importlib.util
from pathlib import Path

import pytest

from dtaifm.core.constraint import Constraint
from dtaifm.core.rule import Action, Rule, Trigger
from dtaifm.domains.registry import _DOMAINS, register_domain
from dtaifm.io import load_constraints, load_ruleset
from dtaifm.student.validator import Validator


HERE = Path(__file__).resolve().parent


def _load_template():
    spec = importlib.util.spec_from_file_location(
        "custom_domain_template_under_test",
        HERE / "__init__.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def template():
    return _load_template()


@pytest.fixture
def registered_domain(template):
    register_domain(template.SUPPORT_DOMAIN)
    yield template.SUPPORT_DOMAIN
    _DOMAINS.pop("support", None)


def test_domain_vocabulary(template):
    d = template.SUPPORT_DOMAIN
    assert d.id == "support"
    assert d.version == "0.1"
    assert "ticket_opened" in d.trigger_events
    assert "notify_team" in d.action_kinds
    assert "escalation_requires_assignment" in d.extra_constraint_evaluators


def test_custom_evaluator_flags_escalation_without_assignment(template):
    rule = Rule(
        id="r_bad",
        name="Escalate without assign",
        trigger=Trigger(device="ticket_system", event="ticket_escalated"),
        actions=[Action(device="ticket_x", action="escalate")],
        satisfies_constraints=["x"],
        rationale="x",
    )
    constraint = Constraint(
        id="esc",
        description="Escalation requires assignment.",
        type="escalation_requires_assignment",
    )
    violation = template.escalation_requires_assignment(rule, constraint)
    assert violation is not None
    assert "assign_engineer" in violation.reason


def test_custom_evaluator_passes_paired_escalation(template):
    rule = Rule(
        id="r_ok",
        name="Escalate with assign",
        trigger=Trigger(device="ticket_system", event="ticket_escalated"),
        actions=[
            Action(device="ticket_x", action="assign_engineer"),
            Action(device="ticket_x", action="escalate"),
        ],
        satisfies_constraints=["x"],
        rationale="x",
    )
    constraint = Constraint(
        id="esc",
        description="Escalation requires assignment.",
        type="escalation_requires_assignment",
    )
    assert template.escalation_requires_assignment(rule, constraint) is None


def test_example_files_validate(template, registered_domain):
    constraints = load_constraints(HERE / "constraints.yaml")
    ruleset = load_ruleset(HERE / "rules.yaml")
    validator = Validator(constraints, domain=registered_domain)
    result = validator.validate_ruleset(ruleset)
    assert result.all_approved, (
        f"Unexpected rejections: "
        f"{[(vr.rule_id, [v.constraint_id for v in vr.violations]) for vr in result.rejected]}"
    )
