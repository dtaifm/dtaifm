"""Tests for audit bundles: hashing, review, replay, inspect, CLI integration."""

import json
from pathlib import Path

import yaml

from dtaifm import inspect_bundle as public_inspect
from dtaifm import replay as public_replay
from dtaifm import review as public_review
from dtaifm.bundle import (
    BUNDLE_VERSION,
    ReplayResult,
    canonical_json,
    load_bundle,
    sha256_of,
)
from dtaifm.cli import main


EXAMPLES_SH = Path(__file__).resolve().parent.parent / "examples" / "smart_rules"
EXAMPLES_NA = Path(__file__).resolve().parent.parent / "examples" / "network_automation"


# ----------------------------------------------------------------------
# Canonical JSON + hashing
# ----------------------------------------------------------------------

def test_canonical_json_sorts_keys():
    assert canonical_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'


def test_canonical_json_uses_compact_separators():
    assert canonical_json({"a": [1, 2]}) == '{"a":[1,2]}'


def test_canonical_json_handles_nested_structures():
    s = canonical_json({"outer": {"z": 9, "a": 1}, "list": [{"b": 2, "a": 1}]})
    assert s == '{"list":[{"a":1,"b":2}],"outer":{"a":1,"z":9}}'


def test_sha256_of_is_key_order_independent():
    h1 = sha256_of({"x": 1, "y": [1, 2], "z": {"a": 1}})
    h2 = sha256_of({"z": {"a": 1}, "y": [1, 2], "x": 1})
    assert h1 == h2
    assert h1.startswith("sha256:")


def test_sha256_changes_on_content_change():
    assert sha256_of({"x": 1}) != sha256_of({"x": 2})
    assert sha256_of({"a": [1, 2]}) != sha256_of({"a": [2, 1]})  # list order matters


# ----------------------------------------------------------------------
# review (library API)
# ----------------------------------------------------------------------

def test_review_returns_complete_bundle():
    bundle = public_review(
        constraints_path=EXAMPLES_SH / "constraints.yaml",
        rules_path=EXAMPLES_SH / "rules.yaml",
        state_path=EXAMPLES_SH / "state.json",
        domain_id="smart_home",
    )
    assert bundle["bundle_version"] == BUNDLE_VERSION
    assert bundle["framework_version"]
    assert bundle["schema_version"] == "0.1"
    assert bundle["domain"] == {"id": "smart_home", "version": "0.1"}
    assert "created_at" in bundle
    assert isinstance(bundle["proposals"], list)

    for kind in ("constraints", "rules", "state"):
        inp = bundle["inputs"][kind]
        assert inp["hash"].startswith("sha256:")
        assert "content" in inp
        # Bundle is self-consistent: stored hash matches stored content
        assert sha256_of(inp["content"]) == inp["hash"]

    assert bundle["validation"]["hash"].startswith("sha256:")
    assert sha256_of(bundle["validation"]["result"]) == bundle["validation"]["hash"]
    assert bundle["execution"]["hash"].startswith("sha256:")
    assert sha256_of(bundle["execution"]["result"]) == bundle["execution"]["hash"]


def test_review_writes_bundle_when_path_given(tmp_path):
    bundle_path = tmp_path / "review.json"
    bundle = public_review(
        constraints_path=EXAMPLES_SH / "constraints.yaml",
        rules_path=EXAMPLES_SH / "rules.yaml",
        state_path=EXAMPLES_SH / "state.json",
        domain_id="smart_home",
        bundle_path=bundle_path,
    )
    assert bundle_path.exists()
    reloaded = json.loads(bundle_path.read_text())
    assert reloaded == bundle


