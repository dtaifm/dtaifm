# The reproposal loop

> The deterministic layer may teach the teacher, but it never lets the teacher grade itself.

Teachers rarely produce a perfect first proposal. The reproposal loop lets any teacher (mock, Anthropic, Ollama, Lemonade, custom) consume the validator's deterministic violation reasons and try again — without weakening the trust boundary.

## The loop

```
1. propose      teacher writes v1.yaml
2. feedback     validator inspects v1.yaml and writes feedback.json (no execution)
3. repropose    teacher receives v1 + feedback, writes v2.yaml (no validation, no execution)
4. review       validator + runtime gate v2.yaml (this is where execution can happen)
```

Steps 1–3 never execute anything. Only step 4 is authorized to run actions.

## End to end

```bash
# 1. Initial proposal
dtaifm propose examples/smart_rules/constraints.yaml \
  --teacher ollama --out v1.yaml

# 2. Inspect what failed (validator only — no execution)
dtaifm feedback examples/smart_rules/constraints.yaml v1.yaml --out feedback.json

# 3. Repropose: the teacher sees the previous rules + the named violations
dtaifm repropose examples/smart_rules/constraints.yaml v1.yaml \
  --teacher ollama --out v2.yaml

# 4. Run a real review on the revised file
dtaifm review examples/smart_rules/constraints.yaml v2.yaml \
  --state examples/smart_rules/state.json --bundle review.json
```

## What `feedback` produces

```json
{
  "schema_version": "0.1",
  "domain": {"id": "smart_home", "version": "0.1"},
  "approved_rule_ids": ["r_motion_night_light", "r_heating_cold"],
  "rejected_rules": [
    {
      "rule_id": "r_auto_unlock_door",
      "name": "Auto-Unlock on Arrival (UNSAFE)",
      "violations": [
        {
          "constraint_id": "no_auto_unlock",
          "constraint_description": "Never unlock doors automatically.",
          "reason": "Rule 'r_auto_unlock_door' performs prohibited action 'unlock' on device 'front_door'."
        }
      ],
      "allowed_triggers": ["motion_detected", "user_arrived", "..."],
      "allowed_conditions": ["time_range", "mode_not", "mode_is", "device_state"],
      "allowed_actions": ["turn_on", "turn_off", "lock", "unlock", "..."]
    }
  ]
}
```

Each rejected rule carries the deterministic violation reasons verbatim plus the domain vocabulary. This is the contract the teacher reasons about.

## What `repropose` sends to the teacher

The teacher receives a `TeacherRequest` with:

- `constraints` — the same hard constraints as on a first proposal
- `domain` — the active domain (vocabulary + version)
- `previous_rules` — the original rules as canonical dicts
- `feedback` — the `TeacherFeedback` produced in step 2

The shared prompt template renders a stable, grep-able `REVISION REQUESTED` section listing:

- The teacher's previous rules (trigger, actions, satisfies_constraints)
- The rejected rules with per-rule violations and allowed vocabulary
- An explicit instruction to return a complete revised RuleSet

## What `repropose` does NOT do

- It does **not** validate the revised file.
- It does **not** execute anything.
- It does **not** treat the teacher's revision as approved.

Even if the teacher returns an unsafe revised rule, `repropose` writes it. Only `dtaifm review` or `dtaifm validate` gates execution. This is by design: the framework never lets a teacher grade its own work.

## Verifying the loop

Tests in `tests/test_feedback_repropose.py` lock this behavior:

- `test_cli_feedback_does_not_invoke_runtime` — spies on `PythonRuntime.__init__`, asserts zero instances during `dtaifm feedback`.
- `test_cli_repropose_validates_original_but_not_revised` — patches `Validator.validate_ruleset`, asserts it is called exactly once (the original).
- `test_cli_repropose_does_not_execute_runtime` — same spy as above, applied to `dtaifm repropose`.
- `test_cli_repropose_writes_unsafe_teacher_output_without_validation` — registers a teacher that returns an unsafe revision; `repropose` writes it; a subsequent `dtaifm validate` catches it (exit 1).

## Public Python API

```python
from dtaifm.teacher import build_feedback, TeacherFeedback
from dtaifm.io import load_constraints, load_ruleset
from dtaifm.domains.registry import get_domain

constraints = load_constraints("constraints.yaml")
ruleset = load_ruleset("rules.yaml")
domain = get_domain("smart_home")

feedback: TeacherFeedback = build_feedback(ruleset, constraints, domain)
# build_feedback runs the validator only — never the runtime.
```

`TeacherFeedback` is the same type that travels in `TeacherRequest.feedback`, so a Python caller can drive the entire loop without the CLI.
