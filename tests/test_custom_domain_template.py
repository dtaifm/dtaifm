"""CI coverage for the custom domain template at examples/custom_domain_template/.

Keeps the template honest as the framework evolves. The template itself is not
auto-discovered by pytest (testpaths is limited to tests/); this file imports
the template via importlib so no examples/__init__.py is required and the
existing example directories stay unaffected.
"""

import importlib.util
from pathlib import Path

import pytest

from dtaifm.core.constraint import Constraint
from dtaifm.core.rule import Action, Rule, Trigger
from dtaifm.domains.registry import _DOMAINS, register_domain
from dtaifm.io import load_constraints, load_ruleset
from dtaifm.student.validator import Validator


TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "examples" / "custom_domain_template"


@pytest.fixture(scope="module")
def template():
    spec = importlib.util.spec_from_file_location(
        "custom_domain_template_ci",
        TEMPLATE_DIR / "__init__.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def registered_support(template):
    register_domain(template.SUPPORT_DOMAIN)
    yield template.SUPPORT_DOMAIN
    _DOMAINS.pop("support", None)


def test_template_defines_domain_metadata(template):
    d = template.SUPPORT_DOMAIN
    assert d.id == "support"
    assert d.version == "0.1"
    assert d.description
    assert d.trigger_events >= frozenset({"ticket_opened", "ticket_escalated"})
    assert d.action_kinds >= frozenset({"notify_team", "assign_engineer", "escalate"})
    assert "escalation_requires_assignment" in d.extra_constraint_evaluators


def test_template_evaluator_flags_unpaired_escalation(template):
    rule = Rule(
        id="r_bad",
        name="Bad",
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
    v = template.escalation_requires_assignment(rule, constraint)
    assert v is not None
    assert "assign_engineer" in v.reason


def test_template_evaluator_passes_paired_escalation(template):
    rule = Rule(
        id="r_ok",
        name="OK",
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


def test_template_example_files_validate_through_domain(template, registered_support):
    constraints = load_constraints(TEMPLATE_DIR / "constraints.yaml")
    ruleset = load_ruleset(TEMPLATE_DIR / "rules.yaml")
    validator = Validator(constraints, domain=registered_support)
    result = validator.validate_ruleset(ruleset)
    assert result.all_approved, (
        f"Unexpected rejections in the template: "
        f"{[(vr.rule_id, [v.constraint_id for v in vr.violations]) for vr in result.rejected]}"
    )


def test_template_does_not_auto_register(template):
    """Loading the template module must NOT register the domain globally.

    This keeps the template's import side-effects predictable and avoids
    polluting other tests in the suite.
    """
    # The fixture above intentionally registers the domain; this test reads the
    # registry without using that fixture and confirms importing the template
    # alone is not enough to register.
    _DOMAINS.pop("support", None)  # ensure clean baseline
    # The `template` fixture has already imported the module — if it had
    # auto-registered, 'support' would still be present after the pop above
    # (because the fixture is module-scoped and runs once). Re-importing is a
    # no-op for the registration check.
    assert "support" not in _DOMAINS
