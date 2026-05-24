"""Tests for the `dtaifm demo` launch-grade walkthrough command.

The demo runs propose -> review -> bundle -> replay end to end. By default
everything is offline (mock teacher, no API key, no network calls), so these
tests run in any environment.
"""

import json
from pathlib import Path

from dtaifm import replay as public_replay
from dtaifm.cli import main
from dtaifm.core.ruleset import RuleSet
from dtaifm.domains.base import Domain
from dtaifm.domains.registry import _DOMAINS, register_domain
from dtaifm.teacher.base import Teacher
from dtaifm.teacher.contract import TeacherResponse
from dtaifm.teacher.registry import _TEACHERS, register_teacher


# ----------------------------------------------------------------------
# Smart home: full walkthrough
# ----------------------------------------------------------------------

def test_cli_demo_smart_home_works_offline(capsys):
    exit_code = main(["demo", "smart_home"])
    assert exit_code == 0
    out = capsys.readouterr().out

    # All five walkthrough steps appear
    for step in ("Step 1/5", "Step 2/5", "Step 3/5", "Step 4/5", "Step 5/5"):
        assert step in out

    # Validator outcomes
    assert "Approved: 2" in out
    assert "Rejected: 1" in out

    # The rejected rule and its named violations
    assert "r_auto_unlock_door" in out
    assert "no_auto_unlock" in out
    assert "rule_must_explain" in out

    # The approved rule fires and its action is shown
    assert "r_motion_night_light" in out
    assert "hallway_light" in out
    assert "turn_on" in out

    # Bundle path mentioned + hashes shown
    assert "review.json" in out
    assert "sha256:" in out

    # Replay verdict
    assert "PASSED" in out


def test_cli_demo_network_automation_works_offline(capsys):
    exit_code = main(["demo", "network_automation"])
    assert exit_code == 0
    out = capsys.readouterr().out

    assert "network_automation domain" in out
    assert "Approved: 2" in out
    assert "Rejected: 1" in out
    assert "r_disable_mgmt_unsafe" in out
    assert "r_apply_router_config_safely" in out
    assert "router1" in out
    assert "apply_config" in out
    assert "PASSED" in out


# ----------------------------------------------------------------------
# JSON output
# ----------------------------------------------------------------------

def test_cli_demo_json_output_shape(capsys):
    exit_code = main(["demo", "smart_home", "--json"])
    assert exit_code == 0
    data = json.loads(capsys.readouterr().out)

    assert data["domain"] == "smart_home"
    assert data["teacher"] == "mock"
    assert data["proposed_rule_count"] == 3
    assert data["approved_count"] == 2
    assert data["rejected_count"] == 1
    assert "r_motion_night_light" in data["triggered_rule_ids"]

    # Action carries enough detail for downstream tools
    action = next(a for a in data["actions_taken"] if a["rule_id"] == "r_motion_night_light")
    assert action["device"] == "hallway_light"
    assert action["action"] == "turn_on"

    # Replay block
    rp = data["replay"]
    assert rp["success"] is True
    assert rp["inputs_intact"] is True
    assert rp["validation_matches"] is True
    assert rp["execution_matches"] is True
    assert rp["issues"] == []

    # Paths are real files
    assert Path(data["proposed_path"]).exists()
    assert Path(data["bundle_path"]).exists()


# ----------------------------------------------------------------------
# Bundle is independently replayable
# ----------------------------------------------------------------------

def test_cli_demo_produces_independently_replayable_bundle(capsys):
    main(["demo", "smart_home", "--json"])
    data = json.loads(capsys.readouterr().out)
    bundle_path = Path(data["bundle_path"])

    # Replay from outside the demo command
    result = public_replay(bundle_path)
    assert result.success
    assert result.inputs_intact
    assert result.validation_matches
    assert result.execution_matches


def test_cli_demo_network_automation_bundle_replays(capsys):
    main(["demo", "network_automation", "--json"])
    data = json.loads(capsys.readouterr().out)
    result = public_replay(Path(data["bundle_path"]))
    assert result.success


# ----------------------------------------------------------------------
# Error paths
# ----------------------------------------------------------------------

def test_cli_demo_unknown_domain_fails_clearly(capsys):
    exit_code = main(["demo", "no_such_domain"])
    assert exit_code == 2
    err = capsys.readouterr().err
    assert "no_such_domain" in err


