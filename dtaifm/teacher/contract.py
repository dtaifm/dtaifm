"""Provider-neutral teacher request/response contract.

All teachers — mock or real LLM adapters — accept a TeacherRequest and return
a TeacherResponse. The response carries a portable RuleSet artifact only.
No validation, no execution: that is the deterministic layer's job downstream.

Principle: provider adapters are translators, not trusted components.
Domains define what is possible; teachers only propose within that boundary.
For revision requests, deterministic feedback is attached so the teacher knows
exactly which previous rules failed, why, and what vocabulary it may use.
"""

from dataclasses import dataclass, field
from typing import Any, Optional

from dtaifm.core.constraint import Constraint
from dtaifm.core.ruleset import RuleSet
from dtaifm.domains.base import Domain
from dtaifm.schema import SCHEMA_VERSION
from dtaifm.teacher.feedback import TeacherFeedback


@dataclass
class PromptContext:
    """Domain context handed to a teacher when proposing rules.

    `domain` is the domain id as a free-form string (for prompt narration);
    the structural Domain object lives on TeacherRequest. `metadata` is a
    free-form bag for extra hints. Adapters should treat both as untrusted
    display strings.
    """

    domain: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TeacherRequest:
    """Everything a teacher needs to produce a candidate RuleSet."""

    constraints: list[Constraint]
    context: PromptContext = field(default_factory=PromptContext)
    schema_version: str = SCHEMA_VERSION
    # When set, the teacher receives the domain's full vocabulary in the prompt.
    domain: Optional[Domain] = None
    # When set, the teacher is being asked to revise a previous proposal. The
    # feedback carries deterministic violation reasons; previous_rules carries
    # the original rule artifacts so the teacher can preserve approved rules.
    feedback: Optional[TeacherFeedback] = None
    previous_rules: Optional[list[dict]] = None


@dataclass
class TeacherResponse:
    """A teacher's output, always in portable RuleSet form.

    `raw_provider_output` is kept for audit and debugging — it is NEVER used
    by the runtime. The runtime only sees the parsed, validator-approved RuleSet.
    """

    ruleset: RuleSet
    raw_provider_output: str = ""