def test_review_yaml_and_json_constraints_hash_identically(tmp_path):
    yaml_path = EXAMPLES_SH / "constraints.yaml"
    json_path = tmp_path / "constraints.json"
    parsed = yaml.safe_load(yaml_path.read_text())
    json_path.write_text(json.dumps(parsed))

    bundle_yaml = public_review(
        constraints_path=yaml_path,
        rules_path=EXAMPLES_SH / "rules.yaml",
        state_path=EXAMPLES_SH / "state.json",
        domain_id="smart_home",
    )
    bundle_json = public_review(
        constraints_path=json_path,
        rules_path=EXAMPLES_SH / "rules.yaml",
        state_path=EXAMPLES_SH / "state.json",
        domain_id="smart_home",
    )
    # Same logical content, different file format → same canonical hash
    assert bundle_yaml["inputs"]["constraints"]["hash"] == bundle_json["inputs"]["constraints"]["hash"]


def test_review_same_inputs_produce_identical_validation_and_execution_hashes():
    a = public_review(
        constraints_path=EXAMPLES_SH / "constraints.yaml",
        rules_path=EXAMPLES_SH / "rules.yaml",
        state_path=EXAMPLES_SH / "state.json",
        domain_id="smart_home",
    )
    b = public_review(
        constraints_path=EXAMPLES_SH / "constraints.yaml",
        rules_path=EXAMPLES_SH / "rules.yaml",
        state_path=EXAMPLES_SH / "state.json",
        domain_id="smart_home",
    )
    # Inputs identical → validation/execution hashes identical (only `created_at` differs)
    assert a["inputs"]["constraints"]["hash"] == b["inputs"]["constraints"]["hash"]
    assert a["validation"]["hash"] == b["validation"]["hash"]
    assert a["execution"]["hash"] == b["execution"]["hash"]


# ----------------------------------------------------------------------
# replay
# ----------------------------------------------------------------------

def _fresh_bundle(tmp_path, *, network=False) -> Path:
    examples = EXAMPLES_NA if network else EXAMPLES_SH
    domain_id = "network_automation" if network else "smart_home"
    bundle_path = tmp_path / "review.json"
    public_review(
        constraints_path=examples / "constraints.yaml",
        rules_path=examples / "rules.yaml",
        state_path=examples / "state.json",
        domain_id=domain_id,
        bundle_path=bundle_path,
    )
    return bundle_path


def test_replay_succeeds_for_unchanged_bundle(tmp_path):
    bundle_path = _fresh_bundle(tmp_path)
    result = public_replay(bundle_path)
    assert isinstance(result, ReplayResult)
    assert result.success
    assert result.inputs_intact
    assert result.validation_matches
    assert result.execution_matches
    assert result.domain_version_matches
    assert result.issues == []


def test_replay_accepts_dict_argument(tmp_path):
    bundle_path = _fresh_bundle(tmp_path)
    bundle_dict = load_bundle(bundle_path)
    result = public_replay(bundle_dict)
    assert result.success


def test_replay_detects_tampered_constraints(tmp_path):
    bundle_path = _fresh_bundle(tmp_path)
    bundle = load_bundle(bundle_path)
    bundle["inputs"]["constraints"]["content"][0]["action"] = "tampered_value"
    bundle_path.write_text(json.dumps(bundle))
    result = public_replay(bundle_path)
    assert not result.success
    assert not result.inputs_intact
    assert any("constraints" in i.lower() for i in result.issues)


def test_replay_detects_tampered_rules(tmp_path):
    bundle_path = _fresh_bundle(tmp_path)
    bundle = load_bundle(bundle_path)
    bundle["inputs"]["rules"]["content"]["rules"][0]["name"] = "Tampered Name"
    bundle_path.write_text(json.dumps(bundle))
    result = public_replay(bundle_path)
    assert not result.success
    assert not result.inputs_intact
    assert any("rules" in i.lower() for i in result.issues)


def test_replay_detects_tampered_state(tmp_path):
    bundle_path = _fresh_bundle(tmp_path)
    bundle = load_bundle(bundle_path)
    bundle["inputs"]["state"]["content"]["mode"] = "tampered_mode"
    bundle_path.write_text(json.dumps(bundle))
    result = public_replay(bundle_path)
    assert not result.success
    assert not result.inputs_intact
    assert any("state" in i.lower() for i in result.issues)


