import json
import sys
from pathlib import Path

import pytest

from dtaifm.cli import main


EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "smart_rules"
CONSTRAINTS = str(EXAMPLES / "constraints.yaml")
RULES = str(EXAMPLES / "rules.yaml")


# ----------------------------------------------------------------------
# validate
# ----------------------------------------------------------------------

def test_validate_exits_nonzero_when_unsafe_rule_present(capsys):
    exit_code = main(["validate", CONSTRAINTS, RULES])
    assert exit_code == 1
    out = capsys.readouterr().out
    assert "APPROVED" in out
    assert "REJECTED" in out
    assert "r_auto_unlock_door" in out
    assert "no_auto_unlock" in out
    assert "rule_must_explain" in out


def test_validate_exits_zero_when_all_rules_safe(tmp_path, capsys):
    safe_rules = tmp_path / "safe_rules.yaml"
    safe_rules.write_text(
        """
schema_version: "0.1"
rules:
  - id: r_safe_light
    name: Safe Light
    trigger:
      device: motion_sensor
      event: motion_detected
    conditions:
      - type: time_range
        start_hour: 22
        end_hour: 6
      - type: mode_not
        mode: security
    actions:
      - device: hallway_light
        action: turn_on
    satisfies_constraints:
      - motion_light_hours
      - security_override
    explanation: Safe motion light.
"""
    )
    exit_code = main(["validate", CONSTRAINTS, str(safe_rules)])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "REJECTED" not in out


def test_validate_json_output_structure(capsys):
    exit_code = main(["validate", CONSTRAINTS, RULES, "--json"])
    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["constraint_count"] == 5
    assert payload["rule_count"] == 3
    assert payload["approved_count"] == 2
    assert payload["rejected_count"] == 1
    assert payload["all_approved"] is False
    statuses = {r["id"]: r["status"] for r in payload["rules"]}
    assert statuses["r_motion_night_light"] == "approved"
    assert statuses["r_auto_unlock_door"] == "rejected"
    assert statuses["r_heating_cold"] == "approved"
    rejected = next(r for r in payload["rules"] if r["id"] == "r_auto_unlock_door")
    violation_ids = {v["constraint_id"] for v in rejected["violations"]}
    assert "no_auto_unlock" in violation_ids
    assert "rule_must_explain" in violation_ids
    for v in rejected["violations"]:
        assert v["reason"]  # non-empty reason


def test_validate_audit_report_contains_rejected_reasons(capsys):
    main(["validate", CONSTRAINTS, RULES, "--json"])
    payload = json.loads(capsys.readouterr().out)
    rejected = next(r for r in payload["rules"] if r["id"] == "r_auto_unlock_door")
    no_unlock = next(v for v in rejected["violations"] if v["constraint_id"] == "no_auto_unlock")
    assert "front_door" in no_unlock["reason"]
    assert "unlock" in no_unlock["reason"]


# ----------------------------------------------------------------------
# run
# ----------------------------------------------------------------------

def _write_state(tmp_path: Path, *, event_device, event_type, time_iso, mode="normal", devices=None):
    p = tmp_path / "state.json"
    p.write_text(json.dumps({
        "schema_version": "0.1",
        "event": {"device": event_device, "type": event_type},
        "time": time_iso,
        "mode": mode,
        "devices": devices or {},
    }))
    return str(p)


def test_run_executes_approved_rule_on_matching_event(tmp_path, capsys):
    state = _write_state(
        tmp_path,
        event_device="motion_sensor",
        event_type="motion_detected",
        time_iso="2024-01-01T23:00:00",
    )
    exit_code = main(["run", CONSTRAINTS, RULES, "--state", state, "--json"])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert "r_motion_night_light" in payload["execution"]["triggered_rule_ids"]


