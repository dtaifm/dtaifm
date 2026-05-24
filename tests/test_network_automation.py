"""End-to-end tests for the network_automation domain pack."""

import json
from pathlib import Path


from dtaifm.cli import main
from dtaifm.core.rule import Action, Condition, Rule, Trigger
from dtaifm.domains.network_automation.evaluators import (
    action_target_limit,
    companion_action_required,
    mode_required,
)
from dtaifm.domains.registry import get_domain
from dtaifm.io import load_constraints, load_ruleset
from dtaifm.student.validator import Validator
from dtaifm.teacher.contract import TeacherRequest
from dtaifm.teacher.mock_teacher import MockTeacher


EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "network_automation"
CONSTRAINTS = str(EXAMPLES / "constraints.yaml")
RULES = str(EXAMPLES / "rules.yaml")
STATE = str(EXAMPLES / "state.json")


def _make_constraint(id_, type_, **params):
    from dtaifm.core.constraint import Constraint
    return Constraint(id=id_, description=f"test {id_}", type=type_, parameters=params)


# ----------------------------------------------------------------------
# Domain-specific evaluators
# ----------------------------------------------------------------------

def test_companion_action_required_flags_missing_rollback():
    constraint = _make_constraint(
        "needs_rollback", "companion_action_required",
        if_action="apply_config", requires_action="rollback",
    )
    rule = Rule(
        id="r_no_rollback", name="No rollback",
        trigger=Trigger(device="scheduler", event="config_change_requested"),
        actions=[Action(device="router1", action="apply_config")],
        satisfies_constraints=["x"], rationale="x",
    )
    violation = companion_action_required(rule, constraint)
    assert violation is not None
    assert "missing the required companion action 'rollback'" in violation.reason


def test_companion_action_required_passes_when_rollback_present():
    constraint = _make_constraint(
        "needs_rollback", "companion_action_required",
        if_action="apply_config", requires_action="rollback",
    )
    rule = Rule(
        id="r_with_rollback", name="With rollback",
        trigger=Trigger(device="scheduler", event="config_change_requested"),
        actions=[
            Action(device="router1", action="apply_config"),
            Action(device="router1", action="rollback"),
        ],
        satisfies_constraints=["x"], rationale="x",
    )
    assert companion_action_required(rule, constraint) is None


def test_action_target_limit_flags_too_many_devices():
    constraint = _make_constraint(
        "limit", "action_target_limit", action_type="apply_config", max_devices=1,
    )
    rule = Rule(
        id="r_bulk", name="Bulk apply",
        trigger=Trigger(device="scheduler", event="config_change_requested"),
        actions=[
            Action(device="router1", action="apply_config"),
            Action(device="router2", action="apply_config"),
        ],
        satisfies_constraints=["x"], rationale="x",
    )
    violation = action_target_limit(rule, constraint)
    assert violation is not None
    assert "2 devices" in violation.reason


def test_mode_required_flags_missing_mode_is_guard():
    constraint = _make_constraint(
        "needs_maintenance", "mode_required",
        required_mode="maintenance", applies_to=["router1"],
    )
    rule = Rule(
        id="r_no_guard", name="No maintenance guard",
        trigger=Trigger(device="scheduler", event="config_change_requested"),
        actions=[Action(device="router1", action="apply_config")],
        satisfies_constraints=["x"], rationale="x",
    )
    violation = mode_required(rule, constraint)
    assert violation is not None
    assert "mode_is: maintenance" in violation.reason


def test_mode_required_passes_when_guard_present():
    constraint = _make_constraint(
        "needs_maintenance", "mode_required",
        required_mode="maintenance", applies_to=["router1"],
    )
    rule = Rule(
        id="r_with_guard", name="With maintenance guard",
        trigger=Trigger(device="scheduler", event="config_change_requested"),
        conditions=[Condition(type="mode_is", parameters={"mode": "maintenance"})],
        actions=[Action(device="router1", action="apply_config")],
        satisfies_constraints=["x"], rationale="x",
    )
    assert mode_required(rule, constraint) is None


# ----------------------------------------------------------------------
# End-to-end via CLI (validate / review)
# ----------------------------------------------------------------------

def test_validate_network_automation_example_rejects_unsafe_only(capsys):
    exit_code = main([
        "validate", CONSTRAINTS, RULES, "--domain", "network_automation", "--json",
    ])
    # Two valid + one rejected → exit 1
    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    statuses = {r["id"]: r["status"] for r in payload["rules"]}
    assert statuses["r_apply_router_config_safely"] == "approved"
    assert statuses["r_notify_operator_on_flap"] == "approved"
    assert statuses["r_disable_mgmt_unsafe"] == "rejected"
    rejected = next(r for r in payload["rules"] if r["id"] == "r_disable_mgmt_unsafe")
    violation_ids = {v["constraint_id"] for v in rejected["violations"]}
    assert "no_disable_mgmt" in violation_ids
    assert "rule_must_explain" in violation_ids


