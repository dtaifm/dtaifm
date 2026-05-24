"""Tests for `dtaifm propose`, `dtaifm review`, and rule provenance."""

import json
from pathlib import Path


from dtaifm.cli import main
from dtaifm.io import load_ruleset
from dtaifm.schema import SCHEMA_VERSION


EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "smart_rules"
CONSTRAINTS = str(EXAMPLES / "constraints.yaml")


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


# ----------------------------------------------------------------------
# propose
# ----------------------------------------------------------------------

def test_propose_writes_loadable_rule_file(tmp_path, capsys):
    out = tmp_path / "proposed.yaml"
    exit_code = main(["propose", CONSTRAINTS, "--teacher", "mock", "--out", str(out)])
    assert exit_code == 0
    assert out.exists()
    ruleset = load_ruleset(out)
    assert len(ruleset) == 3
    msg = capsys.readouterr().out
    assert "mock" in msg
    assert "Proposal ID" in msg


def test_propose_stamps_provenance_on_every_rule(tmp_path):
    out = tmp_path / "proposed.yaml"
    main(["propose", CONSTRAINTS, "--teacher", "mock", "--out", str(out)])
    ruleset = load_ruleset(out)
    proposal_ids = {r.proposal_id for r in ruleset}
    proposed_bys = {r.proposed_by for r in ruleset}
    created_ats = {r.created_at for r in ruleset}
    # One proposal: one shared proposal_id, one creator, one timestamp.
    assert len(proposal_ids) == 1
    assert "" not in proposal_ids
    assert proposed_bys == {"mock"}
    assert len(created_ats) == 1
    assert all(r.rationale for r in ruleset)


def test_propose_two_runs_produce_distinct_proposal_ids(tmp_path):
    a = tmp_path / "a.yaml"
    b = tmp_path / "b.yaml"
    main(["propose", CONSTRAINTS, "--teacher", "mock", "--out", str(a)])
    main(["propose", CONSTRAINTS, "--teacher", "mock", "--out", str(b)])
    a_id = next(iter(load_ruleset(a))).proposal_id
    b_id = next(iter(load_ruleset(b))).proposal_id
    assert a_id != b_id


def test_propose_supports_json_output(tmp_path):
    out = tmp_path / "proposed.json"
    exit_code = main(["propose", CONSTRAINTS, "--teacher", "mock", "--out", str(out)])
    assert exit_code == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["schema_version"] == SCHEMA_VERSION
    assert len(data["rules"]) == 3
    for r in data["rules"]:
        assert r["proposed_by"] == "mock"
        assert r["proposal_id"]
        assert r["created_at"]


def test_propose_does_not_validate_or_execute(tmp_path, capsys):
    out = tmp_path / "proposed.yaml"
    main(["propose", CONSTRAINTS, "--teacher", "mock", "--out", str(out)])
    msg = capsys.readouterr().out
    # Output never mentions validation/execution status; that's review's job.
    assert "REJECTED" not in msg
    assert "APPROVED" not in msg
    assert "Execution Trace" not in msg
    # The unsafe rule is still in the file — propose only writes the artifact.
    ruleset = load_ruleset(out)
    ids = {r.id for r in ruleset}
    assert "r_auto_unlock_door" in ids


def test_propose_rejects_unknown_teacher(tmp_path, capsys):
    out = tmp_path / "proposed.yaml"
    exit_code = main(["propose", CONSTRAINTS, "--teacher", "nope", "--out", str(out)])
    assert exit_code == 2
    err = capsys.readouterr().err
    assert "Unknown teacher" in err


def test_propose_output_yaml_is_human_readable(tmp_path):
    out = tmp_path / "proposed.yaml"
    main(["propose", CONSTRAINTS, "--teacher", "mock", "--out", str(out)])
    text = out.read_text(encoding="utf-8")
    # Key fields appear in the YAML
    assert "schema_version" in text
    assert "rules:" in text
    assert "r_motion_night_light" in text
    assert "proposed_by: mock" in text