def test_run_never_executes_rejected_rule(tmp_path, capsys):
    # Fire the event the unsafe rule subscribes to. It must NOT execute because it was rejected.
    state = _write_state(
        tmp_path,
        event_device="arrival_sensor",
        event_type="user_arrived",
        time_iso="2024-01-01T12:00:00",
    )
    exit_code = main(["run", CONSTRAINTS, RULES, "--state", state, "--json"])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    triggered = payload["execution"]["triggered_rule_ids"]
    assert "r_auto_unlock_door" not in triggered
    # The trace should not even include the unsafe rule, since the runtime never received it.
    trace_ids = [t["rule_id"] for t in payload["execution"]["trace"]]
    assert "r_auto_unlock_door" not in trace_ids


def test_run_trace_explains_why_rule_did_not_fire(tmp_path, capsys):
    # 14:00 is outside the night-hour window, so the night light should not fire.
    state = _write_state(
        tmp_path,
        event_device="motion_sensor",
        event_type="motion_detected",
        time_iso="2024-01-01T14:00:00",
    )
    exit_code = main(["run", CONSTRAINTS, RULES, "--state", state, "--json"])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    trace = next(t for t in payload["execution"]["trace"] if t["rule_id"] == "r_motion_night_light")
    assert trace["matched_trigger"] is True
    assert trace["fired"] is False
    assert "time_range" in trace["reason"]
    time_cond = next(c for c in trace["conditions_evaluated"] if c["type"] == "time_range")
    assert time_cond["passed"] is False


def test_run_trace_marks_fired_rule(tmp_path, capsys):
    state = _write_state(
        tmp_path,
        event_device="motion_sensor",
        event_type="motion_detected",
        time_iso="2024-01-01T23:00:00",
    )
    main(["run", CONSTRAINTS, RULES, "--state", state, "--json"])
    payload = json.loads(capsys.readouterr().out)
    fired = next(t for t in payload["execution"]["trace"] if t["rule_id"] == "r_motion_night_light")
    assert fired["fired"] is True
    assert all(c["passed"] for c in fired["conditions_evaluated"])


def test_run_text_output_shows_trace(tmp_path, capsys):
    state = _write_state(
        tmp_path,
        event_device="motion_sensor",
        event_type="motion_detected",
        time_iso="2024-01-01T23:00:00",
    )
    exit_code = main(["run", CONSTRAINTS, RULES, "--state", state])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Validation Report" in out
    assert "Execution Trace" in out
    assert "FIRED" in out
    assert "r_motion_night_light" in out


# ----------------------------------------------------------------------
# malformed input
# ----------------------------------------------------------------------

def test_malformed_rules_file_fails_with_clear_error(tmp_path, capsys):
    bad = tmp_path / "bad.yaml"
    bad.write_text("rules: [unterminated")
    exit_code = main(["validate", CONSTRAINTS, str(bad)])
    assert exit_code == 2
    err = capsys.readouterr().err
    assert "Error" in err
    assert "invalid YAML" in err


def test_missing_constraints_file_fails(tmp_path, capsys):
    exit_code = main(["validate", str(tmp_path / "nope.yaml"), RULES])
    assert exit_code == 2
    err = capsys.readouterr().err
    assert "Error" in err


def test_state_missing_event_fails(tmp_path, capsys):
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"schema_version": "0.1", "mode": "normal"}))
    exit_code = main(["run", CONSTRAINTS, RULES, "--state", str(state)])
    assert exit_code == 2
    err = capsys.readouterr().err
    assert "event" in err


# ----------------------------------------------------------------------
# prompt
# ----------------------------------------------------------------------

def test_prompt_command_emits_prompt_text(capsys):
    exit_code = main(["prompt", CONSTRAINTS, "--teacher", "mock"])
    assert exit_code == 0
    out = capsys.readouterr().out
    # Every constraint from the example file appears
    assert "no_auto_unlock" in out
    assert "no_hvac_conflict" in out
    assert "motion_light_hours" in out
    assert "security_override" in out
    assert "rule_must_explain" in out
    # The framework principle is stated
    assert "artifact" in out.lower()
    # The prompt demands the literal JSON envelope (no tool-specific wording).
    assert "schema_version" in out
    assert "rules" in out


