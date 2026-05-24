# Changelog

All notable changes to this project are tracked here. The project follows
semantic versioning once it leaves alpha.

## [0.1.1] — 2026-05-24

Post-launch dogfooding fixes discovered while running `dtaifm demo` against a real local Lemonade server hosting a thinking-model (Qwen 3.6). No code on the trust boundary changes; both fixes are additive.

### Configurable local-teacher HTTP timeout

- New `--teacher-timeout <seconds>` CLI flag on `propose`, `repropose`, and `demo`.
- New `DTAIFM_HTTP_TIMEOUT` environment variable, honoured by the `ollama` and `lemonade` adapters.
- Precedence: CLI flag > env var > adapter default (60s).
- Invalid values (non-numeric, zero, negative) surface as clear errors with exit code 2; argparse rejects non-numeric input directly, and `resolve_timeout` rejects zero/negative values via `ValueError`.
- Resolves a hang when using thinking models (Qwen 3.x, Gemma 3, etc.) whose reasoning phase plus structured-output generation exceeds the previous hardcoded 60s.

### Provider-neutral prompt wording for non-tool local models

- Removed the tool-specific `submit_ruleset` reference from the shared prompt template (both the initial-proposal section and the revision-requested section).
- The template now demands a literal `{"schema_version": "0.1", "rules": [...]}` envelope and explicitly warns the model not to wrap output in any other key (`data`, `result`, `output`, tool name).
- Fixes a real failure mode observed with Qwen 3.6 on Lemonade: the model emitted `{"submit_ruleset": {"rules": [...]}}` because the prompt's "via the submit_ruleset tool" wording was interpreted literally as a wrapper key.
- The Anthropic adapter continues to use its `submit_ruleset` tool internally via the SDK's tool-use mechanism; no behaviour change for that adapter — the literal tool name now lives only in the adapter, not in the shared prompt body.

## [0.1.0] — 2026-05-24

### Core architecture
- **Milestone 1** — Core primitives (`Constraint`, `Rule`, `RuleSet`, `ValidationResult`, `ExecutionResult`), `Teacher` interface with `MockTeacher`, deterministic `Validator` with five built-in constraint types, `PythonRuntime`, smart-home demo. 16 tests.
- **Milestone 2** — CLI (`validate`, `run`), portable YAML/JSON rules, per-rule execution trace (`RuleExecutionTrace`, `ConditionEvaluation`), text + JSON audit output, GitHub Actions CI, console script. 41 tests.
- **Milestone 3** — Schema versioning (`schema_version: "0.1"`) enforced at load; `dtaifm schema {constraints|rules|state}` emits Draft 2020-12 JSON Schemas; `dtaifm propose` (teacher artifact, no validation), `dtaifm review` (combined audit); rule provenance fields (`proposed_by`, `proposal_id`, `created_at`, `rationale`). 72 tests.

### Provider boundary
- **Milestone 4** — `TeacherRequest`/`TeacherResponse`/`PromptContext` contract; `dtaifm prompt` renders the input a teacher would see (no API key required); strict provider response parser (`parse_provider_text`, `parse_provider_payload`); Anthropic Claude adapter behind the `dtaifm[anthropic]` optional extra (uses tool-use for structured output). 120 tests.

### Domain packs
- **Milestone 5** — `Domain` abstraction + registry; smart-home behavior moved behind a domain pack; second built-in domain `network_automation` with three custom constraint evaluators (`companion_action_required`, `action_target_limit`, `mode_required`); domain-aware validator (vocabulary check) and runtime (defense-in-depth); prompts include the domain's vocabulary. 148 tests.

### Reproducibility
- **Milestone 6** — Audit bundles (`.dtaifm-review.json`) with canonical-JSON SHA-256 hashes over inputs and results; `dtaifm review --bundle`, `dtaifm replay` (tamper detection: inputs, stored results, recomputed results), `dtaifm inspect` (read-only summary); public Python API (`from dtaifm import review, replay, inspect_bundle`). 179 tests.

### Local-first
- **Milestone 7** — Local teacher adapters `ollama` (`POST /api/chat`) and `lemonade` (`POST /v1/chat/completions`, OpenAI-compatible) over stdlib HTTP — no extra deps; configurable base URLs (CLI > env > default, trailing slash normalized); `dtaifm teachers` / `--check` diagnostics; teacher factory accepts `**kwargs` for `model`/`base_url`. No real network calls in tests. 227 tests.

### Feedback loop
- **Milestone 8** — Deterministic feedback artifact built from validation failures (`dtaifm feedback`, validation-only); `dtaifm repropose` lets any teacher (cloud or local) consume violation reasons through `TeacherRequest.feedback` + `previous_rules`; prompt's `REVISION REQUESTED` section uses stable, grep-able markers; the revised file is written but **never** validated or executed by repropose. 251 tests.

### Distribution
- **Milestone 9** — Project metadata polish (LICENSE, CHANGELOG, CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, issue & PR templates); doc walkthroughs in `docs/`; `examples/custom_domain_template/` for new domain packs; wheel-build smoke test in CI; positioning callouts in README.

### Launch
- **Milestone 10** — `dtaifm demo <domain>` launch-grade walkthrough (`propose → review → bundle → replay → inspect`, fully offline by default via mock teacher); bundled demo fixtures shipped inside the wheel under `dtaifm/_demo/<domain_id>/`; launch docs (`docs/launch.md`, `docs/roadmap.md`, `docs/comparison.md`, `docs/release-checklist.md`); README badges + 60-second demo section; demo smoke tests added to both the test job and the release-readiness wheel job in CI. 268 tests.

[0.1.0]: https://github.com/dtaifm/dtaifm/releases/tag/v0.1.0
