"""Tests for the feedback artifact + repropose loop.

The deterministic layer may teach the teacher, but it never lets the teacher
grade itself: feedback validates only, repropose writes a revised artifact
without validating or executing it. Only `dtaifm review` (or `dtaifm validate`)
authorizes execution of the revision.
"""

import json
import sys
from pathlib import Path


from dtaifm.cli import main
from dtaifm.core.constraint import Constraint, ConstraintType
from dtaifm.core.rule import Action, Condition, Rule, Trigger
from dtaifm.core.ruleset import RuleSet
from dtaifm.domains.registry import get_domain
from dtaifm.io import load_constraints, load_ruleset
from dtaifm.teacher.base import Teacher
from dtaifm.teacher.contract import PromptContext, TeacherRequest, TeacherResponse
from dtaifm.teacher.feedback import (
    build_feedback,
)
from dtaifm.teacher.mock_teacher import MockTeacher
from dtaifm.teacher.parser import ProviderResponseError
from dtaifm.teacher.prompt import render_teacher_prompt
from dtaifm.teacher.registry import _TEACHERS, register_teacher


EXAMPLES_SH = Path(__file__).resolve().parent.parent / "examples" / "smart_rules"
EXAMPLES_NA = Path(__file__).resolve().parent.parent / "examples" / "network_automation"
SH_CONSTRAINTS = str(EXAMPLES_SH / "constraints.yaml")
SH_RULES = str(EXAMPLES_SH / "rules.yaml")
NA_CONSTRAINTS = str(EXAMPLES_NA / "constraints.yaml")
NA_RULES = str(EXAMPLES_NA / "rules.yaml")


# ----------------------------------------------------------------------
# build_feedback (library API)
# ----------------------------------------------------------------------

def test_build_feedback_includes_named_violations_for_smart_home():
    constraints = load_constraints(Path(SH_CONSTRAINTS))
    ruleset = load_ruleset(Path(SH_RULES))
    feedback = build_feedback(ruleset, constraints, get_domain("smart_home"))

    assert feedback.has_rejections
    assert len(feedback.rejected_rules) == 1
    rec = feedback.rejected_rules[0]
    assert rec.rule_id == "r_auto_unlock_door"
    constraint_ids = {v.constraint_id for v in rec.violations}
    assert "no_auto_unlock" in constraint_ids
    assert "rule_must_explain" in constraint_ids
    # Each violation carries the deterministic reason verbatim
    no_unlock = next(v for v in rec.violations if v.constraint_id == "no_auto_unlock")
    assert "front_door" in no_unlock.reason
    assert "unlock" in no_unlock.reason


def test_build_feedback_includes_domain_vocabulary_per_rule():
    constraints = load_constraints(Path(SH_CONSTRAINTS))
    ruleset = load_ruleset(Path(SH_RULES))
    feedback = build_feedback(ruleset, constraints, get_domain("smart_home"))
    rec = feedback.rejected_rules[0]
    assert "motion_detected" in rec.allowed_triggers
    assert "user_arrived" in rec.allowed_triggers
    assert "turn_on" in rec.allowed_actions
    assert "unlock" in rec.allowed_actions
    assert "time_range" in rec.allowed_conditions
    assert "mode_not" in rec.allowed_conditions


def test_build_feedback_records_approved_rule_ids():
    constraints = load_constraints(Path(SH_CONSTRAINTS))
    ruleset = load_ruleset(Path(SH_RULES))
    feedback = build_feedback(ruleset, constraints, get_domain("smart_home"))
    assert set(feedback.approved_rule_ids) == {"r_motion_night_light", "r_heating_cold"}


def test_build_feedback_when_all_rules_approved():
    constraint = Constraint(
        id="rule_must_explain",
        description="Every generated rule must explain which constraints it satisfies.",
        type=ConstraintType.METADATA_REQUIREMENT,
        parameters={"required_fields": ["satisfies_constraints"]},
    )
    ruleset = RuleSet()
    ruleset.add(Rule(
        id="r_ok", name="OK",
        trigger=Trigger(device="motion_sensor", event="motion_detected"),
        conditions=[Condition(type="mode_not", parameters={"mode": "security"})],
        actions=[Action(device="hallway_light", action="turn_on")],
        satisfies_constraints=["rule_must_explain"],
        rationale="ok",
    ))
    feedback = build_feedback(ruleset, [constraint], get_domain("smart_home"))
    assert not feedback.has_rejections
    assert feedback.rejected_rules == []
    assert feedback.approved_rule_ids == ["r_ok"]


