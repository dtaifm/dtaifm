# Contributing to dtaifm

Welcome — and thank you for considering a contribution.

dtaifm is open-source deterministic-first AI middleware. It is **not** a smart-home product or a network-automation product; those are domain packs that demonstrate the pattern. Contributions that improve the framework (new constraint types, additional teacher adapters, new domain packs, better diagnostics, deeper docs) are all welcome.

## Quick setup

```bash
git clone https://github.com/markj87/dtaifm
cd dtaifm
pip install -e ".[dev]"
pytest
```

If everything is green you have a working dev environment. The full test suite finishes in a few seconds and runs entirely offline (no API keys, no network calls).

## Tasks at a glance

| Task | Command |
|---|---|
| Run the full test suite | `pytest` |
| Run a single test file | `pytest tests/test_bundle.py -v` |
| Run the Python demo | `python examples/smart_rules/demo.py` |
| Build the wheel | `python -m build --wheel` |
| Format code | `ruff format dtaifm tests` |
| Lint code | `ruff check dtaifm tests` |
| Type-check (optional) | `mypy dtaifm` |

Ruff is installed by `pip install -e ".[dev]"`. Type checking with mypy is optional and not enforced in CI.

## Repository layout

```
dtaifm/                    framework code
├── core/                  Constraint, Rule, RuleSet, ValidationResult, ExecutionResult
├── domains/               Domain abstraction + registry; built-in packs
├── teacher/               Teacher contract, prompt, parser, registry, adapters
├── student/               Validator
├── runtimes/              PythonRuntime
├── audit.py               JSON/text formatters for validation + execution
├── bundle.py              Audit bundles + replay + inspect (public Python API)
├── cli.py                 CLI entry point
├── io.py                  YAML/JSON loaders, schema-version enforcement
├── schema.py              SCHEMA_VERSION, JSON Schemas
└── serialize.py           Round-trip rules back to dicts for writing

examples/
├── smart_rules/           smart_home domain example files + Python demo
├── network_automation/    network_automation domain example files
└── custom_domain_template/  starting point for new domain packs

tests/                     full test suite (run with `pytest`)
docs/                      human-readable walkthroughs
```

## Architectural rules

These are load-bearing. PRs that weaken them will be sent back for revision.

1. **AI output is an artifact, not an action.** Teachers produce a portable `RuleSet`; only the deterministic `Validator` authorizes execution. No teacher adapter may validate or execute.
2. **Provider adapters are translators, not trusted components.** Strict parsing (`parse_provider_text` / `parse_provider_payload`) sits between every adapter and the framework. The runtime never sees rules that bypassed the validator.
3. **Domains define what is possible; teachers only propose within that boundary.** Adding a new built-in domain pack is welcome; adding domain-specific logic to a teacher adapter is not.
4. **Provider dependencies stay optional.** Core `pip install dtaifm` must work without any LLM SDK. New provider integrations belong in `dtaifm/teacher/adapters/` with a lazy import and a corresponding optional extra in `pyproject.toml`.
5. **All tests run offline.** Adapter tests inject a fake HTTP client or mock SDK object — no real network call in CI.

## Adding a new domain pack

The simplest path is to copy `examples/custom_domain_template/` and adapt it. See `docs/domains.md` for the full walkthrough. A built-in domain pack lives under `dtaifm/domains/<your_domain>/` and self-registers via `register_domain(...)` on import; the package import chain in `dtaifm/domains/__init__.py` triggers it.

## Adding a new teacher adapter

1. Create `dtaifm/teacher/adapters/<name>_adapter.py` exposing a `Teacher` subclass.
2. Use lazy imports inside the constructor if the adapter needs a third-party SDK.
3. Route the model's text response through `parse_provider_text`. Never instantiate the validator or runtime from inside the adapter.
4. Register a `**kwargs`-accepting factory in `dtaifm/teacher/registry.py`.
5. If the adapter needs a third-party SDK, add an optional extra in `pyproject.toml` and document the install command.
6. Add tests using an injected fake (HTTP client or SDK module).

## Pull request process

- Open an issue first for non-trivial changes (architectural changes, new adapters, new domains).
- Keep PRs focused: one logical change per PR.
- Update the changelog under `## [Unreleased]` (or create the section if missing).
- Add tests for new behavior. PRs without tests for new logic will not be merged.
- Run `pytest` locally and ensure all tests pass.
- Run `ruff check dtaifm tests` and address any reported issues (or explain why an ignore is appropriate).
- Update relevant docs in `docs/` and the README if the user-facing surface changes.

## Reporting bugs and requesting features

Use the issue templates under `.github/ISSUE_TEMPLATE/`. For security issues see [SECURITY.md](SECURITY.md).

## Code of conduct

Participation in this project is governed by the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md).
