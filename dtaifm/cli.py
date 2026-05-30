"""Command-line interface for dtaifm.

Commands:
  dtaifm schema <constraints|rules|state>          -- emit a JSON Schema
  dtaifm validate <constraints> <rules>            -- audit rules against constraints
  dtaifm propose <constraints> --teacher <name>    -- write a portable proposed rule file
                                  --out <file>
  dtaifm run <constraints> <rules> --state <file>  -- validate then execute one event
  dtaifm review <constraints> <rules>              -- combined audit (proposal + validation
                                  --state <file>      + execution + trace + final actions)

The runtime never receives rules that have not passed validation. This is the
architectural contract: AI proposes portable rule files; only deterministic
validation authorizes execution. The AI output is an artifact, not an action.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dtaifm.audit import (
    format_execution_json,
    format_execution_text,
    format_review_json,
    format_review_text,
    format_validation_json,
    format_validation_text,
)
from dtaifm.bundle import (
    build_bundle,
    format_inspect_text,
    format_replay_text,
    inspect_bundle,
    load_bundle,
    replay,
    review as bundle_review,
    save_bundle,
)
from dtaifm.domains.registry import get_domain, list_domains
from dtaifm.io import load_constraints, load_ruleset, load_state, write_ruleset
from dtaifm.runtimes.python_runtime import PythonRuntime
from dtaifm.schema import SCHEMA_VERSION, SCHEMAS
from dtaifm.student.validator import Validator
from dtaifm.serialize import ruleset_to_dict
from dtaifm.teacher.contract import PromptContext, TeacherRequest
from dtaifm.teacher.diagnostics import describe_all, format_teachers_text
from dtaifm.teacher.feedback import build_feedback
from dtaifm.teacher.prompt import render_teacher_prompt
from dtaifm.teacher.registry import available_teachers, get_teacher, teacher_is_registered


DEFAULT_DOMAIN = "smart_home"


# ----------------------------------------------------------------------
# schema
# ----------------------------------------------------------------------

def cmd_schema(args: argparse.Namespace) -> int:
    if args.kind not in SCHEMAS:
        print(
            f"Error: unknown schema kind '{args.kind}'. Available: {sorted(SCHEMAS)}",
            file=sys.stderr,
        )
        return 2
    print(json.dumps(SCHEMAS[args.kind], indent=2))
    return 0


# ----------------------------------------------------------------------
# validate
# ----------------------------------------------------------------------

def cmd_validate(args: argparse.Namespace) -> int:
    domain = get_domain(args.domain)
    constraints = load_constraints(Path(args.constraints))
    ruleset = load_ruleset(Path(args.rules))
    validator = Validator(constraints, domain=domain)
    result = validator.validate_ruleset(ruleset)

    if args.json:
        payload = {
            "schema_version": SCHEMA_VERSION,
            **format_validation_json(ruleset, result, constraints),
        }
        print(json.dumps(payload, indent=2))
    else:
        print(format_validation_text(ruleset, result, constraints))

    return 0 if result.all_approved else 1


# ----------------------------------------------------------------------
# propose
# ----------------------------------------------------------------------

def cmd_propose(args: argparse.Namespace) -> int:
    domain = get_domain(args.domain)
    constraints = load_constraints(Path(args.constraints))
    teacher = get_teacher(
        args.teacher,
        model=args.model,
        base_url=args.teacher_base_url,
        timeout=args.teacher_timeout,
    )
    request = TeacherRequest(
        constraints=constraints,
        context=PromptContext(domain=args.domain),
        domain=domain,
    )
    response = teacher.propose(request)
    ruleset = response.ruleset

    proposal_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for rule in ruleset:
        rule.proposed_by = args.teacher
        rule.proposal_id = proposal_id
        rule.created_at = created_at

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_ruleset(ruleset, out_path)

    # The propose command only writes the artifact. It does not validate or execute.
    # Chain with `dtaifm validate` or `dtaifm review` to enter the deterministic gate.
    print(f"Proposed {len(ruleset)} rule(s) using teacher '{args.teacher}'.")
    print(f"Proposal ID: {proposal_id}")
    print(f"Created at:  {created_at}")
    print(f"Wrote to:    {out_path}")
    return 0


# ----------------------------------------------------------------------
# prompt
# ----------------------------------------------------------------------

def cmd_prompt(args: argparse.Namespace) -> int:
    # Validate the teacher name without instantiating it. Construction of provider
    # adapters can require API keys; the prompt command needs neither network nor
    # credentials — it just shows the input a real adapter would receive.
    if not teacher_is_registered(args.teacher):
        print(
            f"Error: Unknown teacher '{args.teacher}'. Available: {available_teachers()}",
            file=sys.stderr,
        )
        return 2
    domain = get_domain(args.domain)
    constraints = load_constraints(Path(args.constraints))
    request = TeacherRequest(
        constraints=constraints,
        context=PromptContext(domain=args.domain),
        domain=domain,
    )
    print(render_teacher_prompt(request))
    return 0


# ----------------------------------------------------------------------
# run
# ----------------------------------------------------------------------

def cmd_run(args: argparse.Namespace) -> int:
    domain = get_domain(args.domain)
    constraints = load_constraints(Path(args.constraints))
    ruleset = load_ruleset(Path(args.rules))
    state_data = load_state(Path(args.state))

    validator = Validator(constraints, domain=domain)
    validation = validator.validate_ruleset(ruleset)

    approved_ids = set(validation.approved)
    approved_rules = [r for r in ruleset if r.id in approved_ids]

    event = state_data["event"]
    runtime_state = {
        "time": _parse_time(state_data.get("time")),
        "mode": state_data.get("mode", "normal"),
        **state_data.get("devices", {}),
    }

    runtime = PythonRuntime(approved_rules, domain=domain)
    execution = runtime.fire(event["device"], event["type"], runtime_state)

    if args.json:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "validation": format_validation_json(ruleset, validation, constraints),
            "execution": format_execution_json(execution, event["device"], event["type"]),
        }
        print(json.dumps(payload, indent=2))
    else:
        print(format_validation_text(ruleset, validation, constraints))
        print()
        print(format_execution_text(execution, event["device"], event["type"]))

    return 0


# ----------------------------------------------------------------------
# review
# ----------------------------------------------------------------------

def cmd_review(args: argparse.Namespace) -> int:
    domain = get_domain(args.domain)
    constraints = load_constraints(Path(args.constraints))
    ruleset = load_ruleset(Path(args.rules))
    state_data = load_state(Path(args.state))
    # Inject wall-clock time when the state file omits it so an emitted bundle
    # is deterministically replayable. Existing tests pass time explicitly.
    if "time" not in state_data or not state_data.get("time"):
        from datetime import datetime, timezone
        state_data = {**state_data, "time": datetime.now(timezone.utc).isoformat(timespec="seconds")}

    validator = Validator(constraints, domain=domain)
    validation = validator.validate_ruleset(ruleset)

    approved_ids = set(validation.approved)
    approved_rules = [r for r in ruleset if r.id in approved_ids]

    event = state_data["event"]
    runtime_state = {
        "time": _parse_time(state_data.get("time")),
        "mode": state_data.get("mode", "normal"),
        **state_data.get("devices", {}),
    }
    runtime = PythonRuntime(approved_rules, domain=domain)
    execution = runtime.fire(event["device"], event["type"], runtime_state)

    if args.json:
        payload = format_review_json(
            ruleset, constraints, validation, execution,
            event["device"], event["type"], state_data,
        )
        print(json.dumps(payload, indent=2))
    else:
        print(format_review_text(
            ruleset, constraints, validation, execution,
            event["device"], event["type"], state_data,
        ))

    if args.bundle:
        bundle = build_bundle(
            domain=domain,
            constraints_path=Path(args.constraints),
            rules_path=Path(args.rules),
            state_path=Path(args.state),
            constraints=constraints,
            ruleset=ruleset,
            state_data=state_data,
            validation=validation,
            execution=execution,
            event_device=event["device"],
            event_type=event["type"],
        )
        save_bundle(bundle, Path(args.bundle))
        print(f"\nAudit bundle written to: {args.bundle}", file=sys.stderr)

    return 0


# ----------------------------------------------------------------------
# replay
# ----------------------------------------------------------------------

def cmd_replay(args: argparse.Namespace) -> int:
    bundle_path = Path(args.bundle)
    bundle = load_bundle(bundle_path)
    result = replay(bundle)
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(format_replay_text(result, bundle_source=str(bundle_path)))
    return 0 if result.success else 1


# ----------------------------------------------------------------------
# inspect
# ----------------------------------------------------------------------

def cmd_inspect(args: argparse.Namespace) -> int:
    bundle = load_bundle(Path(args.bundle))
    summary = inspect_bundle(bundle)
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(format_inspect_text(summary))
    return 0


# ----------------------------------------------------------------------
# feedback
# ----------------------------------------------------------------------

def cmd_feedback(args: argparse.Namespace) -> int:
    """Validate rules and write a deterministic feedback artifact. NO execution."""
    domain = get_domain(args.domain)
    constraints = load_constraints(Path(args.constraints))
    ruleset = load_ruleset(Path(args.rules))
    feedback = build_feedback(ruleset, constraints, domain)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(feedback.to_dict(), indent=2), encoding="utf-8")

    print(f"Wrote feedback to: {out_path}")
    print(f"Domain:    {feedback.domain['id']} v{feedback.domain['version']}")
    print(f"Total rules: {len(ruleset)}")
    print(f"Approved:    {len(feedback.approved_rule_ids)}")
    print(f"Rejected:    {len(feedback.rejected_rules)}")
    for rec in feedback.rejected_rules:
        print(f"  - {rec.rule_id} ({len(rec.violations)} violation(s))")
    return 0


# ----------------------------------------------------------------------
# repropose
# ----------------------------------------------------------------------

def cmd_repropose(args: argparse.Namespace) -> int:
    """Validate originals, hand deterministic feedback to the teacher, write a revised artifact.

    The revised rules are NOT validated or executed inside this command — only
    `dtaifm review` (or `dtaifm validate`) authorizes execution.
    """
    domain = get_domain(args.domain)
    constraints = load_constraints(Path(args.constraints))
    ruleset = load_ruleset(Path(args.rules))

    # 1. Deterministic feedback (validator only — no runtime)
    feedback = build_feedback(ruleset, constraints, domain)

    # 2. Original rules as canonical dicts so the prompt can show them verbatim
    previous_rules = ruleset_to_dict(ruleset)["rules"]

    # 3. Teacher call (HTTP or mock); the teacher MUST return a complete revised RuleSet
    teacher = get_teacher(
        args.teacher,
        model=args.model,
        base_url=args.teacher_base_url,
        timeout=args.teacher_timeout,
    )
    request = TeacherRequest(
        constraints=constraints,
        context=PromptContext(domain=args.domain),
        domain=domain,
        feedback=feedback,
        previous_rules=previous_rules,
    )
    response = teacher.propose(request)
    revised_ruleset = response.ruleset

    # 4. Stamp fresh provenance — a revision is a new proposal
    proposal_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for rule in revised_ruleset:
        rule.proposed_by = args.teacher
        rule.proposal_id = proposal_id
        rule.created_at = created_at

    # 5. Write the revised artifact only — no validation, no execution
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_ruleset(revised_ruleset, out_path)

    print(f"Reproposed {len(revised_ruleset)} rule(s) using teacher '{args.teacher}'.")
    print(f"Original:    {len(ruleset)} rule(s); rejected: {len(feedback.rejected_rules)}")
    print(f"Proposal ID: {proposal_id}")
    print(f"Created at:  {created_at}")
    print(f"Wrote to:    {out_path}")
    print(f"\nNext step:   dtaifm review {args.constraints} {out_path} --state <state.json> --domain {args.domain}", file=sys.stderr)
    return 0


# ----------------------------------------------------------------------
# demo — launch-grade walkthrough
# ----------------------------------------------------------------------

def cmd_demo(args: argparse.Namespace) -> int:
    """Run the full pipeline (propose -> review -> bundle -> replay) end to end."""
    import shutil
    import tempfile

    domain_id: str = args.domain_id

    # Verify the domain exists FIRST so the error is clear regardless of file paths.
    domain = get_domain(domain_id)

    tmp_dir = Path(tempfile.mkdtemp(prefix="dtaifm-demo-"))

    # Resolve constraints + state — either user-provided or built-in fixtures.
    if args.constraints and args.state:
        constraints_path = Path(args.constraints)
        state_path = Path(args.state)
    else:
        materialized = _materialize_builtin_demo(domain_id, tmp_dir)
        if materialized is None:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            print(
                f"Error: domain '{domain_id}' has no built-in demo fixtures. "
                f"Pass --constraints and --state to demo a custom domain.",
                file=sys.stderr,
            )
            return 2
        constraints_path, state_path = materialized

    # Step 1: teacher proposes
    teacher = get_teacher(
        args.teacher,
        model=args.model,
        base_url=args.teacher_base_url,
        timeout=args.teacher_timeout,
    )
    constraints = load_constraints(constraints_path)
    request = TeacherRequest(
        constraints=constraints,
        context=PromptContext(domain=domain_id),
        domain=domain,
    )
    response = teacher.propose(request)
    proposed_ruleset = response.ruleset

    # Stamp provenance and write the proposed artifact
    proposal_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for rule in proposed_ruleset:
        rule.proposed_by = args.teacher
        rule.proposal_id = proposal_id
        rule.created_at = created_at
    proposed_path = tmp_dir / "proposed.yaml"
    write_ruleset(proposed_ruleset, proposed_path)

    # Steps 2-4: review, write bundle
    bundle_path = tmp_dir / "review.json"
    bundle = bundle_review(
        constraints_path=constraints_path,
        rules_path=proposed_path,
        state_path=state_path,
        domain_id=domain_id,
        bundle_path=bundle_path,
    )

    # Step 5: replay
    replay_result = replay(bundle_path)

    # Emit
    if args.json:
        print(json.dumps(
            _demo_json_payload(
                domain_id, args.teacher,
                proposed_path, bundle_path,
                proposed_ruleset, bundle, replay_result,
            ),
            indent=2,
        ))
    else:
        print(_format_demo_text(
            domain_id, args.teacher,
            proposed_path, bundle_path,
            proposed_ruleset, bundle, replay_result,
        ))

    return 0 if replay_result.success else 1


def _materialize_builtin_demo(domain_id: str, tmp_dir: Path):
    """Copy packaged demo fixtures for `domain_id` into tmp_dir; return (constraints, state) paths."""
    from importlib import resources

    try:
        pkg = resources.files(f"dtaifm._demo.{domain_id}")
    except (ModuleNotFoundError, AttributeError):
        return None

    constraints_resource = pkg / "constraints.yaml"
    state_resource = pkg / "state.json"
    if not constraints_resource.is_file() or not state_resource.is_file():
        return None

    constraints_path = tmp_dir / "constraints.yaml"
    state_path = tmp_dir / "state.json"
    constraints_path.write_text(constraints_resource.read_text(encoding="utf-8"), encoding="utf-8")
    state_path.write_text(state_resource.read_text(encoding="utf-8"), encoding="utf-8")
    return constraints_path, state_path


def _demo_json_payload(domain_id, teacher_name, proposed_path, bundle_path,
                       proposed_ruleset, bundle, replay_result):
    val = bundle["validation"]["result"]
    exe = bundle["execution"]["result"]
    return {
        "domain": domain_id,
        "teacher": teacher_name,
        "proposed_rule_count": len(proposed_ruleset),
        "approved_count": val["approved_count"],
        "rejected_count": val["rejected_count"],
        "triggered_rule_ids": list(exe["triggered_rule_ids"]),
        "actions_taken": list(exe["actions_taken"]),
        "proposed_path": str(proposed_path),
        "bundle_path": str(bundle_path),
        "replay": {
            "success": replay_result.success,
            "inputs_intact": replay_result.inputs_intact,
            "validation_matches": replay_result.validation_matches,
            "execution_matches": replay_result.execution_matches,
            "domain_version_matches": replay_result.domain_version_matches,
            "issues": list(replay_result.issues),
            "warnings": list(replay_result.warnings),
        },
    }


def _format_demo_text(domain_id, teacher_name, proposed_path, bundle_path,
                      proposed_ruleset, bundle, replay_result):
    val = bundle["validation"]["result"]
    exe = bundle["execution"]["result"]
    event = exe["event"]

    lines: list[str] = []
    bar = "=" * 72
    lines.extend([
        bar,
        f"  dtaifm demo  -  {domain_id} domain  (teacher: {teacher_name})",
        bar,
        "",
        "Step 1/5  Teacher proposes candidate rules",
        f"  {teacher_name} proposed {len(proposed_ruleset)} rule(s).",
        f"  Wrote: {proposed_path}",
        "",
        "Step 2/5  Deterministic validator reviews the rules",
        f"  Approved: {val['approved_count']}",
        f"  Rejected: {val['rejected_count']}",
    ])

    for rule_info in val.get("rules", []):
        if rule_info["status"] == "rejected":
            lines.append(f"    - {rule_info['id']}  \"{rule_info['name']}\"")
            for v in rule_info["violations"]:
                lines.append(f"        ! [{v['constraint_id']}] {v['reason']}")

    lines.extend([
        "",
        "Step 3/5  Runtime executes ONLY approved rules",
        f"  Event: {event['device']}.{event['type']}",
    ])
    if exe["triggered_rule_ids"]:
        for action in exe["actions_taken"]:
            params = action.get("parameters") or {}
            extra = f"  {params}" if params else ""
            lines.append(f"  Fired: {action['rule_id']}")
            lines.append(f"    -> {action['device']}.{action['action']}{extra}")
    else:
        lines.append("  No rules triggered (event did not match any approved rule).")

    lines.extend([
        "",
        "Step 4/5  Audit bundle written",
        f"  Wrote: {bundle_path}",
        "  Hashes:",
        f"    constraints  {bundle['inputs']['constraints']['hash']}",
        f"    rules        {bundle['inputs']['rules']['hash']}",
        f"    state        {bundle['inputs']['state']['hash']}",
        f"    validation   {bundle['validation']['hash']}",
        f"    execution    {bundle['execution']['hash']}",
        "",
        "Step 5/5  Replay verifies deterministic reproducibility",
        f"  Inputs intact:           {'OK' if replay_result.inputs_intact else 'FAILED'}",
        f"  Validation matches:      {'OK' if replay_result.validation_matches else 'FAILED'}",
        f"  Execution matches:       {'OK' if replay_result.execution_matches else 'FAILED'}",
        f"  Domain version matches:  {'OK' if replay_result.domain_version_matches else 'DIFFERS'}",
        "",
    ])

    if replay_result.success:
        lines.extend([
            "RESULT: PASSED - The deterministic trust boundary held end to end.",
            "",
            "What you just saw:",
            "  - The teacher proposed candidate rules; the validator approved or rejected each.",
            "  - The runtime executed ONLY the approved rules.",
            "  - The whole audit was written to a portable bundle.",
            "  - Replay re-ran the pipeline from the bundle's inputs and confirmed every hash matches.",
            "",
            "Next:",
            f"  dtaifm inspect {bundle_path}",
            f"  dtaifm replay  {bundle_path}",
        ])
    else:
        lines.append("RESULT: FAILED - replay could not reproduce the original review.")
        for issue in replay_result.issues:
            lines.append(f"  ! {issue}")

    return "\n".join(lines)


# ----------------------------------------------------------------------
# teachers
# ----------------------------------------------------------------------

def cmd_teachers(args: argparse.Namespace) -> int:
    infos = describe_all(check=args.check)
    if args.json:
        print(json.dumps(infos, indent=2))
    else:
        print(format_teachers_text(infos))
    return 0


# ----------------------------------------------------------------------
# helpers + parser
# ----------------------------------------------------------------------

def _parse_time(value) -> datetime:
    if value is None:
        return datetime.now()
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def _add_domain_module_argument(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument(
        "--domain-module",
        default=None,
        metavar="PKG.MODULE",
        help=(
            "Import this module before resolving the domain so a custom or "
            "not-yet-installed domain pack registers itself (the module must call "
            "register_domain() at import). Installed packs are auto-discovered via "
            "the 'dtaifm.domains' entry-point group and need no flag."
        ),
    )


def _add_domain_argument(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument(
        "--domain",
        default=DEFAULT_DOMAIN,
        help=f"Domain id (default: {DEFAULT_DOMAIN}; available: {', '.join(list_domains())})",
    )
    _add_domain_module_argument(subparser)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dtaifm",
        description="Deterministic-first Teaching AI Framework Middleware",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_schema = subparsers.add_parser(
        "schema",
        help="Emit a JSON Schema for one of the portable file kinds.",
    )
    p_schema.add_argument("kind", choices=sorted(SCHEMAS), help="Which schema to emit")
    p_schema.set_defaults(func=cmd_schema)

    p_validate = subparsers.add_parser(
        "validate",
        help="Validate a rule file against a constraint file and print an audit report.",
    )
    p_validate.add_argument("constraints", help="Path to constraints file (.yaml/.json)")
    p_validate.add_argument("rules", help="Path to rules file (.yaml/.json)")
    p_validate.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    _add_domain_argument(p_validate)
    p_validate.set_defaults(func=cmd_validate)

    p_propose = subparsers.add_parser(
        "propose",
        help="Run a teacher and write a portable proposed rule file. Does not validate or execute.",
    )
    p_propose.add_argument("constraints", help="Path to constraints file (.yaml/.json)")
    p_propose.add_argument(
        "--teacher",
        required=True,
        help=f"Teacher name (available: {', '.join(available_teachers())})",
    )
    p_propose.add_argument("--out", required=True, help="Output path (.yaml/.yml/.json)")
    p_propose.add_argument(
        "--teacher-base-url",
        default=None,
        help=(
            "Base URL for HTTP teachers (ollama, lemonade). "
            "Override order: this flag > env var > default. Trailing slash is normalized."
        ),
    )
    p_propose.add_argument(
        "--model",
        default=None,
        help="Model identifier passed to the teacher (e.g. 'llama3.2', 'Qwen3-0.6B-GGUF', 'claude-sonnet-4-6', 'gpt-5.5').",
    )
    p_propose.add_argument(
        "--teacher-timeout",
        type=float,
        default=None,
        help=(
            "HTTP timeout in seconds for local-HTTP teachers (ollama, lemonade). "
            "Override order: this flag > DTAIFM_HTTP_TIMEOUT env var > adapter default (60s). "
            "Raise it for thinking models whose reasoning phase eats into the budget."
        ),
    )
    _add_domain_argument(p_propose)
    p_propose.set_defaults(func=cmd_propose)

    p_prompt = subparsers.add_parser(
        "prompt",
        help="Show the exact prompt a teacher adapter would receive. Requires no API key.",
    )
    p_prompt.add_argument("constraints", help="Path to constraints file (.yaml/.json)")
    p_prompt.add_argument(
        "--teacher",
        required=True,
        help=f"Teacher name (available: {', '.join(available_teachers())})",
    )
    _add_domain_argument(p_prompt)
    p_prompt.set_defaults(func=cmd_prompt)

    p_run = subparsers.add_parser(
        "run",
        help="Validate a rule file then execute approved rules against a state event.",
    )
    p_run.add_argument("constraints", help="Path to constraints file (.yaml/.json)")
    p_run.add_argument("rules", help="Path to rules file (.yaml/.json)")
    p_run.add_argument("--state", required=True, help="Path to state file (.json/.yaml) with event + system state")
    p_run.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    _add_domain_argument(p_run)
    p_run.set_defaults(func=cmd_run)

    p_review = subparsers.add_parser(
        "review",
        help="Full audit: proposal metadata + validation + execution trace + final actions.",
    )
    p_review.add_argument("constraints", help="Path to constraints file (.yaml/.json)")
    p_review.add_argument("rules", help="Path to rules file (.yaml/.json)")
    p_review.add_argument("--state", required=True, help="Path to state file (.json/.yaml)")
    p_review.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    p_review.add_argument(
        "--bundle",
        default=None,
        help="Optional path to write a portable, replayable audit bundle (.dtaifm-review.json)",
    )
    _add_domain_argument(p_review)
    p_review.set_defaults(func=cmd_review)

    p_replay = subparsers.add_parser(
        "replay",
        help="Replay a bundle and verify deterministic reproducibility.",
    )
    p_replay.add_argument("bundle", help="Path to .dtaifm-review.json")
    p_replay.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    _add_domain_module_argument(p_replay)
    p_replay.set_defaults(func=cmd_replay)

    p_inspect = subparsers.add_parser(
        "inspect",
        help="Read-only summary of a bundle. Does not execute anything.",
    )
    p_inspect.add_argument("bundle", help="Path to .dtaifm-review.json")
    p_inspect.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    p_inspect.set_defaults(func=cmd_inspect)

    p_demo = subparsers.add_parser(
        "demo",
        help="Launch demo: propose -> review -> bundle -> replay (60 seconds, fully offline by default).",
    )
    p_demo.add_argument(
        "domain_id",
        metavar="DOMAIN",
        help=(
            "Domain to demo. Built-in: smart_home, network_automation. "
            "For custom domains, also pass --constraints and --state."
        ),
    )
    p_demo.add_argument(
        "--teacher",
        default="mock",
        help="Teacher to use (default: mock — offline, no API key required).",
    )
    p_demo.add_argument(
        "--teacher-base-url",
        default=None,
        help="Base URL for HTTP teachers (ollama, lemonade). CLI > env > default.",
    )
    p_demo.add_argument(
        "--model",
        default=None,
        help="Model identifier passed to the teacher.",
    )
    p_demo.add_argument(
        "--teacher-timeout",
        type=float,
        default=None,
        help=(
            "HTTP timeout in seconds for local-HTTP teachers (ollama, lemonade). "
            "Override order: this flag > DTAIFM_HTTP_TIMEOUT env var > adapter default (60s). "
            "Raise it for thinking models that take longer than 60s end to end."
        ),
    )
    p_demo.add_argument(
        "--constraints",
        default=None,
        help="Override constraints file (required for non-built-in domains).",
    )
    p_demo.add_argument(
        "--state",
        default=None,
        help="Override state file (required for non-built-in domains).",
    )
    p_demo.add_argument("--json", action="store_true", help="Emit machine-readable JSON instead of the walkthrough.")
    _add_domain_module_argument(p_demo)
    p_demo.set_defaults(func=cmd_demo)

    p_teachers = subparsers.add_parser(
        "teachers",
        help="List registered teachers; --check pings local endpoints (offline servers reported gracefully).",
    )
    p_teachers.add_argument("--check", action="store_true", help="Ping local HTTP teacher endpoints")
    p_teachers.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    p_teachers.set_defaults(func=cmd_teachers)

    p_feedback = subparsers.add_parser(
        "feedback",
        help="Validate rules and write a deterministic feedback artifact. Does NOT execute.",
    )
    p_feedback.add_argument("constraints", help="Path to constraints file (.yaml/.json)")
    p_feedback.add_argument("rules", help="Path to rules file (.yaml/.json)")
    p_feedback.add_argument("--out", required=True, help="Output path for the feedback JSON")
    _add_domain_argument(p_feedback)
    p_feedback.set_defaults(func=cmd_feedback)

    p_repropose = subparsers.add_parser(
        "repropose",
        help="Validate originals, hand deterministic feedback to a teacher, write a revised rule file.",
    )
    p_repropose.add_argument("constraints", help="Path to constraints file (.yaml/.json)")
    p_repropose.add_argument("rules", help="Path to the rules file being revised")
    p_repropose.add_argument(
        "--teacher",
        required=True,
        help=f"Teacher name (available: {', '.join(available_teachers())})",
    )
    p_repropose.add_argument("--out", required=True, help="Output path for the revised rules (.yaml/.yml/.json)")
    p_repropose.add_argument(
        "--teacher-base-url",
        default=None,
        help="Base URL for HTTP teachers. Override order: this flag > env var > default.",
    )
    p_repropose.add_argument(
        "--model",
        default=None,
        help="Model identifier passed to the teacher.",
    )
    p_repropose.add_argument(
        "--teacher-timeout",
        type=float,
        default=None,
        help=(
            "HTTP timeout in seconds for local-HTTP teachers (ollama, lemonade). "
            "Override order: this flag > DTAIFM_HTTP_TIMEOUT env var > adapter default (60s)."
        ),
    )
    _add_domain_argument(p_repropose)
    p_repropose.set_defaults(func=cmd_repropose)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    domain_module = getattr(args, "domain_module", None)
    if domain_module:
        import importlib
        try:
            importlib.import_module(domain_module)
        except Exception as exc:  # noqa: BLE001 - a bad user module must not dump a traceback
            print(f"Error: failed to load --domain-module '{domain_module}': {exc}", file=sys.stderr)
            return 2
    try:
        return args.func(args)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except ImportError as exc:
        # Optional provider extra (e.g. anthropic) not installed.
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        # Adapter prerequisite missing at runtime (e.g. ANTHROPIC_API_KEY).
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except (ValueError, KeyError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