def test_prompt_command_includes_domain(capsys):
    exit_code = main(["prompt", CONSTRAINTS, "--teacher", "mock", "--domain", "smart_home"])
    assert exit_code == 0
    assert "smart_home" in capsys.readouterr().out


def test_prompt_command_works_with_anthropic_teacher_without_api_key(monkeypatch, capsys):
    # The prompt command must NOT require API credentials — it only renders text.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    exit_code = main(["prompt", CONSTRAINTS, "--teacher", "anthropic"])
    assert exit_code == 0
    assert "no_auto_unlock" in capsys.readouterr().out


def test_prompt_command_rejects_unknown_teacher(capsys):
    exit_code = main(["prompt", CONSTRAINTS, "--teacher", "nope"])
    assert exit_code == 2
    assert "Unknown teacher" in capsys.readouterr().err


# ----------------------------------------------------------------------
# propose: provider-extra failure modes
# ----------------------------------------------------------------------

def test_propose_anthropic_fails_clearly_when_sdk_missing(tmp_path, monkeypatch, capsys):
    # Force `import anthropic` to fail inside the adapter constructor.
    monkeypatch.setitem(sys.modules, "anthropic", None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out = tmp_path / "p.yaml"
    exit_code = main(["propose", CONSTRAINTS, "--teacher", "anthropic", "--out", str(out)])
    assert exit_code == 2
    err = capsys.readouterr().err
    assert "dtaifm[anthropic]" in err
    assert not out.exists()


def test_propose_anthropic_fails_clearly_when_api_key_missing(tmp_path, monkeypatch, capsys):
    # Pretend the SDK is importable; missing API key must surface as a clear error.
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    fake_sdk = SimpleNamespace(Anthropic=lambda api_key: MagicMock())
    monkeypatch.setitem(sys.modules, "anthropic", fake_sdk)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out = tmp_path / "p.yaml"
    exit_code = main(["propose", CONSTRAINTS, "--teacher", "anthropic", "--out", str(out)])
    assert exit_code == 2
    err = capsys.readouterr().err
    assert "ANTHROPIC_API_KEY" in err
    assert not out.exists()


# ----------------------------------------------------------------------
# propose: --teacher-base-url / --model threading
# ----------------------------------------------------------------------

def test_propose_threads_base_url_and_model_through_to_teacher_factory(tmp_path, capsys):
    """`dtaifm propose --teacher X --teacher-base-url Y --model Z` must hand Y and Z to X's factory."""
    from dtaifm.core.ruleset import RuleSet
    from dtaifm.teacher.base import Teacher
    from dtaifm.teacher.contract import TeacherResponse
    from dtaifm.teacher.registry import _TEACHERS, register_teacher

    captured: dict = {}

    class _RecordingTeacher(Teacher):
        def propose(self, request):
            return TeacherResponse(
                ruleset=RuleSet(source="recording"),
                raw_provider_output="recording",
            )

    def _factory(**opts):
        captured.update(opts)
        return _RecordingTeacher()

    register_teacher("__record__", _factory)
    try:
        out = tmp_path / "proposed.yaml"
        exit_code = main([
            "propose", CONSTRAINTS,
            "--teacher", "__record__",
            "--teacher-base-url", "http://192.0.2.10:13305",
            "--model", "Qwen3-0.6B-GGUF",
            "--out", str(out),
        ])
        assert exit_code == 0
        assert captured["base_url"] == "http://192.0.2.10:13305"
        assert captured["model"] == "Qwen3-0.6B-GGUF"
    finally:
        _TEACHERS.pop("__record__", None)


def test_propose_without_explicit_options_passes_none(tmp_path, capsys):
    """When the user omits --teacher-base-url and --model, the factory receives None for both."""
    from dtaifm.core.ruleset import RuleSet
    from dtaifm.teacher.base import Teacher
    from dtaifm.teacher.contract import TeacherResponse
    from dtaifm.teacher.registry import _TEACHERS, register_teacher

    captured: dict = {}

    class _RecordingTeacher(Teacher):
        def propose(self, request):
            return TeacherResponse(ruleset=RuleSet(), raw_provider_output="")

    def _factory(**opts):
        captured.update(opts)
        return _RecordingTeacher()

    register_teacher("__record2__", _factory)
    try:
        out = tmp_path / "proposed.yaml"
        main(["propose", CONSTRAINTS, "--teacher", "__record2__", "--out", str(out)])
        assert captured["base_url"] is None
        assert captured["model"] is None
        assert captured["timeout"] is None
    finally:
        _TEACHERS.pop("__record2__", None)


# ----------------------------------------------------------------------
# propose: --teacher-timeout threading (v0.1.1)
# ----------------------------------------------------------------------

def _register_recording_teacher(name, captured):
    """Helper: register a teacher that records every kwarg it was constructed with."""
    from dtaifm.core.ruleset import RuleSet
    from dtaifm.teacher.base import Teacher
    from dtaifm.teacher.contract import TeacherResponse
    from dtaifm.teacher.registry import register_teacher

    class _RecordingTeacher(Teacher):
        def propose(self, request):
            return TeacherResponse(ruleset=RuleSet(), raw_provider_output="")

    def _factory(**opts):
        captured.update(opts)
        return _RecordingTeacher()

    register_teacher(name, _factory)


def test_propose_threads_teacher_timeout_flag(tmp_path):
    from dtaifm.teacher.registry import _TEACHERS
    captured: dict = {}
    _register_recording_teacher("__timeout_propose__", captured)
    try:
        out = tmp_path / "p.yaml"
        exit_code = main([
            "propose", CONSTRAINTS,
            "--teacher", "__timeout_propose__",
            "--teacher-timeout", "300",
            "--out", str(out),
        ])
        assert exit_code == 0
        assert captured["timeout"] == 300.0
    finally:
        _TEACHERS.pop("__timeout_propose__", None)


def test_cli_teacher_timeout_non_numeric_fails(tmp_path, capsys):
    # argparse rejects the type=float conversion with SystemExit code 2.
    with pytest.raises(SystemExit) as exc:
        main([
            "propose", CONSTRAINTS,
            "--teacher", "mock",
            "--teacher-timeout", "abc",
            "--out", str(tmp_path / "p.yaml"),
        ])
    assert exc.value.code == 2


def test_cli_teacher_timeout_negative_fails(tmp_path, capsys):
    # Negative values pass argparse but fail in resolve_timeout — caught by
    # main()'s ValueError handler with exit 2 and a clear stderr message.
    from dtaifm.teacher.registry import _TEACHERS
    captured: dict = {}
    _register_recording_teacher("__timeout_propose_neg__", captured)
    # Even though we register a recording teacher, we point at a real local
    # adapter so resolve_timeout fires. We use ollama because its factory
    # constructs the real adapter.
    try:
        exit_code = main([
            "propose", CONSTRAINTS,
            "--teacher", "ollama",
            "--teacher-timeout", "-1",
            "--out", str(tmp_path / "p.yaml"),
        ])
        assert exit_code == 2
        err = capsys.readouterr().err
        assert "positive" in err.lower()
    finally:
        _TEACHERS.pop("__timeout_propose_neg__", None)


def test_cli_teacher_timeout_env_var_used_when_no_flag(tmp_path, monkeypatch):
    monkeypatch.setenv("DTAIFM_HTTP_TIMEOUT", "240")
    from dtaifm.teacher.registry import get_teacher
    # The CLI passes timeout=None when no flag is given; resolve_timeout falls
    # back to the env var. Verify end-to-end via the real ollama adapter.
    teacher = get_teacher("ollama")
    assert teacher.timeout == 240.0


def test_cli_teacher_timeout_flag_beats_env_var(tmp_path, monkeypatch):
    monkeypatch.setenv("DTAIFM_HTTP_TIMEOUT", "240")
    from dtaifm.teacher.registry import get_teacher
    teacher = get_teacher("ollama", timeout=900.0)
    assert teacher.timeout == 900.0
