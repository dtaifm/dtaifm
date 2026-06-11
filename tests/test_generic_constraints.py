"""Tests for the generic policy constraint types (dtaifm/student/generic_evaluators.py)."""

import pytest

from dtaifm.core.constraint import Constraint
from dtaifm.core.result import ConstraintViolation
from dtaifm.core.rule import Action, Condition, Rule, Trigger
from dtaifm.domains.base import Domain
from dtaifm.student.generic_evaluators import (
    GENERIC_EVALUATORS,
    action_allowlist,
    action_denylist,
    mutually_exclusive_actions,
    parameter_threshold,
    requires,
)
from dtaifm.student.validator import Validator


def _make_constraint(id_, type_, **params):
    return Constraint(id=id_, description=f"test {id_}", type=type_, parameters=params)


def _make_rule(actions, conditions=()):
    return Rule(
        id="r_test", name="Test rule",
        trigger=Trigger(device="sensor", event="event_a"),
        actions=actions, conditions=list(conditions),
        satisfies_constraints=["x"], rationale="x",
    )


# ----------------------------------------------------------------------
# action_allowlist
# ----------------------------------------------------------------------

def test_allowlist_passes_when_all_actions_allowed():
    c = _make_constraint("only_safe", "action_allowlist", allowed_actions=["notify", "escalate"])
    rule = _make_rule([Action(device="d1", action="notify")])
    assert action_allowlist(rule, c) is None


def test_allowlist_rejects_action_outside_list():
    c = _make_constraint("only_safe", "action_allowlist", allowed_actions=["notify"])
    rule = _make_rule([Action(device="d1", action="refund")])
    v = action_allowlist(rule, c)
    assert v is not None
    assert "'refund'" in v.reason and "allowlist" in v.reason


def test_allowlist_applies_to_restricts_check_to_listed_devices():
    c = _make_constraint(
        "only_safe", "action_allowlist", allowed_actions=["notify"], applies_to=["d1"],
    )
    rule = _make_rule([Action(device="d2", action="refund")])
    assert action_allowlist(rule, c) is None


def test_allowlist_empty_list_is_noop():
    c = _make_constraint("only_safe", "action_allowlist", allowed_actions=[])
    rule = _make_rule([Action(device="d1", action="refund")])
    assert action_allowlist(rule, c) is None


# ----------------------------------------------------------------------
# action_denylist
# ----------------------------------------------------------------------

def test_denylist_rejects_denied_action():
    c = _make_constraint("no_destroy", "action_denylist", denied_actions=["delete", "purge"])
    rule = _make_rule([Action(device="d1", action="purge")])
    v = action_denylist(rule, c)
    assert v is not None
    assert "denied action 'purge'" in v.reason


def test_denylist_passes_clean_rule():
    c = _make_constraint("no_destroy", "action_denylist", denied_actions=["delete"])
    rule = _make_rule([Action(device="d1", action="notify")])
    assert action_denylist(rule, c) is None


def test_denylist_applies_to_restricts_check_to_listed_devices():
    c = _make_constraint(
        "no_destroy", "action_denylist", denied_actions=["delete"], applies_to=["prod_db"],
    )
    rule = _make_rule([Action(device="staging_db", action="delete")])
    assert action_denylist(rule, c) is None


# ----------------------------------------------------------------------
# requires
# ----------------------------------------------------------------------

def test_requires_flags_missing_companion_action():
    c = _make_constraint("needs_backup", "requires", if_action="apply", requires_action="backup")
    rule = _make_rule([Action(device="d1", action="apply")])
    v = requires(rule, c)
    assert v is not None
    assert "companion action 'backup'" in v.reason


def test_requires_passes_with_companion_action():
    c = _make_constraint("needs_backup", "requires", if_action="apply", requires_action="backup")
    rule = _make_rule([
        Action(device="d1", action="apply"),
        Action(device="d1", action="backup"),
    ])
    assert requires(rule, c) is None


