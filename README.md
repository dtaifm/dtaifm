# dtaifm — Deterministic-first Teaching AI Framework Middleware

[![tests](https://github.com/dtaifm/dtaifm/actions/workflows/tests.yml/badge.svg)](https://github.com/dtaifm/dtaifm/actions/workflows/tests.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.1.0-blue.svg)](CHANGELOG.md)
[![Tests passing](https://img.shields.io/badge/tests-268%20passing-brightgreen.svg)](tests/)

**AI proposes. The deterministic layer disposes. AI output is an artifact, not an action.**

dtaifm is open-source middleware for systems where AI generates candidate logic (rules, configurations, strategies) and a deterministic, constraint-verified layer has the final say. No AI output executes until it passes a human-defined constraint check.

> **What dtaifm is not.** dtaifm is **not** a smart-home product or a network-automation product. `smart_home` and `network_automation` are domain packs that ship in the box to demonstrate the pattern. The framework itself is provider-agnostic (mock, Anthropic, Ollama, Lemonade, bring-your-own) and domain-agnostic (bring your own — see [`examples/custom_domain_template/`](examples/custom_domain_template/)).

All file formats are explicitly versioned (`schema_version`) and have published JSON Schemas, so producers and consumers can evolve independently.

## 60-second demo

```bash
pip install -e ".[dev]"
dtaifm demo smart_home
```

That single command walks the entire pipeline — `propose → validate → execute → bundle → replay` — and prints a step-by-step report ending in `RESULT: PASSED`. Runs fully offline using the mock teacher; no API key needed.

Want to see the second built-in domain or a local LLM driving it?

```bash
dtaifm demo network_automation                                  # second built-in domain
dtaifm demo smart_home --teacher ollama --model llama3.2        # local model via Ollama
dtaifm demo smart_home --teacher lemonade --teacher-base-url http://192.0.2.10:13305 --model Qwen3-0.6B-GGUF
dtaifm demo smart_home --json                                   # machine-readable
```

The demo leaves the proposed rules, the audit bundle, and the hashes in a temp dir so you can `dtaifm inspect` / `dtaifm replay` them afterward.

## Documentation

| Doc | What it covers |
|---|---|
| [docs/launch.md](docs/launch.md) | The pitch, what's in v0.1, where it fits and does not fit |
| [docs/quickstart.md](docs/quickstart.md) | Install, run the demo, exercise every CLI command |
| [docs/concepts.md](docs/concepts.md) | Three-layer architecture, trust boundary, core primitives |
| [docs/domains.md](docs/domains.md) | Built-in domain packs + how to write your own |
| [docs/local-teachers.md](docs/local-teachers.md) | Ollama and Lemonade adapters, configuration, diagnostics |
| [docs/audit-bundles.md](docs/audit-bundles.md) | `.dtaifm-review.json`, replay, tamper detection |
| [docs/reproposal-loop.md](docs/reproposal-loop.md) | Validator → feedback → teacher revision cycle |
| [docs/comparison.md](docs/comparison.md) | Where dtaifm fits vs LLM agents, workflow engines, guardrails, policy engines, orchestration |
| [docs/roadmap.md](docs/roadmap.md) | What shipped in v0.1; near-term and longer-term plans |
| [docs/release-checklist.md](docs/release-checklist.md) | Maintainer pre-release checklist |

For contributors: [CONTRIBUTING.md](CONTRIBUTING.md), [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md), [SECURITY.md](SECURITY.md), [CHANGELOG.md](CHANGELOG.md).

## Why

Raw LLMs in production systems hallucinate. They are unpredictable at edge cases. Calling them on every user action is slow and expensive. dtaifm decouples the *intelligence* (the AI teacher) from the *execution* (the deterministic student) so you get AI-level optimization with deterministic-level safety and auditability.

## Architecture

```
  Constraints (YAML)           ← defined by humans; never changed by AI
        │
        ▼
  Teacher.propose_rules()      ← AI model or mock; returns a candidate RuleSet
        │
        ▼
  Validator.validate_ruleset() ← deterministic; approves or rejects each rule
        │
        ▼
  PythonRuntime.fire()         ← executes approved rules only; predictable, auditable
```

Three layers, one contract: **the AI never executes anything directly.**

## Quickstart

```bash
git clone <repo-url>
cd dtaifm
pip install -e ".[dev]"

# Run the smart home demo (Python script)
python examples/smart_rules/demo.py

# Run the test suite
pytest
```

## CLI

```bash
# Emit a JSON Schema for one of the portable file kinds
dtaifm schema constraints
dtaifm schema rules
dtaifm schema state

# Run a teacher and write a portable proposed rule file (does NOT validate or execute)
dtaifm propose examples/smart_rules/constraints.yaml --teacher mock --out proposed.yaml

# Audit a rule file against a constraint file (exit 1 if any rule is rejected)
dtaifm validate examples/smart_rules/constraints.yaml examples/smart_rules/rules.yaml

# Validate, then execute approved rules against a state event
dtaifm run examples/smart_rules/constraints.yaml examples/smart_rules/rules.yaml \
  --state examples/smart_rules/state.json

# Combined audit: proposal metadata + validation + execution trace + final actions
dtaifm review examples/smart_rules/constraints.yaml proposed.yaml \
  --state examples/smart_rules/state.json --json

# Write a portable audit bundle alongside the review
dtaifm review examples/smart_rules/constraints.yaml proposed.yaml \
  --state examples/smart_rules/state.json --bundle review.json

# Replay a bundle and verify it reproduces exactly (exit 1 on mismatch)
dtaifm replay review.json

# Read-only summary of a bundle — no execution
dtaifm inspect review.json

# Build a deterministic feedback artifact from validation failures (NO execution)
dtaifm feedback constraints.yaml rules.yaml --out feedback.json

# Hand the deterministic feedback to a teacher and write a revised rule file
# (the revised file is NOT validated or executed by repropose — only review/validate does that)
dtaifm repropose constraints.yaml rules.yaml --teacher mock --out revised.yaml
```

`--json` is available on `validate`, `run`, `review`, `replay`, and `inspect`. If the `dtaifm` entry point isn't on your PATH after install, use `python -m dtaifm ...` instead.

## Audit Bundles & Replay

`dtaifm review --bundle review.json` writes a self-contained audit artifact embedding the constraints, rules, state, validation result, and execution trace, with **SHA-256 hashes** over the canonical-JSON form of each. The bundle is portable across machines and survives YAML/JSON formatting differences.

`dtaifm replay review.json` re-executes the review on a fresh checkout and verifies:

1. Embedded inputs match their recorded hashes (catches input tampering).
2. Stored validation/execution results match their recorded hashes (catches result tampering).
3. Recomputed validation/execution from inputs match the stored hashes (catches framework non-determinism or domain semantic drift).

A domain-version mismatch becomes a **warning** rather than a failure when results still match (a non-breaking domain change). Replay never invokes a teacher or provider adapter — it's a pure deterministic verification.

### Public Python API

```python
from dtaifm import review, replay, inspect_bundle

bundle = review(
    constraints_path="constraints.yaml",
    rules_path="rules.yaml",
    state_path="state.json",
    domain_id="smart_home",
    bundle_path="review.json",  # optional
)

result = replay("review.json")          # or replay(bundle)
assert result.success
assert result.inputs_intact
assert result.validation_matches

summary = inspect_bundle("review.json")  # pure read; no execution
```

The CLI is a thin wrapper over these three functions.

### Pipeline

```
propose   ->   validate   ->   run      (or `review` for all three in one report)
[teacher]      [student]       [runtime]
artifact       gate            execution
```

`propose` only writes a file. `validate` only audits it. The runtime only ever sees rules that the validator approved. The principle: AI output is an artifact, not an action.

### File formats (all versioned)

Every dtaifm file carries `schema_version: "0.1"` at the top level. Loaders reject files with a missing or unsupported version.

**constraints.yaml**

```yaml
schema_version: "0.1"
constraints:
  - id: no_auto_unlock
    description: "Never unlock doors automatically."
    type: absolute_prohibition
    applies_to: [front_door]
    action: unlock
```

**rules.yaml** (proposed rules carry provenance; hand-written rules may omit it)

```yaml
schema_version: "0.1"
rules:
  - id: r_x
    name: "Example"
    trigger: { device: motion_sensor, event: motion_detected }
    conditions: []
    actions:
      - { device: hallway_light, action: turn_on }
    satisfies_constraints: [motion_light_hours]
    explanation: "What the rule does."
    rationale: "Why the teacher proposed it."
    proposed_by: mock
    proposal_id: 7f3c...
    created_at: "2026-05-24T10:00:00+00:00"
```

**state.json**

```json
{
  "schema_version": "0.1",
  "event":   { "device": "motion_sensor", "type": "motion_detected" },
  "time":    "2024-01-01T23:00:00",
  "mode":    "normal",
  "devices": { "ac": "off", "heating": "off" }
}
```

### Execution trace

Every `run` produces a deterministic trace explaining why each approved rule fired or was skipped — the condition that failed, with its evaluated parameters. Rejected rules never reach the runtime and therefore never appear in the trace.

```
FIRED    [r_motion_night_light]  trigger matched and all conditions passed
             - time_range {'start_hour': 22, 'end_hour': 6} -> ok
             - mode_not {'mode': 'security'} -> ok
SKIPPED  [r_heating_cold]  trigger did not match (rule expects thermostat.temperature_below_threshold)
```

### Expected demo output

```
=== dtaifm Smart Home Demo ===
AI proposes. The deterministic layer disposes.

──────────────────────────────────────────────────
  1. Constraints (defined by humans)
──────────────────────────────────────────────────
  [no_auto_unlock]      Never unlock doors automatically.
  [no_hvac_conflict]    Do not turn heating and AC on at the same time.
  [motion_light_hours]  Lights may turn on from motion only during configured night hours.
  [security_override]   Security mode overrides comfort automation.
  [rule_must_explain]   Every generated rule must explain which constraint it satisfies.

──────────────────────────────────────────────────
  2. Teacher proposes rules (AI / mock)
──────────────────────────────────────────────────
  3 rule(s) proposed:
  [r_motion_night_light]  Motion-Activated Night Light
  [r_auto_unlock_door]    Auto-Unlock on Arrival (UNSAFE)
  [r_heating_cold]        Activate Heating When Cold

──────────────────────────────────────────────────
  3. Validator reviews each rule (deterministic)
──────────────────────────────────────────────────
  APPROVED  [r_motion_night_light]  Motion-Activated Night Light
  REJECTED  [r_auto_unlock_door]    Auto-Unlock on Arrival (UNSAFE)
            ! [no_auto_unlock]    Rule 'r_auto_unlock_door' performs prohibited action 'unlock' on device 'front_door'.
            ! [rule_must_explain] Rule 'r_auto_unlock_door' does not declare which constraints it satisfies.
  APPROVED  [r_heating_cold]        Activate Heating When Cold

──────────────────────────────────────────────────
  4. Runtime executes approved rules (deterministic)
──────────────────────────────────────────────────

  Event: motion_detected at 23:00 — normal mode
    -> [r_motion_night_light] hallway_light: turn_on  {'duration': 300}

  Event: motion_detected at 23:00 — security mode
    -> (no rules triggered)

  Event: motion_detected at 14:00 — normal mode (outside night hours)
    -> (no rules triggered)

  Event: temperature_below_threshold — AC off, normal mode
    -> [r_heating_cold] heating: turn_on
```

## Core Concepts

| Concept | Role |
|---|---|
| `Constraint` | A hard rule a system must never violate. Defined by humans in YAML. Immutable at runtime. |
| `Rule` | A candidate action proposed by the AI teacher. Contains trigger, conditions, actions, and a declaration of which constraints it satisfies. |
| `RuleSet` | A collection of proposed rules returned by a single teacher call. |
| `ValidationResult` | The outcome of checking one Rule against all Constraints. Carries violations with reasons. |
| `ExecutionResult` | The outcome of firing approved rules against a live system state event. |

### Constraint types

| Type | Description |
|---|---|
| `absolute_prohibition` | A specific action on a specific device is never allowed. |
| `mutual_exclusion` | Two or more devices must never be activated simultaneously. |
| `temporal_restriction` | A device may only be controlled via a trigger within a time window. |
| `mode_override` | A named mode (e.g. `security`) supersedes comfort automation. |
| `metadata_requirement` | Every rule must carry specified metadata fields. |

## Defining Your Own Constraints

```yaml
# constraints.yaml
constraints:
  - id: no_auto_unlock
    description: "Never unlock doors automatically."
    type: absolute_prohibition
    applies_to:
      - front_door
    action: unlock
```

Load them in Python:

```python
import yaml
from dtaifm.core.constraint import Constraint

with open("constraints.yaml") as f:
    data = yaml.safe_load(f)
constraints = [Constraint.from_dict(c) for c in data["constraints"]]
```

## Domains

dtaifm is **middleware**, not a smart-home engine. A *domain pack* declares what is possible in a given system — its allowed trigger events, condition types, action verbs, and any domain-specific constraint evaluators. Teachers propose only within that boundary; the validator and runtime both refuse out-of-vocabulary rules.

Two domains ship in the box:

| Domain id | What it covers |
|---|---|
| `smart_home` (default) | Residential automation: lights, HVAC, locks, sensors. |
| `network_automation` | Router/switch config, BGP, maintenance windows; includes custom evaluators for `companion_action_required`, `action_target_limit`, `mode_required`. |

Every CLI command takes `--domain`:

```bash
# smart_home (default)
dtaifm validate examples/smart_rules/constraints.yaml examples/smart_rules/rules.yaml

# network_automation
dtaifm validate --domain network_automation \
  examples/network_automation/constraints.yaml examples/network_automation/rules.yaml

dtaifm review --domain network_automation \
  examples/network_automation/constraints.yaml examples/network_automation/rules.yaml \
  --state examples/network_automation/state.json
```

### Adding your own domain

```python
from dtaifm.domains.base import Domain
from dtaifm.domains.registry import register_domain

MY_DOMAIN = Domain(
    id="my_domain",
    version="0.1",
    trigger_events=frozenset({"order_placed", "shipment_delayed"}),
    condition_types=frozenset({"time_range", "mode_not", "device_state"}),
    action_kinds=frozenset({"notify", "refund", "escalate"}),
    extra_constraint_evaluators={
        # "my_custom_type": my_evaluator,  # (rule, constraint) -> ConstraintViolation | None
    },
)
register_domain(MY_DOMAIN)
# Now: dtaifm validate --domain my_domain ...
```

Provider adapters (Anthropic, OpenAI, etc.) contain **no domain logic**. They are translators that take a `TeacherRequest` (which carries the domain) and return a portable RuleSet. The domain's vocabulary is rendered into the prompt automatically.

## Teachers

A **Teacher** translates a `TeacherRequest` (constraints + context) into a `TeacherResponse` carrying a portable `RuleSet` artifact. Teachers never validate or execute. **Provider adapters are translators, not trusted components.**

### Mock teacher (always available, no install needed)

```bash
dtaifm propose constraints.yaml --teacher mock --out proposed.yaml
```

### Anthropic Claude adapter (optional extra)

```bash
pip install 'dtaifm[anthropic]'
export ANTHROPIC_API_KEY=sk-ant-...

# (optional) override the default model:
export ANTHROPIC_MODEL=claude-opus-4-7

dtaifm propose constraints.yaml --teacher anthropic --domain smart_home --out proposed.yaml
```

The Anthropic SDK is **not** a core dependency. `pip install dtaifm` still works without it; an attempt to use `--teacher anthropic` without the extra installed fails with a clear install hint.

### Local teachers — Ollama and Lemonade (no API keys)

Both adapters speak plain JSON over HTTP via stdlib — no extra install required. Defaults:

| Teacher | Default base URL | Endpoint | Env var |
|---|---|---|---|
| `ollama` | `http://localhost:11434` | `POST /api/chat` | `DTAIFM_OLLAMA_BASE_URL` |
| `lemonade` | `http://localhost:13305` | `POST /v1/chat/completions` (OpenAI-compatible) | `DTAIFM_LEMONADE_BASE_URL` |

Override precedence is **CLI flag > env var > default**, and trailing slashes are normalized.

```bash
# Local Ollama (default endpoint, llama3.2 by default)
dtaifm propose constraints.yaml --teacher ollama --domain smart_home --out proposed.yaml

# Local Ollama with a specific model
dtaifm propose constraints.yaml --teacher ollama --model qwen3:0.6b --out proposed.yaml

# Lemonade on a remote workstation
dtaifm propose constraints.yaml \
  --teacher lemonade \
  --teacher-base-url http://192.0.2.10:13305 \
  --model Qwen3-0.6B-GGUF \
  --out proposed.yaml

# Or, via env var:
export DTAIFM_LEMONADE_BASE_URL=http://192.0.2.10:13305
dtaifm propose constraints.yaml --teacher lemonade --model Qwen3-0.6B-GGUF --out proposed.yaml
```

The local adapters route the model's response through the same strict parser as the Anthropic adapter — malformed output fails clearly, narration outside the JSON block is tolerated, and provenance fields (`rationale`, `satisfies_constraints`) are required. **Local models improve privacy and adoption, but they are still untrusted teachers** — every proposed rule still has to pass `dtaifm review` before anything executes.

### Diagnosing your local setup

```bash
dtaifm teachers           # list registered teachers + base URLs + env-var hints
dtaifm teachers --check   # additionally ping local endpoints; offline servers are reported gracefully
dtaifm teachers --json    # machine-readable
```

## Reproposal Loop

Teachers rarely produce a perfect first proposal. The reproposal loop lets any teacher (mock, Anthropic, Ollama, Lemonade) consume the validator's deterministic violation reasons and try again — without weakening the trust boundary.

```bash
# 1. The teacher's first attempt
dtaifm propose constraints.yaml --teacher ollama --out v1.yaml

# 2. Inspect what failed (validator only — no execution)
dtaifm feedback constraints.yaml v1.yaml --out feedback.json
# feedback.json contains: schema_version, domain, rejected_rules
#   [{rule_id, name, violations, allowed_triggers, allowed_conditions, allowed_actions}]

# 3. Repropose: the teacher receives the previous rules + the named violations
dtaifm repropose constraints.yaml v1.yaml --teacher ollama --out v2.yaml

# 4. Now run a real review on the revised file (THIS is where execution happens)
dtaifm review constraints.yaml v2.yaml --state state.json --bundle review.json
```

**Guarantees enforced in code:**

- `dtaifm feedback` never instantiates the runtime (tests assert this).
- `dtaifm repropose` validates the original rules once to build feedback, calls the teacher, and writes the revised file — it does **not** validate or execute the revision. Even if the teacher returns an unsafe rule, repropose writes it. Only `dtaifm review` or `dtaifm validate` gates execution.
- The prompt's `REVISION REQUESTED` section uses stable, grep-able markers (`YOUR PREVIOUS RULES:`, `REJECTED RULES (must be fixed or removed):`, `Violations:`, `Allowed triggers:` / `conditions:` / `actions:`) so adapter tests can lock its format.

The principle: **the deterministic layer may teach the teacher, but it never lets the teacher grade itself.**

> **Warning:** Generated rules are an artifact, not a green light. Always run them through `dtaifm review` (or `dtaifm validate` + `dtaifm run`) before deploying — the validator is the only gate that authorizes execution.

### Inspecting the prompt

```bash
dtaifm prompt constraints.yaml --teacher anthropic --domain smart_home
```

`dtaifm prompt` shows the exact text input the adapter would send. It requires no API key and makes no network calls.

### Building your own teacher

```python
from dtaifm.teacher.base import Teacher
from dtaifm.teacher.contract import TeacherRequest, TeacherResponse
from dtaifm.teacher.parser import parse_provider_payload
from dtaifm.teacher.registry import register_teacher

class CustomTeacher(Teacher):
    def propose(self, request: TeacherRequest) -> TeacherResponse:
        # 1. self.render_prompt(request) gives you the standard prompt
        # 2. Call your provider, request JSON output that matches dtaifm.schema.RULES_SCHEMA
        # 3. Run the response through parse_provider_payload for strict validation
        payload = ...  # dict from your provider
        ruleset = parse_provider_payload(payload, source="custom")
        return TeacherResponse(ruleset=ruleset, raw_provider_output=...)

register_teacher("custom", CustomTeacher)
# Now: dtaifm propose constraints.yaml --teacher custom --out proposed.yaml
```

`dtaifm propose` stamps `proposed_by`, `proposal_id`, and `created_at` on every rule automatically. Teachers only need to supply the rule logic and a non-empty `rationale` for each rule.

## Developer commands

```bash
# Install with dev tools (pytest, jsonschema, ruff, build)
pip install -e ".[dev]"

# Run the test suite (256 tests, fully offline, no API keys)
pytest

# Lint and format
ruff check dtaifm tests
ruff format dtaifm tests

# Build a wheel
python -m build --wheel

# Smoke-test the wheel in a clean venv (also runs in CI)
python -m venv /tmp/wheel-test
/tmp/wheel-test/bin/pip install dist/dtaifm-0.1.0-py3-none-any.whl
/tmp/wheel-test/bin/dtaifm --help
```

Optional type checking (`mypy dtaifm`) is supported but not enforced in CI.

## Roadmap

- [x] CLI (`validate`, `run`) with text + JSON output
- [x] Portable rule files (YAML / JSON)
- [x] Deterministic execution trace
- [x] CI on Python 3.11–3.13 (core install + anthropic-extra install)
- [x] Schema versioning + published JSON Schemas (`dtaifm schema`)
- [x] `dtaifm propose` (teacher artifact) and `dtaifm review` (combined audit)
- [x] Rule provenance fields (`proposed_by`, `proposal_id`, `created_at`, `rationale`)
- [x] Teacher registry (adapter slot — no provider deps in core)
- [x] `TeacherRequest` / `TeacherResponse` / `PromptContext` provider-neutral contract
- [x] `dtaifm prompt` — inspect adapter input with no API key
- [x] Strict provider response parsing (`ProviderResponseError`)
- [x] Anthropic Claude teacher adapter (optional extra)
- [x] Domain pack abstraction with registry (`smart_home`, `network_automation`)
- [x] Domain-aware validator (rejects out-of-vocabulary triggers/conditions/actions)
- [x] Runtime defense-in-depth: refuses actions outside the active domain
- [x] Domain-aware prompts (every adapter receives the domain's vocabulary)
- [x] Replayable audit bundles (`.dtaifm-review.json`) with canonical-JSON SHA-256 hashes
- [x] `dtaifm replay` and `dtaifm inspect` commands; public Python API (`review`, `replay`, `inspect_bundle`)
- [x] Tamper detection across inputs, stored results, and recomputed results
- [x] Local teacher adapters: `ollama` and `lemonade` (no API keys, no extra deps)
- [x] `dtaifm teachers` / `dtaifm teachers --check` connectivity diagnostics
- [x] Deterministic feedback artifacts (`dtaifm feedback`) — validation-only, no execution
- [x] Reproposal loop (`dtaifm repropose`) — teachers consume named violations through the same `TeacherRequest` contract; the revision is written but not validated/executed
- [ ] OpenAI teacher adapter (optional extra)
- [ ] Persistent audit log of every propose → validate → execute cycle
- [ ] Telecom / network automation example
- [ ] Rust/WASM deterministic runtime

## Contributing

Contributions welcome. The most valuable areas right now are teacher adapters for real AI providers and additional constraint types. Open an issue before large PRs.

## License

MIT
