# Concepts

dtaifm is open-source middleware for systems where AI generates candidate logic and a deterministic, constraint-verified layer has the final say.

> AI output is an artifact, not an action.

## The three layers

```
Constraints (humans)        ← trusted; define what must never happen
       │
       ▼
Teacher.propose()           ← AI or mock; produces a candidate RuleSet (artifact)
       │
       ▼
Validator.validate_ruleset()← deterministic; approves or rejects each rule
       │
       ▼
PythonRuntime.fire()        ← executes ONLY validator-approved rules
```

No rule reaches the runtime without passing the validator. This is the architectural contract.

## Core primitives

| Type | Role |
|---|---|
| `Constraint` | A hard rule a system must never violate. Trusted human input. Has an `id`, `description`, `type`, and type-specific parameters. |
| `Rule` | A candidate action proposed by a teacher. Has a trigger, conditions, actions, `satisfies_constraints` declaration, `explanation`, and provenance fields. |
| `RuleSet` | A collection of proposed rules from one teacher call. |
| `ValidationResult` | Per-rule outcome with named `ConstraintViolation` records. |
| `ExecutionResult` | Per-event outcome with `triggered_rule_ids`, `actions_taken`, and a `RuleExecutionTrace` per rule explaining why it fired or was skipped. |

## Built-in constraint types

| Type | Meaning |
|---|---|
| `absolute_prohibition` | A specific action on a specific device is never allowed. |
| `mutual_exclusion` | Two or more devices must never be activated simultaneously. |
| `temporal_restriction` | A device may only be controlled via a trigger within a time window. |
| `mode_override` | A named mode (e.g. `security`) supersedes ordinary automation. |
| `metadata_requirement` | Every rule must carry specified metadata fields (e.g. `satisfies_constraints`). |

Domain packs may register additional constraint types. The validator dispatches by `constraint.type` (a plain string), falling back from domain-registered evaluators to the built-ins.

## Writing a domain pack

A **domain pack** is a `Domain` that declares the vocabulary teachers may use, plus any custom constraint evaluators. The validator and runtime both refuse out-of-vocabulary rules.

```python
from dtaifm.domains.base import Domain
from dtaifm.domains.registry import register_domain

MY_DOMAIN = Domain(
    id="my_domain",
    version="0.1",
    trigger_events=frozenset({"event_a", "event_b"}),       # allowed trigger events
    condition_types=frozenset({"time_range", "mode_not"}),  # known condition types
    action_kinds=frozenset({"notify", "escalate"}),         # allowed action verbs
    extra_constraint_evaluators={"my_type": my_evaluator},  # custom checks, keyed by constraint.type
)
register_domain(MY_DOMAIN)
```

A custom constraint evaluator is a **pure function** with the same signature as the built-ins — `(Rule, Constraint) -> ConstraintViolation | None` — returning `None` when the rule satisfies the constraint. By design it receives only the rule and the constraint: no external state, database, or scoring handle. Keep your system of record outside dtaifm and pass what the evaluator needs in as constraint parameters (or as a validated attestation).

See **[Domains](domains.md)** for the full walkthrough — the `examples/custom_domain_template/` starting point, vocabulary enforcement, and reading the registry.

## The teacher contract

Every teacher — `MockTeacher`, `AnthropicTeacher`, `OllamaTeacher`, `LemonadeTeacher`, and any custom adapter — implements:

```python
class Teacher(ABC):
    def render_prompt(self, request: TeacherRequest) -> str: ...
    def propose(self, request: TeacherRequest) -> TeacherResponse: ...
```

A `TeacherRequest` carries the constraints, the domain (with its vocabulary), an optional `PromptContext`, and — for revisions — a `feedback` artifact and `previous_rules`. A `TeacherResponse` carries a portable `RuleSet`. It also exposes `raw_provider_output` (the raw model text) as **in-memory diagnostic data only** — the framework never serializes it into proposed rule files or audit bundles, so a caller that needs to keep it must persist it themselves to a private path.

## Trust boundary rules

1. **AI output is an artifact, not an action.** Teachers never validate or execute.
2. **Provider adapters are translators, not trusted components.** Every adapter routes output through the strict parser before returning a `RuleSet`.
3. **Domains define what is possible; teachers only propose within that boundary.** The validator rejects rules using out-of-vocabulary triggers, conditions, or actions; the runtime double-checks at execution time.
4. **Provider dependencies stay optional.** `pip install dtaifm` works without any LLM SDK.
5. **Replay is deterministic.** Bundles use canonical-JSON SHA-256 hashes; replay reproduces exactly or fails clearly.

## Audit bundles

`dtaifm review ... --bundle review.json` writes a portable, replayable record of a single review; `dtaifm replay` recomputes it on a fresh checkout and confirms — via canonical-JSON SHA-256 hashes — that the same inputs reproduce the same outputs. A bundle holds **only** the keys below; it never contains raw provider prompts or responses (see the teacher contract above).

| Key | Contents |
|---|---|
| `bundle_version` | Bundle format version. |
| `framework_version` | dtaifm version that wrote the bundle. |
| `schema_version` | Portable-file schema version. |
| `created_at` | UTC timestamp (seconds precision). |
| `domain` | `{id, version}` of the domain used. |
| `proposals` | Provenance grouped by `proposal_id`: `proposed_by`, `created_at`, `rule_ids`. |
| `inputs` | `constraints`, `rules`, `state` — each as `{source, hash, content}`. |
| `validation` | `{hash, result}` — per-rule approve/reject outcome. |
| `execution` | `{hash, result}` — event, triggered rules, actions taken, and trace. |

Each `hash` is `sha256:<hex>` over the canonical-JSON form of its `content`/`result`. See **[Audit bundles](audit-bundles.md)** for replay semantics and the public Python API.

## File formats

Every dtaifm file declares `schema_version: "0.1"` and is validated against a published JSON Schema (`dtaifm schema constraints | rules | state`). YAML and JSON are interchangeable — they hash identically thanks to canonical-JSON serialization.

## Pipeline of CLI commands

```
schema      emit JSON Schemas
prompt      show the exact text a teacher would receive (no API key needed)
propose     teacher writes a candidate rule file
feedback    validate + emit deterministic violation feedback (no execution)
repropose   feed violations back to the teacher and write a revised file
validate    audit a rule file against constraints (exit 1 on rejection)
run         validate + execute against a state event
review      validate + execute + emit a combined audit (optionally as a bundle)
inspect     read a bundle (no execution)
replay      re-run from a bundle and verify hashes match
teachers    list registered teachers; --check pings local endpoints
```

Only `validate`, `run`, `review`, and `replay` exercise the deterministic gate. Everything else is read-only or write-only.
