# Where dtaifm fits in the landscape

dtaifm overlaps with several existing categories. This page is a factual map — what each category does well, where it overlaps with dtaifm, and where dtaifm differs. The point is to help you decide whether dtaifm is the right tool for your problem, not to argue any other tool is wrong.

## Raw LLM agents (no validation layer)

*Examples: home-grown agent loops, naive function-calling, "let the model decide" architectures.*

| | |
|---|---|
| **What they do well** | Maximum flexibility; the model can attempt anything you let it. |
| **Overlap with dtaifm** | Both involve a model producing actions to take. |
| **Where dtaifm differs** | A raw agent's output IS the action. In dtaifm, the model's output is an artifact that a deterministic layer reviews against named constraints. The model cannot bypass the validator; the validator cannot be re-trained by the model. |
| **When to use which** | Use a raw agent for low-stakes exploration, prototyping, or chat experiences. Use dtaifm when a wrong action costs more than no action. |

## Workflow engines

*Examples: Temporal, Airflow, Prefect, Step Functions, Argo Workflows.*

| | |
|---|---|
| **What they do well** | Orchestrating long-running, multi-step pipelines with retries, scheduling, durability, and visibility across teams. |
| **Overlap with dtaifm** | Both care about reproducibility and audit trails. |
| **Where dtaifm differs** | Workflow engines orchestrate steps you wrote. dtaifm validates rules an AI proposes against rules a human wrote. Different layer of the stack. They compose: a workflow engine can invoke `dtaifm review` as one step in a pipeline. |
| **When to use which** | Use a workflow engine for the overall job graph. Use dtaifm inside a step that decides what to do based on AI-generated logic. |

## Guardrail libraries

*Examples: Guardrails AI, NeMo Guardrails, Rebuff, LlamaGuard.*

| | |
|---|---|
| **What they do well** | Filtering or shaping individual LLM responses against content policies, output schemas, or safety classifiers — usually one prompt-and-response at a time. |
| **Overlap with dtaifm** | Both put a check between an LLM and downstream effects. |
| **Where dtaifm differs** | Guardrails typically validate the *shape and content of a response*. dtaifm validates the *behavior of proposed rules over time*: a rule isn't just a string, it's a `(trigger, conditions, actions)` triple checked against named domain constraints. dtaifm also seals the result into a replayable bundle and supports a reproposal loop driven by deterministic feedback. |
| **When to use which** | Use a guardrail library when you need turn-by-turn output filtering. Use dtaifm when the AI is proposing automation logic that will fire later against real events. They are compatible: a guardrail can wrap the LLM call inside a dtaifm teacher adapter. |

## Policy engines

*Examples: Open Policy Agent (OPA / Rego), Casbin, Cedar, Sentinel.*

| | |
|---|---|
| **What they do well** | Centralized, deterministic policy decisions ("is this request allowed?") expressed in a dedicated language, decoupled from application code. |
| **Overlap with dtaifm** | Both gate actions deterministically against human-authored policy. |
| **Where dtaifm differs** | Policy engines decide on actions you formulate. dtaifm decides on *rules an AI formulated*, including a feedback path that explains rejections back to the AI so it can revise. A dtaifm constraint is closer to a policy engine policy; a dtaifm rule is closer to "the thing the application wanted to do." |
| **When to use which** | Use a policy engine when humans (or services) author the requests and you need policy decisions across many systems. Use dtaifm when the requests themselves come from an AI proposer that needs a deterministic reviewer in the loop. They compose: a policy engine can be the body of a dtaifm constraint evaluator, or vice versa. |

## LLM orchestration frameworks

*Examples: LangChain, LlamaIndex, DSPy, Haystack.*

| | |
|---|---|
| **What they do well** | Chains, agents, retrieval, memory, multi-provider abstraction, prompt templating, tool calling. |
| **Overlap with dtaifm** | Both abstract over multiple LLM providers. |
| **Where dtaifm differs** | Orchestration frameworks help you *build* the LLM call. dtaifm is what happens *after* the LLM produces an artifact: a deterministic gate, a portable bundle, and a replayable audit. dtaifm's teacher adapters intentionally do one thing (return a portable RuleSet); the orchestration of how that teacher gets called — caching, retries, fallback providers — is somebody else's job. |
| **When to use which** | Use an orchestration framework when you're composing LLM calls. Use dtaifm when those calls produce automation rules that need to be ratified before anything runs. They compose: a LangChain pipeline can call `dtaifm.review(...)` as its final, authoritative step. |

## Quick decision guide

- Want to **build the LLM call**? Use an orchestration framework.
- Want to **filter a single response**? Use a guardrail library.
- Want to **decide if a user request is allowed**? Use a policy engine.
- Want to **orchestrate a long pipeline**? Use a workflow engine.
- Want the AI to **propose rules that automatically run later**, with a deterministic reviewer in the loop and a replayable audit on every decision? That's what dtaifm is for.

## The trust-boundary test

A clarifying question whenever you're evaluating tools in this space:

> **Can the AI's output reach an effect without passing a deterministic check authored by a human?**

If yes, you're in raw-agent territory; the tool is offering convenience, not safety. If no, you're in dtaifm's territory — the question is just whether the deterministic check is rich enough for your domain, and whether the audit it produces meets your reproducibility needs.
