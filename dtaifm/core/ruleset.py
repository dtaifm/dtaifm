from dataclasses import dataclass, field
from dtaifm.core.rule import Rule


@dataclass
class RuleSet:
    rules: list[Rule] = field(default_factory=list)
    source: str = "unknown"

    def add(self, rule: Rule) -> None:
        self.rules.append(rule)

    def __len__(self) -> int:
        return len(self.rules)

    def __iter__(self):
        return iter(self.rules)