def test_requires_flags_missing_condition():
    c = _make_constraint("needs_evidence", "requires", if_action="refund", requires_condition="evidence")
    rule = _make_rule([Action(device="d1", action="refund")])
    v = requires(rule, c)
    assert v is not None
    assert "condition 'evidence'" in v.reason


def test_requires_passes_with_matching_condition_parameters():
    c = _make_constraint(
        "needs_evidence", "requires",
        if_action="refund", requires_condition="evidence",
        condition_parameters={"signal": "order_verified"},
    )
    rule = _make_rule(
        [Action(device="d1", action="refund")],
        [Condition(type="evidence", parameters={"signal": "order_verified"})],
    )
    assert requires(rule, c) is None


def test_requires_flags_condition_with_wrong_parameters():
    c = _make_constraint(
        "needs_evidence", "requires",
        if_action="refund", requires_condition="evidence",
        condition_parameters={"signal": "order_verified"},
    )
    rule = _make_rule(
        [Action(device="d1", action="refund")],
        [Condition(type="evidence", parameters={"signal": "something_else"})],
    )
    assert requires(rule, c) is not None


def test_requires_ignores_rules_without_trigger_action():
    c = _make_constraint("needs_backup", "requires", if_action="apply", requires_action="backup")
    rule = _make_rule([Action(device="d1", action="notify")])
    assert requires(rule, c) is None


def test_requires_incomplete_parameters_is_noop():
    c = _make_constraint("incomplete", "requires", if_action="apply")
    rule = _make_rule([Action(device="d1", action="apply")])
    assert requires(rule, c) is None


# ----------------------------------------------------------------------
# mutually_exclusive_actions
# ----------------------------------------------------------------------

def test_mutually_exclusive_actions_rejects_combination():
    c = _make_constraint("no_both", "mutually_exclusive_actions", actions=["approve", "hold"])
    rule = _make_rule([
        Action(device="d1", action="approve"),
        Action(device="d1", action="hold"),
    ])
    v = mutually_exclusive_actions(rule, c)
    assert v is not None
    assert "mutually exclusive" in v.reason


def test_mutually_exclusive_actions_passes_single_action():
    c = _make_constraint("no_both", "mutually_exclusive_actions", actions=["approve", "hold"])
    rule = _make_rule([Action(device="d1", action="approve")])
    assert mutually_exclusive_actions(rule, c) is None


# ----------------------------------------------------------------------
# parameter_threshold
# ----------------------------------------------------------------------

def test_threshold_rejects_value_above_max():
    c = _make_constraint("amount_cap", "parameter_threshold", action="transfer", parameter="amount", max=1000)
    rule = _make_rule([Action(device="d1", action="transfer", parameters={"amount": 5000})])
    v = parameter_threshold(rule, c)
    assert v is not None
    assert "above the maximum 1000" in v.reason


def test_threshold_rejects_value_below_min():
    c = _make_constraint("min_sample", "parameter_threshold", condition="evidence", parameter="sample_size", min=30)
    rule = _make_rule(
        [Action(device="d1", action="tune")],
        [Condition(type="evidence", parameters={"sample_size": 3})],
    )
    v = parameter_threshold(rule, c)
    assert v is not None
    assert "below the minimum 30" in v.reason


def test_threshold_passes_value_in_range():
    c = _make_constraint("amount_cap", "parameter_threshold", action="transfer", parameter="amount", min=1, max=1000)
    rule = _make_rule([Action(device="d1", action="transfer", parameters={"amount": 500})])
    assert parameter_threshold(rule, c) is None


def test_threshold_fails_closed_on_missing_parameter():
    c = _make_constraint("amount_cap", "parameter_threshold", action="transfer", parameter="amount", max=1000)
    rule = _make_rule([Action(device="d1", action="transfer")])
    v = parameter_threshold(rule, c)
    assert v is not None
    assert "must declare a numeric 'amount'" in v.reason


def test_threshold_fails_closed_on_non_numeric_parameter():
    c = _make_constraint("amount_cap", "parameter_threshold", action="transfer", parameter="amount", max=1000)
    rule = _make_rule([Action(device="d1", action="transfer", parameters={"amount": True})])
    assert parameter_threshold(rule, c) is not None


