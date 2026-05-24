from dataclasses import dataclass, field
from typing import Any


@dataclass
class Trigger:
    device: str
    event: str


@dataclass
class Condition:
    type: str
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass
class Action:
    device: str
    action: str
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass
class Rule:
    id: str
    name: str
    trigger: Trigger
    actions: list[Action]
    conditions: list[Condition] = field(default_factory=list)
    satisfies_constraints: list[str] = field(default_factory=list)
    explanation: str = ""
    # Provenance — stamped by `dtaifm propose`; empty on hand-written rules.
    proposed_by: str = ""
    proposal_id: str = ""
    created_at: str = ""
    rationale: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "Rule":
        trigger = Trigger(device=data["trigger"]["device"], event=data["trigger"]["event"])
        actions = [
            Action(
                device=a["device"],
                action=a["action"],
                parameters={k: v for k, v in a.items() if k not in ("device", "action")},
            )
            for a in data.get("actions", [])
        ]
        conditions = [
            Condition(
                type=c["type"],
                parameters={k: v for k, v in c.items() if k != "type"},
            )
            for c in data.get("conditions", [])
        ]
        return cls(
            id=data["id"],
            name=data["name"],
            trigger=trigger,
            actions=actions,
            conditions=conditions,
            satisfies_constraints=data.get("satisfies_constraints", []),
            explanation=data.get("explanation", ""),
            proposed_by=data.get("proposed_by", ""),
            proposal_id=data.get("proposal_id", ""),
            created_at=data.get("created_at", ""),
            rationale=data.get("rationale", ""),
        )
