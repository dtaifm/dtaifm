# Local teachers

Two local HTTP teacher adapters ship with the framework. Both speak plain JSON over stdlib `urllib` — no extra dependencies, no API keys.

| Teacher | Default base URL | Endpoint | Override env var |
|---|---|---|---|
| `ollama` | `http://localhost:11434` | `POST /api/chat` | `DTAIFM_OLLAMA_BASE_URL` |
| `lemonade` | `http://localhost:13305` | `POST /v1/chat/completions` (OpenAI-compatible) | `DTAIFM_LEMONADE_BASE_URL` |

Override precedence: **CLI flag > env var > default**. Trailing slashes are normalized.

## Ollama

```bash
# Default (assumes Ollama on localhost:11434)
dtaifm propose examples/smart_rules/constraints.yaml --teacher ollama --out proposed.yaml

# Specific model
dtaifm propose examples/smart_rules/constraints.yaml \
  --teacher ollama --model qwen3:0.6b --out proposed.yaml

# Different host
DTAIFM_OLLAMA_BASE_URL=http://192.0.2.10:11434 \
  dtaifm propose examples/smart_rules/constraints.yaml --teacher ollama --out proposed.yaml
```

Default model is `llama3.2`. Override with `--model` or `DTAIFM_OLLAMA_MODEL`.

## Lemonade

Lemonade exposes an OpenAI-compatible chat endpoint, so the adapter uses `response_format={"type":"json_object"}` to coax structured output.

```bash
# Remote workstation
dtaifm propose examples/network_automation/constraints.yaml \
  --domain network_automation \
  --teacher lemonade \
  --teacher-base-url http://192.0.2.10:13305 \
  --model Qwen3-0.6B-GGUF \
  --out proposed.yaml

# Or via env vars:
export DTAIFM_LEMONADE_BASE_URL=http://192.0.2.10:13305
export DTAIFM_LEMONADE_MODEL=Qwen3-0.6B-GGUF
dtaifm propose examples/network_automation/constraints.yaml \
  --domain network_automation --teacher lemonade --out proposed.yaml
```

Default model is `Qwen3-0.6B-GGUF`.

## Diagnostics

```bash
dtaifm teachers          # list registered teachers + base URLs + env-var hints
dtaifm teachers --check  # additionally ping local endpoints
dtaifm teachers --json   # machine-readable
```

`--check` reports `reachable` (with the model list when available) or `offline` (with a clear error message). Offline servers never crash the command — exit code is 0 either way.

## Strict response parsing

Every adapter routes model output through `parse_provider_text` → `parse_provider_payload`. The same rules apply across cloud and local:

- Narration outside the JSON block is ignored (fenced ` ```json ` or bare `{ ... }` both work).
- Missing `rationale` or an empty `satisfies_constraints` list fail at parse time. Condition/trigger/action **vocabulary is not checked here** — that is the Validator's job against the active domain, so a custom domain's types pass the parser and are validated downstream.
- Connection failures surface as `RuntimeError("teacher: failed to reach <url>: ...")`.

## Trust note

> Local models improve privacy and adoption, but they are still untrusted teachers.

Every proposed rule still has to pass `dtaifm review` before anything executes. The local adapters route output through the same translator → validator → runtime pipeline as the cloud adapter; the architectural contract holds regardless of where the proposal came from.

## Writing your own HTTP adapter

See [domains.md](domains.md) for the architectural rules, and read `dtaifm/teacher/adapters/ollama_adapter.py` for the smallest working example. The pattern is:

1. Subclass `Teacher`.
2. Accept `model`, `base_url`, `client`, `timeout` in `__init__`. Default the client to `HttpJsonClient`; tests inject a fake.
3. In `propose`, render the prompt via `self.render_prompt(request)`, POST it, extract the model's text, run it through `parse_provider_text(content, source="<your_name>")`.
4. Return a `TeacherResponse(ruleset=..., raw_provider_output=content)`.
5. Add a `**kwargs` factory in `dtaifm/teacher/registry.py`.
