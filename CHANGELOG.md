# Changelog

All notable changes to this project are tracked here. The project follows
semantic versioning once it leaves alpha.

## [0.1.0] — Unreleased

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

[0.1.0]: https://github.com/markj87/dtaifm/releases/tag/v0.1.0