# ----------------------------------------------------------------------
# review
# ----------------------------------------------------------------------

def test_review_produces_combined_audit_artifact(tmp_path, capsys):
    proposed = tmp_path / "proposed.yaml"
    main(["propose", CONSTRAINTS, "--teacher", "mock", "--out", str(proposed)])
    capsys.readouterr()

    state = _write_state(
        tmp_path,
        event_device="motion_sensor",
        event_type="motion_detected",
        time_iso="2024-01-01T23:00:00",
    )
    exit_code = main(["review", CONSTRAINTS, str(proposed), "--state", state, "--json"])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)

    # Combined artifact contains every required section
    assert payload["schema_version"] == SCHEMA_VERSION
    assert "proposals" in payload
    assert "state" in payload
    assert "validation" in payload
    assert "execution" in payload

    # Proposal metadata round-trips from the proposed file
    assert len(payload["proposals"]) == 1
    proposal = payload["proposals"][0]
    assert proposal["proposed_by"] == "mock"
    assert proposal["proposal_id"]
    assert proposal["created_at"]
    assert set(proposal["rule_ids"]) == {"r_motion_night_light", "r_auto_unlock_door", "r_heating_cold"}

    # Validation included with rejected-rule reasons
    statuses = {r["id"]: r["status"] for r in payload["validation"]["rules"]}
    assert statuses["r_auto_unlock_door"] == "rejected"
    rejected = next(r for r in payload["validation"]["rules"] if r["id"] == "r_auto_unlock_door")
    assert any("front_door" in v["reason"] for v in rejected["violations"])

    # Execution trace + final actions only for approved rules
    assert "r_motion_night_light" in payload["execution"]["triggered_rule_ids"]
    assert "r_auto_unlock_door" not in payload["execution"]["triggered_rule_ids"]
    trace_ids = [t["rule_id"] for t in payload["execution"]["trace"]]
    assert "r_auto_unlock_door" not in trace_ids
    assert any(a["device"] == "hallway_light" for a in payload["execution"]["actions_taken"])


def test_review_runtime_never_receives_rejected_rules(tmp_path, capsys):
    proposed = tmp_path / "proposed.yaml"
    main(["propose", CONSTRAINTS, "--teacher", "mock", "--out", str(proposed)])
    capsys.readouterr()

    # Fire the unsafe rule's own event. It must NOT execute.
    state = _write_state(
        tmp_path,
        event_device="arrival_sensor",
        event_type="user_arrived",
        time_iso="2024-01-01T12:00:00",
    )
    main(["review", CONSTRAINTS, str(proposed), "--state", state, "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert "r_auto_unlock_door" not in payload["execution"]["triggered_rule_ids"]
    assert payload["execution"]["actions_taken"] == []


def test_review_text_output_contains_all_sections(tmp_path, capsys):
    proposed = tmp_path / "proposed.yaml"
    main(["propose", CONSTRAINTS, "--teacher", "mock", "--out", str(proposed)])
    capsys.readouterr()

    state = _write_state(
        tmp_path,
        event_device="motion_sensor",
        event_type="motion_detected",
        time_iso="2024-01-01T23:00:00",
    )
    exit_code = main(["review", CONSTRAINTS, str(proposed), "--state", state])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Review Report" in out
    assert "Proposals:" in out
    assert "Validation Report" in out
    assert "Execution Trace" in out
    assert "FIRED" in out
    assert "REJECTED" in out


def test_review_handles_handwritten_rules_without_provenance(tmp_path, capsys):
    state = _write_state(
        tmp_path,
        event_device="motion_sensor",
        event_type="motion_detected",
        time_iso="2024-01-01T23:00:00",
    )
    # Use the example rules.yaml which has rationale/explanation but no proposal_id (hand-written).
    exit_code = main([
        "review", CONSTRAINTS, str(EXAMPLES / "rules.yaml"), "--state", state, "--json",
    ])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert len(payload["proposals"]) == 1
    assert payload["proposals"][0]["proposal_id"] == "<unknown>"