def test_cli_demo_custom_domain_without_paths_fails_clearly(capsys):
    # Register a domain that has no built-in fixtures
    custom = Domain(
        id="__demo_no_fixtures__",
        version="0.1",
        trigger_events=frozenset({"e"}),
        condition_types=frozenset({"time_range"}),
        action_kinds=frozenset({"a"}),
    )
    register_domain(custom)
    try:
        exit_code = main(["demo", "__demo_no_fixtures__"])
        assert exit_code == 2
        err = capsys.readouterr().err
        assert "no built-in demo fixtures" in err
        assert "--constraints" in err and "--state" in err
    finally:
        _DOMAINS.pop("__demo_no_fixtures__", None)


def test_cli_demo_custom_domain_with_explicit_paths(capsys, tmp_path):
    # A custom domain + minimal constraints + state should run end to end.
    custom = Domain(
        id="__demo_custom__",
        version="0.1",
        trigger_events=frozenset({"motion_detected"}),
        condition_types=frozenset({"time_range", "mode_not", "mode_is", "device_state"}),
        action_kinds=frozenset({"turn_on"}),
    )
    register_domain(custom)
    try:
        c = tmp_path / "c.yaml"
        c.write_text(
            'schema_version: "0.1"\n'
            'constraints:\n'
            '  - id: rme\n'
            '    description: must explain\n'
            '    type: metadata_requirement\n'
            '    required_fields: [satisfies_constraints]\n'
        )
        s = tmp_path / "s.json"
        s.write_text(json.dumps({
            "schema_version": "0.1",
            "event": {"device": "motion_sensor", "type": "motion_detected"},
            "time": "2024-01-01T23:00:00",
            "mode": "normal",
            "devices": {},
        }))
        exit_code = main([
            "demo", "__demo_custom__",
            "--constraints", str(c),
            "--state", str(s),
            "--json",
        ])
        assert exit_code == 0
        data = json.loads(capsys.readouterr().out)
        # MockTeacher has no fixture for this domain -> empty ruleset, but the
        # full pipeline still runs and replay still verifies an empty result.
        assert data["proposed_rule_count"] == 0
        assert data["replay"]["success"] is True
    finally:
        _DOMAINS.pop("__demo_custom__", None)


# ----------------------------------------------------------------------
# Teacher options threading
# ----------------------------------------------------------------------

def test_cli_demo_threads_teacher_options(capsys):
    captured: dict = {}

    class _Recording(Teacher):
        def propose(self, request):
            return TeacherResponse(ruleset=RuleSet(), raw_provider_output="recorded")

    def _factory(**opts):
        captured.update(opts)
        return _Recording()

    register_teacher("__demo_record__", _factory)
    try:
        exit_code = main([
            "demo", "smart_home",
            "--teacher", "__demo_record__",
            "--teacher-base-url", "http://192.0.2.10:13305",
            "--model", "Qwen3-0.6B-GGUF",
        ])
        # Empty ruleset still replays cleanly
        assert exit_code == 0
        assert captured["base_url"] == "http://192.0.2.10:13305"
        assert captured["model"] == "Qwen3-0.6B-GGUF"
    finally:
        _TEACHERS.pop("__demo_record__", None)


# ----------------------------------------------------------------------
# Trust-boundary assertions on the walkthrough text
# ----------------------------------------------------------------------

def test_cli_demo_text_states_runtime_executes_only_approved_rules(capsys):
    main(["demo", "smart_home"])
    out = capsys.readouterr().out
    assert "Runtime executes ONLY approved rules" in out


def test_cli_demo_text_offers_inspect_and_replay_followups(capsys):
    main(["demo", "smart_home"])
    out = capsys.readouterr().out
    # The user should leave the demo knowing how to dig deeper
    assert "dtaifm inspect" in out
    assert "dtaifm replay" in out


# ----------------------------------------------------------------------
# The demo command is not a teacher (sanity)
# ----------------------------------------------------------------------

def test_cli_demo_does_not_appear_in_teacher_registry():
    # Defensive: demos and teachers are distinct concepts.
    from dtaifm.teacher.registry import available_teachers
    assert "demo" not in available_teachers()
