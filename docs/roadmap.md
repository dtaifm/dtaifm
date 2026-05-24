# Roadmap

The framework is alpha. The architectural foundation is stable, but the surface is small by design. This document tracks what shipped, what's planned, and how to influence it.

## v0.1 — shipped

The full milestone list is in [CHANGELOG.md](../CHANGELOG.md). Headline capabilities:

- Three-layer architecture: teacher → validator → runtime.
- Built-in constraint types and a domain pack registry.
- Two domain packs that demonstrate the pattern (`smart_home`, `network_automation`) and a starting template (`examples/custom_domain_template/`).
- Teacher adapters: `mock`, `anthropic` (optional extra), `ollama`, `lemonade`.
- Audit bundles with canonical-JSON SHA-256 hashes; `dtaifm replay` for deterministic reproducibility.
- Reproposal loop: `dtaifm feedback` produces validator-only feedback, `dtaifm repropose` lets any teacher revise without weakening the trust boundary.
- `dtaifm demo <domain>` walkthrough.
- 268 tests, fully offline, no API keys.

## Near-term — community-shaped

These are ideas, not commitments. Each is reasonably scoped for a contributor.

### Teacher adapters

- **OpenAI adapter** (`dtaifm[openai]`). Use structured outputs / function calling for the same strict-parse contract as the Anthropic adapter. Should drop in alongside `anthropic`, `ollama`, `lemonade` with no domain logic.
- **vLLM / TGI adapters.** Same shape as the local HTTP adapters; mostly a base-URL + payload-shape change.
- **HuggingFace-Inference adapter.** Probably as another optional extra.

### Domain packs

- **Content moderation.** Triggers like `post_submitted`; actions like `flag`, `quarantine`, `auto_reject`. Constraints around forbidden categories, escalation paths, audit retention.
- **Financial controls.** Triggers like `transfer_requested`; actions like `approve`, `hold`, `require_dual_approval`. Constraints around amount limits and counterparty rules.
- **CI/CD policy.** Triggers like `deployment_requested`; actions like `proceed`, `require_canary`, `block`. Constraints around environments, change windows, and rollback requirements.

### Audit & trust

- **Persistent audit log.** Append-only store for every `propose → validate → execute` cycle. A "git for AI proposals."
- **Signed bundles.** Optional Ed25519 signing on top of the existing SHA-256 hashes.
- **Bundle diff.** `dtaifm diff a.json b.json` showing what changed across two reviews (constraint changes, rule changes, outcome changes).

### Diagnostics

- **`dtaifm doctor`** — broader environment check than `teachers --check`: verifies Python version, optional extras, file permissions, registered domains and their evaluators.

### Domains & evaluators

- **Additional generic constraint types.** Candidates: `rate_limit` (no more than N actions per time window), `dependency_required` (action A requires preceding action B in some store), `counterparty_allowlist`.
- **State-schema enforcement.** Each domain optionally publishes a JSON Schema for state files; loaders validate against it.

## Longer-term ambitions

- **Rust/WASM runtime.** A second runtime implementation that loads approved rules into WebAssembly for safe execution at the edge.
- **Streaming runtime.** Multi-event windows, sliding-window conditions; today the runtime is event-at-a-time.
- **Distributed validator.** Sharded constraint sets for very large domains.
- **Web UI.** Read-only at first — browse bundles, diff reviews, inspect violation reasons. Never an execution surface.

## What is explicitly out of scope

- General LLM orchestration (chains, agents, RAG pipelines). dtaifm is middleware that sits below an orchestrator if you have one.
- Domain-specific business logic in the core framework. If a domain needs custom evaluators, they belong in a domain pack, not in `dtaifm/student/validator.py`.
- A specific provider's prompt format leaking into the shared prompt template. Adapters may override `Teacher.render_prompt` if absolutely necessary.
- Any feature that would let an AI teacher bypass the validator. The trust boundary is the product.

## How to influence the roadmap

- Open an issue against the [GitHub repository](https://github.com/markj87/dtaifm) using the feature-request template.
- Sketch the architectural fit explicitly. PRs that align with the contract in [docs/concepts.md](concepts.md) move quickly.
- For new domain packs and teacher adapters: a PR with tests is the fastest path. Use [`examples/custom_domain_template/`](../examples/custom_domain_template/) or `dtaifm/teacher/adapters/ollama_adapter.py` as a starting point.