def test_build_feedback_does_not_instantiate_runtime(monkeypatch):
    from dtaifm.runtimes import python_runtime as runtime_mod
    instances: list = []
    orig_init = runtime_mod.PythonRuntime.__init__

    def spy(self, *args, **kwargs):
        instances.append(True)
        return orig_init(self, *args, **kwargs)

    monkeypatch.setattr(runtime_mod.PythonRuntime, "__init__", spy)
    constraints = load_constraints(Path(SH_CONSTRAINTS))
    ruleset = load_ruleset(Path(SH_RULES))
    build_feedback(ruleset, constraints, get_domain("smart_home"))
    assert instances == [], "build_feedback must never instantiate the runtime"


# ----------------------------------------------------------------------
# CLI: feedback command
# ----------------------------------------------------------------------

def test_cli_feedback_writes_spec_compliant_artifact(tmp_path, capsys):
    out = tmp_path / "feedback.json"
    exit_code = main(["feedback", SH_CONSTRAINTS, SH_RULES, "--out", str(out)])
    assert exit_code == 0
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))

    # Top-level shape per spec
    assert data["schema_version"] == "0.1"
    assert data["domain"] == {"id": "smart_home", "version": "0.1"}
    assert isinstance(data["rejected_rules"], list)
    assert len(data["rejected_rules"]) == 1

    rec = data["rejected_rules"][0]
    assert rec["rule_id"] == "r_auto_unlock_door"
    assert isinstance(rec["violations"], list)
    assert isinstance(rec["allowed_triggers"], list)
    assert isinstance(rec["allowed_conditions"], list)
    assert isinstance(rec["allowed_actions"], list)

    v = rec["violations"][0]
    assert "constraint_id" in v
    assert "constraint_description" in v
    assert "reason" in v


def test_cli_feedback_summary_text_includes_counts(tmp_path, capsys):
    out = tmp_path / "feedback.json"
    main(["feedback", SH_CONSTRAINTS, SH_RULES, "--out", str(out)])
    text = capsys.readouterr().out
    assert "Approved:" in text
    assert "Rejected:" in text
    assert "r_auto_unlock_door" in text


def test_cli_feedback_does_not_invoke_runtime(tmp_path, monkeypatch):
    from dtaifm.runtimes import python_runtime as runtime_mod
    instances: list = []
    orig_init = runtime_mod.PythonRuntime.__init__

    def spy(self, *args, **kwargs):
        instances.append(True)
        return orig_init(self, *args, **kwargs)

    monkeypatch.setattr(runtime_mod.PythonRuntime, "__init__", spy)
    out = tmp_path / "feedback.json"
    main(["feedback", SH_CONSTRAINTS, SH_RULES, "--out", str(out)])
    assert instances == []