def test_threshold_ignores_non_matching_actions():
    c = _make_constraint("amount_cap", "parameter_threshold", action="transfer", parameter="amount", max=1000)
    rule = _make_rule([Action(device="d1", action="notify")])
    assert parameter_threshold(rule, c) is None


def test_threshold_without_bounds_is_noop():
    c = _make_constraint("incomplete", "parameter_threshold", action="transfer", parameter="amount")
    rule = _make_rule([Action(device="d1", action="transfer")])
    assert parameter_threshold(rule, c) is None


def test_threshold_when_action_enforces_bound_on_matching_rule():
    c = _make_constraint(
        "downgrade_needs_streak", "parameter_threshold",
        when_action="downgrade", condition="attestation", parameter="failure_streak", min=2,
    )
    rule = _make_rule(
        [Action(device="d1", action="downgrade")],
        [Condition(type="attestation", parameters={"failure_streak": 0})],
    )
    v = parameter_threshold(rule, c)
    assert v is not None
    assert "below the minimum 2" in v.reason


def test_threshold_when_action_skips_rule_without_that_action():
    c = _make_constraint(
        "downgrade_needs_streak", "parameter_threshold",
        when_action="downgrade", condition="attestation", parameter="failure_streak", min=2,
    )
    # Same condition, same low streak — but this rule only monitors, so the bound must not apply.
    rule = _make_rule(
        [Action(device="d1", action="monitor")],
        [Condition(type="attestation", parameters={"failure_streak": 0})],
    )
    assert parameter_threshold(rule, c) is None


def test_threshold_when_action_composes_with_action_target():
    c = _make_constraint(
        "big_transfer_needs_approval_amount", "parameter_threshold",
        when_action="require_dual_approval", action="transfer", parameter="amount", max=1000,
    )
    # Rule performs the gating action, so the transfer amount bound applies.
    rule = _make_rule([
        Action(device="d1", action="require_dual_approval"),
        Action(device="d1", action="transfer", parameters={"amount": 5000}),
    ])
    assert parameter_threshold(rule, c) is not None
    # Without the gating action the bound is not applicable.
    rule2 = _make_rule([Action(device="d1", action="transfer", parameters={"amount": 5000})])
    assert parameter_threshold(rule2, c) is None


# ----------------------------------------------------------------------
# Validator dispatch
# ----------------------------------------------------------------------

def test_validator_dispatches_generic_type_without_domain():
    c = _make_constraint("no_destroy", "action_denylist", denied_actions=["delete"])
    rule = _make_rule([Action(device="d1", action="delete")])
    result = Validator([c]).validate_rule(rule)
    assert not result.is_valid
    assert result.violations[0].constraint_id == "no_destroy"


def test_domain_evaluator_overrides_generic_builtin():
    def always_reject(rule, constraint):
        return ConstraintViolation(
            constraint_id=constraint.id,
            constraint_description=constraint.description,
            reason="domain override wins",
        )

    domain = Domain(
        id="test_domain", version="0.1",
        trigger_events=frozenset({"event_a"}),
        condition_types=frozenset(),
        action_kinds=frozenset({"notify"}),
        extra_constraint_evaluators={"action_denylist": always_reject},
    )
    # The rule is clean for the generic evaluator; only the override rejects it.
    c = _make_constraint("no_destroy", "action_denylist", denied_actions=["delete"])
    rule = _make_rule([Action(device="d1", action="notify")])
    result = Validator([c], domain=domain).validate_rule(rule)
    assert not result.is_valid
    assert "domain override wins" in result.violations[0].reason


def test_unknown_constraint_type_still_raises():
    c = _make_constraint("mystery", "definitely_not_registered")
    rule = _make_rule([Action(device="d1", action="notify")])
    with pytest.raises(ValueError, match="Unknown constraint type"):
        Validator([c]).validate_rule(rule)


def test_all_generic_types_are_in_registry():
    assert set(GENERIC_EVALUATORS) == {
        "action_allowlist",
        "action_denylist",
        "requires",
        "mutually_exclusive_actions",
        "parameter_threshold",
    }
