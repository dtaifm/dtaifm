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

## The teacher contract

Every teacher — `MockTeacher`, `AnthropicTeacher`, `OllamaTeacher`, `LemonadeTeacher`, and any custom adapter — implements:

```python
class Teacher(ABC):
    def render_prompt(self, request: TeacherRequest) -> str: ...
    def propose(self, request: TeacherRequest) -> TeacherResponse: ...
```

A `TeacherRequest` carries the constraints, the domain (with its vocabulary), an optional `PromptContext`, and — for revisions — a `feedback` artifact and `previous_rules`. A `TeacherResponse` carries a portable `RuleSet` plus the raw provider output for audit.

## Trust boundary rules

1. **AI output is an artifact, not an action.** Teachers never validate or execute.
2. **Provider adapters are translators, not trusted components.** Every adapter routes output through the strict parser before returning a `RuleSet`.
3. **Domains define what is possible; teachers only propose within that boundary.** The validator rejects rules using out-of-vocabulary triggers, conditions, or actions; the runtime double-checks at execution time.
4. **Provider dependencies stay optional.** `pip install dtaifm` works without any LLM SDK.
5. **Replay is deterministic.** Bundles use canonical-JSON SHA-256 hashes; replay reproduces exactly or fails clearly.

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