def test_cli_feedback_does_not_invoke_teacher(tmp_path, monkeypatch):
    """Feedback must work even without any teacher available (no API keys, no SDK)."""
    monkeypatch.setitem(sys.modules, "anthropic", None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out = tmp_path / "feedback.json"
    exit_code = main(["feedback", SH_CONSTRAINTS, SH_RULES, "--out", str(out)])
    assert exit_code == 0


def test_cli_feedback_supports_network_automation(tmp_path, capsys):
    out = tmp_path / "feedback.json"
    exit_code = main([
        "feedback", NA_CONSTRAINTS, NA_RULES,
        "--domain", "network_automation", "--out", str(out),
    ])
    assert exit_code == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["domain"]["id"] == "network_automation"
    rec_ids = {r["rule_id"] for r in data["rejected_rules"]}
    assert "r_disable_mgmt_unsafe" in rec_ids
    # Network vocabulary appears in the per-rule allowed_actions
    rec = next(r for r in data["rejected_rules"] if r["rule_id"] == "r_disable_mgmt_unsafe")
    assert "apply_config" in rec["allowed_actions"]
    assert "rollback" in rec["allowed_actions"]


# ----------------------------------------------------------------------
# Prompt rendering with feedback
# ----------------------------------------------------------------------

def test_prompt_omits_revision_section_when_no_feedback():
    request = TeacherRequest(
        constraints=[],
        context=PromptContext(domain="smart_home"),
        domain=get_domain("smart_home"),
    )
    prompt = render_teacher_prompt(request)
    assert "REVISION REQUESTED" not in prompt


def test_prompt_includes_revision_section_when_feedback_set():
    constraints = load_constraints(Path(SH_CONSTRAINTS))
    ruleset = load_ruleset(Path(SH_RULES))
    domain = get_domain("smart_home")
    feedback = build_feedback(ruleset, constraints, domain)
    from dtaifm.serialize import ruleset_to_dict
    previous = ruleset_to_dict(ruleset)["rules"]

    request = TeacherRequest(
        constraints=constraints,
        context=PromptContext(domain="smart_home"),
        domain=domain,
        feedback=feedback,
        previous_rules=previous,
    )
    prompt = render_teacher_prompt(request)

    # Stable markers for the prompt contract
    assert "REVISION REQUESTED" in prompt
    assert "YOUR PREVIOUS RULES:" in prompt
    assert "REJECTED RULES (must be fixed or removed):" in prompt
    assert "Violations:" in prompt
    assert "Allowed triggers:" in prompt
    assert "Allowed conditions:" in prompt
    assert "Allowed actions:" in prompt

    # The rejected rule's id, its violation constraint_id, and the deterministic reason
    assert "r_auto_unlock_door" in prompt
    assert "no_auto_unlock" in prompt
    assert "rule_must_explain" in prompt
    assert "front_door" in prompt  # part of the deterministic reason

    # The previous-rules block lists ALL original rules so the teacher knows what to keep
    assert "r_motion_night_light" in prompt
    assert "r_heating_cold" in prompt


# ----------------------------------------------------------------------
# MockTeacher revision behavior
# ----------------------------------------------------------------------

def test_mock_teacher_drops_rejected_rules_when_feedback_present():
    constraints = load_constraints(Path(SH_CONSTRAINTS))
    ruleset = load_ruleset(Path(SH_RULES))
    domain = get_domain("smart_home")
    feedback = build_feedback(ruleset, constraints, domain)

    teacher = MockTeacher()
    response = teacher.propose(TeacherRequest(
        constraints=constraints,
        domain=domain,
        feedback=feedback,
        previous_rules=[],
    ))
    ids = {r.id for r in response.ruleset}
    assert "r_auto_unlock_door" not in ids
    assert "r_motion_night_light" in ids
    assert "r_heating_cold" in ids
    assert "dropped 1 rejected rule" in response.raw_provider_output


def test_mock_teacher_drops_rejected_rules_for_network_automation():
    constraints = load_constraints(Path(NA_CONSTRAINTS))
    ruleset = load_ruleset(Path(NA_RULES))
    domain = get_domain("network_automation")
    feedback = build_feedback(ruleset, constraints, domain)

    teacher = MockTeacher()
    response = teacher.propose(TeacherRequest(
        constraints=constraints,
        domain=domain,
        feedback=feedback,
    ))
    ids = {r.id for r in response.ruleset}
    assert "r_disable_mgmt_unsafe" not in ids
    assert "r_apply_router_config_safely" in ids


def test_mock_teacher_without_feedback_returns_full_fixture():
    constraints = load_constraints(Path(SH_CONSTRAINTS))
    teacher = MockTeacher()
    response = teacher.propose(TeacherRequest(
        constraints=constraints,
        domain=get_domain("smart_home"),
    ))
    assert {r.id for r in response.ruleset} == {
        "r_motion_night_light", "r_auto_unlock_door", "r_heating_cold",
    }


# ----------------------------------------------------------------------
# CLI: repropose command
# ----------------------------------------------------------------------

def test_cli_repropose_writes_revised_file_dropping_unsafe(tmp_path, capsys):
    out = tmp_path / "revised.yaml"
    exit_code = main([
        "repropose", SH_CONSTRAINTS, SH_RULES,
        "--teacher", "mock", "--out", str(out),
    ])
    assert exit_code == 0
    assert out.exists()
    revised = load_ruleset(out)
    ids = {r.id for r in revised}
    assert ids == {"r_motion_night_light", "r_heating_cold"}
    # Fresh provenance stamped on each revised rule
    for rule in revised:
        assert rule.proposed_by == "mock"
        assert rule.proposal_id
        assert rule.created_at


def test_cli_repropose_sends_feedback_to_teacher(tmp_path, capsys):
    captured: list[TeacherRequest] = []

    class _CapturingTeacher(Teacher):
        def propose(self, request):
            captured.append(request)
            return TeacherResponse(ruleset=RuleSet(), raw_provider_output="captured")

    register_teacher("__capture_fb__", lambda **_: _CapturingTeacher())
    try:
        out = tmp_path / "revised.yaml"
        exit_code = main([
            "repropose", SH_CONSTRAINTS, SH_RULES,
            "--teacher", "__capture_fb__", "--out", str(out),
        ])
        assert exit_code == 0
        assert len(captured) == 1
        request = captured[0]
        assert request.feedback is not None
        rejected_ids = {r.rule_id for r in request.feedback.rejected_rules}
        assert "r_auto_unlock_door" in rejected_ids
        assert request.previous_rules is not None
        assert {r["id"] for r in request.previous_rules} == {
            "r_motion_night_light", "r_auto_unlock_door", "r_heating_cold",
        }
        assert request.domain is not None
        assert request.domain.id == "smart_home"
    finally:
        _TEACHERS.pop("__capture_fb__", None)


def test_cli_repropose_validates_original_but_not_revised(tmp_path, monkeypatch):
    """The validator runs once on the original rules; the revised rules are NOT validated."""
    from dtaifm.student import validator as validator_mod
    calls = {"count": 0}
    orig = validator_mod.Validator.validate_ruleset

    def spy(self, ruleset):
        calls["count"] += 1
        return orig(self, ruleset)

    monkeypatch.setattr(validator_mod.Validator, "validate_ruleset", spy)
    out = tmp_path / "revised.yaml"
    exit_code = main([
        "repropose", SH_CONSTRAINTS, SH_RULES,
        "--teacher", "mock", "--out", str(out),
    ])
    assert exit_code == 0
    assert calls["count"] == 1


def test_cli_repropose_does_not_execute_runtime(tmp_path, monkeypatch):
    from dtaifm.runtimes import python_runtime as runtime_mod
    instances: list = []
    orig_init = runtime_mod.PythonRuntime.__init__

    def spy(self, *args, **kwargs):
        instances.append(True)
        return orig_init(self, *args, **kwargs)

    monkeypatch.setattr(runtime_mod.PythonRuntime, "__init__", spy)
    out = tmp_path / "revised.yaml"
    main(["repropose", SH_CONSTRAINTS, SH_RULES, "--teacher", "mock", "--out", str(out)])
    assert instances == []


def test_cli_repropose_writes_unsafe_teacher_output_without_validation(tmp_path):
    """If the teacher returns an unsafe revised rule, repropose still writes it.

    The principle: the deterministic layer may teach the teacher, but it never
    grades the teacher's output for it. Only `dtaifm review` validates.
    """

    class _StubbornTeacher(Teacher):
        def propose(self, request):
            rs = RuleSet()
            rs.add(Rule(
                id="r_still_unsafe",
                name="Still Unsafe",
                trigger=Trigger(device="arrival_sensor", event="user_arrived"),
                conditions=[],
                actions=[Action(device="front_door", action="unlock")],
                satisfies_constraints=[],
                rationale="I refuse to learn.",
            ))
            return TeacherResponse(ruleset=rs, raw_provider_output="stubborn")

    register_teacher("__stubborn__", lambda **_: _StubbornTeacher())
    try:
        out = tmp_path / "revised.yaml"
        exit_code = main([
            "repropose", SH_CONSTRAINTS, SH_RULES,
            "--teacher", "__stubborn__", "--out", str(out),
        ])
        assert exit_code == 0
        loaded = load_ruleset(out)
        assert any(r.id == "r_still_unsafe" for r in loaded)

        # Now if we run validate explicitly, the unsafe rule is caught:
        validate_exit = main(["validate", SH_CONSTRAINTS, str(out)])
        assert validate_exit == 1
    finally:
        _TEACHERS.pop("__stubborn__", None)


def test_cli_repropose_propagates_parser_errors_from_adapter(tmp_path, capsys):
    """A teacher whose response can't be parsed must fail clearly (exit 2)."""

    class _MalformedTeacher(Teacher):
        def propose(self, request):
            raise ProviderResponseError("teacher returned garbage")

    register_teacher("__malformed__", lambda **_: _MalformedTeacher())
    try:
        out = tmp_path / "revised.yaml"
        exit_code = main([
            "repropose", SH_CONSTRAINTS, SH_RULES,
            "--teacher", "__malformed__", "--out", str(out),
        ])
        assert exit_code == 2
        assert not out.exists()
        err = capsys.readouterr().err
        assert "garbage" in err
    finally:
        _TEACHERS.pop("__malformed__", None)


def test_cli_repropose_supports_network_automation(tmp_path, capsys):
    out = tmp_path / "na_revised.yaml"
    exit_code = main([
        "repropose", NA_CONSTRAINTS, NA_RULES,
        "--domain", "network_automation",
        "--teacher", "mock", "--out", str(out),
    ])
    assert exit_code == 0
    revised = load_ruleset(out)
    ids = {r.id for r in revised}
    assert "r_disable_mgmt_unsafe" not in ids
    assert "r_apply_router_config_safely" in ids


def test_cli_repropose_threads_base_url_and_model_to_teacher_factory(tmp_path):
    """`repropose` must respect --teacher-base-url and --model just like `propose`."""
    captured_opts: dict = {}

    class _RecordingTeacher(Teacher):
        def propose(self, request):
            return TeacherResponse(ruleset=RuleSet(), raw_provider_output="recorded")

    def _factory(**opts):
        captured_opts.update(opts)
        return _RecordingTeacher()

    register_teacher("__record_repropose__", _factory)
    try:
        out = tmp_path / "revised.yaml"
        exit_code = main([
            "repropose", SH_CONSTRAINTS, SH_RULES,
            "--teacher", "__record_repropose__",
            "--teacher-base-url", "http://192.0.2.10:13305",
            "--model", "Qwen3-0.6B-GGUF",
            "--out", str(out),
        ])
        assert exit_code == 0
        assert captured_opts["base_url"] == "http://192.0.2.10:13305"
        assert captured_opts["model"] == "Qwen3-0.6B-GGUF"
    finally:
        _TEACHERS.pop("__record_repropose__", None)


def test_cli_repropose_threads_teacher_timeout(tmp_path):
    """`repropose --teacher-timeout` must thread through to the teacher factory."""
    captured_opts: dict = {}

    class _RecordingTeacher(Teacher):
        def propose(self, request):
            return TeacherResponse(ruleset=RuleSet(), raw_provider_output="recorded")

    def _factory(**opts):
        captured_opts.update(opts)
        return _RecordingTeacher()

    register_teacher("__repropose_timeout__", _factory)
    try:
        out = tmp_path / "revised.yaml"
        exit_code = main([
            "repropose", SH_CONSTRAINTS, SH_RULES,
            "--teacher", "__repropose_timeout__",
            "--teacher-timeout", "720",
            "--out", str(out),
        ])
        assert exit_code == 0
        assert captured_opts["timeout"] == 720.0
    finally:
        _TEACHERS.pop("__repropose_timeout__", None)


# ----------------------------------------------------------------------
# Full loop: review -> feedback -> repropose -> review
# ----------------------------------------------------------------------

def test_full_repropose_loop_resolves_smart_home_rejection(tmp_path, capsys):
    """A complete loop: review the original (rejection), repropose, then review the revision (clean)."""
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({
        "schema_version": "0.1",
        "event": {"device": "motion_sensor", "type": "motion_detected"},
        "time": "2024-01-01T23:00:00",
        "mode": "normal",
        "devices": {"ac": "off"},
    }))
    revised_path = tmp_path / "revised.yaml"

    # Step 1: review the original — exit 0 but with 1 rejection in the JSON
    exit1 = main([
        "review", SH_CONSTRAINTS, SH_RULES, "--state", str(state_path), "--json",
    ])
    assert exit1 == 0
    review1 = json.loads(capsys.readouterr().out)
    assert review1["validation"]["rejected_count"] == 1

    # Step 2: repropose using mock teacher; drops the unsafe rule
    exit2 = main([
        "repropose", SH_CONSTRAINTS, SH_RULES,
        "--teacher", "mock", "--out", str(revised_path),
    ])
    assert exit2 == 0
    capsys.readouterr()

    # Step 3: review the revision — must be clean (0 rejections)
    exit3 = main([
        "review", SH_CONSTRAINTS, str(revised_path), "--state", str(state_path), "--json",
    ])
    assert exit3 == 0
    review2 = json.loads(capsys.readouterr().out)
    assert review2["validation"]["rejected_count"] == 0
    assert review2["validation"]["approved_count"] == 2
