from dtaifm.domains.base import Domain, ConstraintEvaluator
from dtaifm.domains.registry import (
    UnknownDomainError,
    domain_is_registered,
    get_domain,
    list_domains,
    register_domain,
)

# Trigger registration side-effects for the built-in domain packs so that
# `import dtaifm` is enough to make them discoverable.
from dtaifm.domains import smart_home as _smart_home  # noqa: F401, E402
from dtaifm.domains import network_automation as _network_automation  # noqa: F401, E402

__all__ = [
    "Domain",
    "ConstraintEvaluator",
    "UnknownDomainError",
    "domain_is_registered",
    "get_domain",
    "list_domains",
    "register_domain",
]