def test_replay_detects_tampered_validation_result(tmp_path):
    bundle_path = _fresh_bundle(tmp_path)
    bundle = load_bundle(bundle_path)
    bundle["validation"]["result"]["approved_count"] = 999
    bundle_path.write_text(json.dumps(bundle))
    result = public_replay(bundle_path)
    assert not result.success
    # Stored hash no longer matches stored content; the self-consistency check fires.
    assert any("validation" in i.lower() for i in result.issues)


def test_replay_detects_tampered_execution_result(tmp_path):
    bundle_path = _fresh_bundle(tmp_path)
    bundle = load_bundle(bundle_path)
    bundle["execution"]["result"]["triggered_rule_ids"] = ["r_fake"]
    bundle_path.write_text(json.dumps(bundle))
    result = public_replay(bundle_path)
    assert not result.success
    assert any("execution" in i.lower() for i in result.issues)


def test_replay_warns_on_domain_version_change_but_can_still_succeed(tmp_path):
    bundle_path = _fresh_bundle(tmp_path)
    bundle = load_bundle(bundle_path)
    bundle["domain"]["version"] = "9.9"  # claim a different version
    bundle_path.write_text(json.dumps(bundle))
    result = public_replay(bundle_path)
    # Inputs unchanged, results unchanged → replay still succeeds; but warns.
    assert result.success
    assert not result.domain_version_matches
    assert any("version" in w.lower() for w in result.warnings)


def test_replay_fails_when_domain_is_unknown(tmp_path):
    bundle_path = _fresh_bundle(tmp_path)
    bundle = load_bundle(bundle_path)
    bundle["domain"]["id"] = "no_such_domain"
    bundle_path.write_text(json.dumps(bundle))
    result = public_replay(bundle_path)
    assert not result.success
    assert any("no_such_domain" in i for i in result.issues)


# ----------------------------------------------------------------------
# inspect
# ----------------------------------------------------------------------

def test_inspect_returns_summary_without_executing(tmp_path):
    bundle_path = _fresh_bundle(tmp_path)
    summary = public_inspect(bundle_path)
    assert summary["bundle_version"] == BUNDLE_VERSION
    assert summary["framework_version"]
    assert summary["domain"]["id"] == "smart_home"
    assert summary["validation_summary"]["approved_count"] == 2
    assert summary["validation_summary"]["rejected_count"] == 1
    assert summary["execution_summary"]["triggered_rule_ids"]
    assert summary["input_hashes"]["constraints"].startswith("sha256:")


def test_inspect_does_not_mutate_bundle(tmp_path):
    bundle_path = _fresh_bundle(tmp_path)
    before = bundle_path.read_text()
    public_inspect(bundle_path)
    after = bundle_path.read_text()
    assert before == after


# ----------------------------------------------------------------------
# CLI integration
# ----------------------------------------------------------------------

def test_cli_review_with_bundle_writes_file(tmp_path, capsys):
    bundle_path = tmp_path / "review.json"
    exit_code = main([
        "review",
        str(EXAMPLES_SH / "constraints.yaml"),
        str(EXAMPLES_SH / "rules.yaml"),
        "--state", str(EXAMPLES_SH / "state.json"),
        "--bundle", str(bundle_path),
    ])
    assert exit_code == 0
    assert bundle_path.exists()
    bundle = json.loads(bundle_path.read_text())
    assert bundle["bundle_version"] == BUNDLE_VERSION
    err = capsys.readouterr().err
    assert "bundle written" in err.lower()


