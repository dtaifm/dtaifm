# Launch

> AI proposes. The deterministic layer disposes. AI output is an artifact, not an action.

## The pitch

dtaifm is open-source middleware for systems where AI generates candidate logic and a deterministic, constraint-verified layer has the final say. Every rule a teacher (cloud LLM, local model, or test stub) proposes is validated against human-authored constraints before any action runs — and every review can be sealed into a portable, replayable audit bundle.

Three layers, one contract:

```
Constraints (humans)          ← trusted; define what must never happen
Teacher.propose()             ← AI or mock; produces a portable RuleSet
Validator.validate_ruleset()  ← deterministic; approves or rejects each rule
PythonRuntime.fire()          ← executes ONLY validator-approved rules
```

No rule reaches the runtime without passing the validator. This is the architectural contract that everything else in dtaifm exists to support.

## 60-second demo

```bash
pip install -e ".[dev]"
dtaifm demo smart_home
```

The demo walks the full pipeline — propose → validate → execute → bundle → replay — and prints a step-by-step report ending in `RESULT: PASSED`. It runs fully offline using a mock teacher; no API key is required.

Also try:

```bash
dtaifm demo network_automation
dtaifm demo smart_home --teacher ollama --model llama3.2   # if you have Ollama running locally
dtaifm demo smart_home --json                              # machine-readable
```

## Where dtaifm fits

- **Closed-loop AI for systems with hard rules.** Operations, networking, home automation, support workflows, financial controls — anywhere a wrong action is more expensive than no action.
- **AI-as-teacher patterns.** Use an LLM to draft policy candidates that a deterministic layer ratifies.
- **Audit-required environments.** Every review can be sealed into a `.dtaifm-review.json` bundle with canonical-JSON SHA-256 hashes; `dtaifm replay` reproduces it deterministically.
- **Local-first deployments.** Ollama and Lemonade adapters ship in core with no extra dependencies; nothing leaves the machine if you don't want it to.

## Where dtaifm does not fit

- **General LLM orchestration.** If you want to chain prompts, manage memory, or build agentic loops, use LangChain, LlamaIndex, or DSPy.
- **Free-form chat or RAG.** dtaifm has no opinion about retrieval pipelines.
- **As a smart-home product.** `smart_home` and `network_automation` ship as **domain packs** that demonstrate the pattern; they are not finished products. Build a real domain pack on top — see [`examples/custom_domain_template/`](../examples/custom_domain_template/).
- **As a workflow engine.** dtaifm validates and executes a single event per fire; it does not orchestrate long-running multi-step pipelines. Pair it with Temporal/Airflow if you need that.

## What ships in v0.1

| Capability | Surface |
|---|---|
| Core primitives | `Constraint`, `Rule`, `RuleSet`, `ValidationResult`, `ExecutionResult` |
| Built-in constraint types | `absolute_prohibition`, `mutual_exclusion`, `temporal_restriction`, `mode_override`, `metadata_requirement` |
| Domain packs | `smart_home`, `network_automation` (+ extensible registry) |
| Teacher adapters | `mock`, `anthropic` (optional extra), `ollama`, `lemonade` |
| Audit | `dtaifm review --bundle`, `dtaifm replay`, `dtaifm inspect`; public Python API (`from dtaifm import review, replay, inspect_bundle`) |
| Reproposal loop | `dtaifm feedback`, `dtaifm repropose` (validator-only feedback; never validates the revision) |
| Diagnostics | `dtaifm teachers --check` |
| Demo | `dtaifm demo <domain>` walks the full pipeline in under a minute |
| Schema versioning | `schema_version: "0.1"` on every file; published JSON Schemas via `dtaifm schema {constraints|rules|state}` |
| Tests | 268 tests, fully offline, no API keys required |

## How to evaluate it in 10 minutes

1. `dtaifm demo smart_home` — see the trust boundary in action.
2. `dtaifm demo smart_home --json | jq` — see the same thing as structured data.
3. Read [docs/concepts.md](concepts.md) — 5 minutes.
4. Read [docs/comparison.md](comparison.md) — does dtaifm overlap with something you already use? Where does it differ?
5. Skim [`examples/custom_domain_template/`](../examples/custom_domain_template/) — could you write a domain pack for your system?

## Where to go next

- [docs/quickstart.md](quickstart.md) — full install + first run
- [docs/concepts.md](concepts.md) — architecture and the trust boundary
- [docs/domains.md](domains.md) — write your own domain pack
- [docs/local-teachers.md](local-teachers.md) — Ollama and Lemonade in depth
- [docs/audit-bundles.md](audit-bundles.md) — replayable artifacts
- [docs/reproposal-loop.md](reproposal-loop.md) — letting teachers learn from the validator
- [docs/comparison.md](comparison.md) — where dtaifm fits in the landscape
- [docs/roadmap.md](roadmap.md) — where v0.2 is headed
