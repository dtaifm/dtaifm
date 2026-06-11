# Changelog

All notable changes to this project are tracked here. The project follows
semantic versioning once it leaves alpha.

## [Unreleased]

### Added

- **`when_action:` scope on `parameter_threshold`** (#38) — optional action-conditional bounds: the threshold only applies to rules whose action set includes the named action kind, so a bound on a shared condition binds only the rules that act on it. Backward-compatible (no behavior change when absent); requested from adopter field experience with 0.1.6's generic types. The equivalent extension on `requires` was explicitly declined — its `if_action` already provides that scoping.

### Docs

- **Fail-closed governance metadata** guidance in `docs/domains.md`: producers emit governance state explicitly, validators reject absence; `parameter_threshold`'s fail-closed behavior is the in-framework precedent.

## [0.1.6] — 2026-06-11

Additive release: five generic policy constraint types. No trust-boundary, rule-schema, bundle, or replay change.

### Added

- **Five generic policy constraint types** (#35) — `action_allowlist`, `action_denylist`, `requires`, `mutually_exclusive_actions`, and `parameter_threshold` — usable from any `constraints.yaml` with no custom evaluator code. They cover the guardrail shapes domain packs most often re-implement: allow/deny action vocabularies (optionally per device), companion action/condition requirements (the evidence-as-conditions pattern), action mutual exclusion, and numeric bounds. `parameter_threshold` is fail-closed: a matching action/condition whose bounded parameter is missing or non-numeric is rejected. Implemented in `dtaifm/student/generic_evaluators.py`; domain-registered evaluators still take priority, so a domain can override any of them. The constraints JSON Schema enum is widened accordingly (additive; `schema_version` unchanged at 0.1). No change to the rule schema, bundle format, or replay semantics.

## [0.1.5] — 2026-06-10

Additive release: a `--version` CLI flag and `twine` in the dev extra, plus README/metadata polish. No trust-boundary or rule-schema change.

### Added

- **`dtaifm --version`.** The top-level CLI now accepts `--version`, printing `dtaifm <version>` and exiting 0 — no subcommand required. Previously the installed version could only be read by importing `dtaifm.__version__` in Python.

### Changed

- **`twine` added to the `[dev]` extra.** Release tooling (`twine check` / `twine upload`) is now provisioned by `pip install -e ".[dev]"` instead of an ad-hoc install at release time.
- **README positioning.** Leads with the threat model and the advisor-not-executor philosophy, adds a traditional-agentic-AI vs dtaifm comparison table, and broadens PyPI keywords + adds the `Topic :: Security` classifier.

## [0.1.4] — 2026-05-31

Bugfix release. The teacher parser no longer rejects custom-domain condition types; the trust boundary is preserved (parser = shape/schema, validator = domain vocabulary). No rule-schema change.

### Fixed

- **BUG-1 (#21): teacher parser rejected custom-domain condition types.** The strict provider-response parser hardcoded the built-in condition vocabulary and rejected any other condition `type` at parse time, blocking custom domains (e.g. `host_class` for a `ttek2_crawler_gate` domain) on the propose/repropose path. The parser now checks **shape only** (a condition must be an object with a `type`); domain vocabulary is enforced downstream by the Validator against the active domain (`domain.condition_types`), which already did so. `KNOWN_CONDITION_TYPES` is retained and still exported but is no longer enforced by the parser. Trigger/action parsing was already shape-only (guard test added).

### Tests

- Full suite: **327 passed**. Added: parser accepts an arbitrary/custom condition type; OpenAI + Anthropic fake-client adapters accept a `host_class` proposal; validator accepts `host_class` when the active domain includes it and rejects it when not.

## [0.1.3] — 2026-05-30

### OpenAI teacher adapter (optional extra)

- New `openai` teacher behind the `dtaifm[openai]` optional extra, beside `anthropic`, `ollama`, and `lemonade`. Registered as `--teacher openai`.
- Calls OpenAI's **Responses API** (`client.responses.create`) and requests **Structured Outputs** via a `json_schema` `text.format`; the returned text is routed through the same strict parser (`parse_provider_text`) as every other adapter — the adapter only translates, it never validates or executes.
- The Structured-Outputs schema is sent in **non-strict** mode by design: strict mode requires `additionalProperties: false` on every object, which would forbid dtaifm's open-ended action `parameters` and per-type condition fields. Non-strict steers structure while the deterministic parser stays the authoritative gate.
- Requires `OPENAI_API_KEY`; honours `OPENAI_MODEL`; `--model` overrides env and default. Default model: `gpt-5.5`.
- Missing SDK and missing key each fail with a clear hint (`pip install 'dtaifm[openai]'` / `OPENAI_API_KEY`, exit 2). `dtaifm teachers` lists `openai` as `cloud_sdk`; `dtaifm prompt --teacher openai` needs no key.
- Unit tests inject a fake client — no live OpenAI calls in CI. Raw provider output stays diagnostic-only (never serialized into proposed/reproposed rule files or audit bundles).

### Tests

- Full suite: **324 passed**.

## [0.1.2] — 2026-05-26

Additive release: external domain discovery, a clarified (and regression-tested) raw-output contract, and concepts-doc closeout. No trust-boundary or rule-schema changes.

### External / custom domain discovery

- Installed third-party domain packs are auto-discovered from the `dtaifm.domains` entry-point group (an entry point may resolve to a `Domain` or a zero-argument callable returning one).
- New `--domain-module PKG.MODULE` flag on every domain-resolving command (`validate`, `run`, `review`, `propose`, `prompt`, `feedback`, `repropose`, `demo`, `replay`) loads a local or not-yet-installed domain module before resolution.
- A broken third-party entry point is reported as a warning and skipped — never fatal; unknown-domain errors still list the available domains.

### Raw provider output clarified as diagnostic-only

- `TeacherResponse.raw_provider_output` is documented as in-memory diagnostic data that the framework never serializes into proposed/reproposed rule files or audit bundles. Docstring and `docs/concepts.md` wording corrected.
- Added regression tests asserting a sentinel raw output never leaks via `propose`, `repropose`, `demo`, or `review --bundle`.

### Documentation

- `docs/concepts.md` now links the domain-pack (`docs/domains.md`) and audit-bundle (`docs/audit-bundles.md`) guidance, with a "Writing a domain pack" section and a bundle-contents table.

### Tests

- Full suite: **304 passed**.

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

[0.1.4]: https://github.com/dtaifm/dtaifm/releases/tag/v0.1.4
[0.1.3]: https://github.com/dtaifm/dtaifm/releases/tag/v0.1.3
[0.1.0]: https://github.com/dtaifm/dtaifm/releases/tag/v0.1.0
