"""Regression: raw provider output is in-memory diagnostic data only and must
NEVER be serialized into any artifact the framework writes.

A teacher's ``raw_provider_output`` can contain secrets or PII (raw prompts and
model responses). These tests pin the contract for every command that runs a
teacher and then writes a file or bundle: ``propose``, ``repropose``, ``demo``,
and the ``propose`` -> ``review --bundle`` chain. Each uses a stub teacher whose
raw output is a sentinel string and asserts the sentinel never reaches disk or
stdout. See issue #10.
"""

import json
from pathlib import Path

from dtaifm.cli import main


EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "smart_rules"
CONSTRAINTS = str(EXAMPLES / "constraints.yaml")
RULES = str(EXAMPLES / "rules.yaml")

SENTINEL = "SECRET-RAW-DO-NOT-LEAK"

# Top-level keys an audit bundle is allowed to contain (the documented contract).
BUNDLE_KEYS = {
    "bundle_version", "framework_version", "schema_version", "created_at",
    "domain", "proposals", "inputs", "validation", "execution",
}


def _register_sentinel_teacher(name):
    """Register a teacher returning an empty RuleSet and a sentinel raw output."""
    from dtaifm.core.ruleset import RuleSet
    from dtaifm.teacher.base import Teacher
    from dtaifm.teacher.contract import TeacherResponse
    from dtaifm.teacher.registry import register_teacher

    class _SentinelTeacher(Teacher):
        def propose(self, request):
            return TeacherResponse(ruleset=RuleSet(), raw_provider_output=SENTINEL)

    register_teacher(name, lambda **_: _SentinelTeacher())


def _write_state(tmp_path):
    p = tmp_path / "state.json"
    p.write_text(json.dumps({
        "schema_version": "0.1",
        "event": {"device": "motion_sensor", "type": "motion_detected"},
        "time": "2024-01-01T23:00:00",
        "mode": "normal",
        "devices": {},
    }))
    return str(p)


def test_propose_does_not_leak_raw_output(tmp_path):
    from dtaifm.teacher.registry import _TEACHERS
    _register_sentinel_teacher("__sentinel_propose__")
    try:
        out = tmp_path / "proposed.yaml"
        rc = main(["propose", CONSTRAINTS, "--teacher", "__sentinel_propose__", "--out", str(out)])
        assert rc == 0
        assert out.exists()
        assert SENTINEL not in out.read_text(encoding="utf-8")
    finally:
        _TEACHERS.pop("__sentinel_propose__", None)


def test_repropose_does_not_leak_raw_output(tmp_path):
    from dtaifm.teacher.registry import _TEACHERS
    _register_sentinel_teacher("__sentinel_repropose__")
    try:
        out = tmp_path / "revised.yaml"
        rc = main(["repropose", CONSTRAINTS, RULES, "--teacher", "__sentinel_repropose__", "--out", str(out)])
        assert rc == 0
        assert out.exists()
        assert SENTINEL not in out.read_text(encoding="utf-8")
    finally:
        _TEACHERS.pop("__sentinel_repropose__", None)


def test_demo_does_not_leak_raw_output(capsys):
    from dtaifm.teacher.registry import _TEACHERS
    _register_sentinel_teacher("__sentinel_demo__")
    try:
        rc = main(["demo", "smart_home", "--teacher", "__sentinel_demo__", "--json"])
        out = capsys.readouterr().out
        assert rc == 0
        assert SENTINEL not in out
        payload = json.loads(out)
        assert SENTINEL not in Path(payload["proposed_path"]).read_text(encoding="utf-8")
        assert SENTINEL not in Path(payload["bundle_path"]).read_text(encoding="utf-8")
    finally:
        _TEACHERS.pop("__sentinel_demo__", None)


def test_review_bundle_does_not_leak_raw_output(tmp_path, capsys):
    """End to end: rules proposed by a sentinel teacher, then review --bundle.

    The sentinel must appear in neither the bundle nor stdout, and the bundle
    must contain only the documented top-level keys (no raw-output field).
    """
    from dtaifm.teacher.registry import _TEACHERS
    _register_sentinel_teacher("__sentinel_review__")
    try:
        proposed = tmp_path / "proposed.yaml"
        rc = main(["propose", CONSTRAINTS, "--teacher", "__sentinel_review__", "--out", str(proposed)])
        assert rc == 0
        capsys.readouterr()  # discard propose output

        state = _write_state(tmp_path)
        bundle = tmp_path / "review.dtaifm-review.json"
        rc = main(["review", CONSTRAINTS, str(proposed), "--state", state, "--bundle", str(bundle)])
        assert rc == 0

        out = capsys.readouterr().out
        assert SENTINEL not in out
        assert bundle.exists()
        bundle_text = bundle.read_text(encoding="utf-8")
        assert SENTINEL not in bundle_text
        assert set(json.loads(bundle_text).keys()) == BUNDLE_KEYS
    finally:
        _TEACHERS.pop("__sentinel_review__", None)