def test_review_network_automation_fires_only_approved_rule(capsys):
    exit_code = main([
        "review", CONSTRAINTS, RULES, "--state", STATE,
        "--domain", "network_automation", "--json",
    ])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    triggered = payload["execution"]["triggered_rule_ids"]
    assert "r_apply_router_config_safely" in triggered
    assert "r_disable_mgmt_unsafe" not in triggered
    # Final actions must be the maintenance-mode router1 config + rollback pair
    actions = [(a["device"], a["action"]) for a in payload["execution"]["actions_taken"]]
    assert ("router1", "apply_config") in actions
    assert ("router1", "rollback") in actions


def test_review_network_automation_runtime_never_executes_rejected_rule(tmp_path, capsys):
    # Fire the unsafe rule's own event. It must NOT execute.
    state = tmp_path / "state.json"
    state.write_text(json.dumps({
        "schema_version": "0.1",
        "event": {"device": "monitoring", "type": "interface_down_alert"},
        "time": "2024-01-01T02:30:00",
        "mode": "maintenance",
        "devices": {},
    }))
    exit_code = main([
        "review", CONSTRAINTS, RULES, "--state", str(state),
        "--domain", "network_automation", "--json",
    ])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert "r_disable_mgmt_unsafe" not in payload["execution"]["triggered_rule_ids"]
    assert payload["execution"]["actions_taken"] == []


def test_mock_teacher_proposes_network_automation_rules(tmp_path, capsys):
    out = tmp_path / "proposed.yaml"
    exit_code = main([
        "propose", CONSTRAINTS,
        "--teacher", "mock", "--out", str(out),
        "--domain", "network_automation",
    ])
    assert exit_code == 0
    ruleset = load_ruleset(out)
    ids = {r.id for r in ruleset}
    assert "r_apply_router_config_safely" in ids
    assert "r_disable_mgmt_unsafe" in ids
    # Provenance is stamped just like smart_home propose
    for rule in ruleset:
        assert rule.proposed_by == "mock"
        assert rule.proposal_id
        assert rule.created_at


def test_propose_then_review_network_automation_chain(tmp_path, capsys):
    out = tmp_path / "proposed.yaml"
    main([
        "propose", CONSTRAINTS,
        "--teacher", "mock", "--out", str(out),
        "--domain", "network_automation",
    ])
    capsys.readouterr()
    main([
        "review", CONSTRAINTS, str(out), "--state", STATE,
        "--domain", "network_automation", "--json",
    ])
    payload = json.loads(capsys.readouterr().out)
    # Same outcome as the hand-written file: only the safe rule fires.
    assert payload["execution"]["triggered_rule_ids"] == ["r_apply_router_config_safely"]


def test_prompt_for_network_automation_includes_only_network_vocabulary(capsys):
    exit_code = main([
        "prompt", CONSTRAINTS,
        "--teacher", "mock", "--domain", "network_automation",
    ])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "apply_config" in out
    assert "rollback" in out
    assert "config_change_requested" in out
    # Smart-home vocab must not leak in
    assert "turn_on" not in out
    assert "motion_detected" not in out


# ----------------------------------------------------------------------
# Smart home still flows through the (now domain-aware) layer
# ----------------------------------------------------------------------

def test_smart_home_example_still_validates_under_domain():
    examples = Path(__file__).resolve().parent.parent / "examples" / "smart_rules"
    constraints = load_constraints(examples / "constraints.yaml")
    ruleset = load_ruleset(examples / "rules.yaml")
    domain = get_domain("smart_home")
    validator = Validator(constraints, domain=domain)
    result = validator.validate_ruleset(ruleset)
    # Same outcome as before adding domains: 2 approved, 1 rejected (auto-unlock).
    assert set(result.approved) == {"r_motion_night_light", "r_heating_cold"}
    assert {vr.rule_id for vr in result.rejected} == {"r_auto_unlock_door"}


def test_mock_teacher_dispatches_by_request_domain():
    teacher = MockTeacher()
    smart = teacher.propose(TeacherRequest(constraints=[], domain=get_domain("smart_home"))).ruleset
    network = teacher.propose(TeacherRequest(constraints=[], domain=get_domain("network_automation"))).ruleset
    assert {r.id for r in smart} & {r.id for r in network} == set()
    assert {r.id for r in smart} == {"r_motion_night_light", "r_auto_unlock_door", "r_heating_cold"}
    assert "r_apply_router_config_safely" in {r.id for r in network}


def test_mock_teacher_unknown_domain_returns_empty_ruleset():
    teacher = MockTeacher()
    from dtaifm.domains.base import Domain
    custom = Domain(id="something_unknown", version="0.1")
    response = teacher.propose(TeacherRequest(constraints=[], domain=custom))
    assert len(response.ruleset) == 0
    assert "no built-in fixture" in response.raw_provider_output