def test_cli_review_without_bundle_does_not_change_existing_output(tmp_path, capsys):
    # Existing review --json behavior must remain unchanged.
    exit_code = main([
        "review",
        str(EXAMPLES_SH / "constraints.yaml"),
        str(EXAMPLES_SH / "rules.yaml"),
        "--state", str(EXAMPLES_SH / "state.json"),
        "--json",
    ])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    # Schema is unchanged from Milestone 3+
    assert set(payload.keys()) >= {"schema_version", "proposals", "state", "validation", "execution"}


def test_cli_replay_passes_for_unchanged_bundle(tmp_path, capsys):
    bundle_path = _fresh_bundle(tmp_path)
    capsys.readouterr()
    exit_code = main(["replay", str(bundle_path)])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "PASSED" in out


def test_cli_replay_fails_after_tampering(tmp_path, capsys):
    bundle_path = _fresh_bundle(tmp_path)
    bundle = load_bundle(bundle_path)
    bundle["inputs"]["constraints"]["content"][0]["action"] = "tampered"
    bundle_path.write_text(json.dumps(bundle))
    capsys.readouterr()
    exit_code = main(["replay", str(bundle_path)])
    assert exit_code == 1
    out = capsys.readouterr().out
    assert "FAILED" in out


def test_cli_replay_json_output(tmp_path, capsys):
    bundle_path = _fresh_bundle(tmp_path)
    capsys.readouterr()
    exit_code = main(["replay", str(bundle_path), "--json"])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is True
    assert payload["inputs_intact"] is True
    assert payload["issues"] == []


def test_cli_inspect_outputs_summary(tmp_path, capsys):
    bundle_path = _fresh_bundle(tmp_path)
    capsys.readouterr()
    exit_code = main(["inspect", str(bundle_path)])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Bundle Inspect" in out
    assert "smart_home" in out
    assert "approved" in out.lower()


def test_cli_inspect_json_output(tmp_path, capsys):
    bundle_path = _fresh_bundle(tmp_path)
    capsys.readouterr()
    exit_code = main(["inspect", str(bundle_path), "--json"])
    assert exit_code == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["domain"]["id"] == "smart_home"
    assert "validation_summary" in summary


# ----------------------------------------------------------------------
# Network automation also supports bundles
# ----------------------------------------------------------------------

def test_network_automation_review_replay_chain(tmp_path):
    bundle_path = _fresh_bundle(tmp_path, network=True)
    bundle = load_bundle(bundle_path)
    assert bundle["domain"]["id"] == "network_automation"
    # The safe router config rule fired
    assert "r_apply_router_config_safely" in bundle["execution"]["result"]["triggered_rule_ids"]
    # And the unsafe rule was rejected
    rule_statuses = {r["id"]: r["status"] for r in bundle["validation"]["result"]["rules"]}
    assert rule_statuses["r_disable_mgmt_unsafe"] == "rejected"
    # Replay reproduces deterministically
    result = public_replay(bundle_path)
    assert result.success


def test_network_automation_replay_detects_tampered_state(tmp_path):
    bundle_path = _fresh_bundle(tmp_path, network=True)
    bundle = load_bundle(bundle_path)
    # Change mode away from maintenance — original safe rule will no longer fire
    bundle["inputs"]["state"]["content"]["mode"] = "normal"
    bundle_path.write_text(json.dumps(bundle))
    result = public_replay(bundle_path)
    assert not result.success


# ----------------------------------------------------------------------
# Public Python API surface
# ----------------------------------------------------------------------

def test_public_api_is_importable_from_top_level():
    from dtaifm import inspect_bundle, replay, review
    assert callable(review)
    assert callable(replay)
    assert callable(inspect_bundle)


def test_replay_does_not_invoke_any_provider_adapter(tmp_path, monkeypatch):
    # Force `import anthropic` to fail so any accidental adapter use would crash.
    import sys
    monkeypatch.setitem(sys.modules, "anthropic", None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    bundle_path = _fresh_bundle(tmp_path)
    result = public_replay(bundle_path)
    assert result.success
