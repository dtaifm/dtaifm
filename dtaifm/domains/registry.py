"""Domain registry — name -> Domain lookup.

Domains are eagerly registered via side effects when their sub-package is
imported (see dtaifm/domains/__init__.py). External callers can plug in new
domains by calling register_domain() at any time.
"""

from dtaifm.domains.base import Domain


class UnknownDomainError(ValueError):
    """Raised when an unrecognized domain id is requested."""


_DOMAINS: dict[str, Domain] = {}


def register_domain(domain: Domain) -> None:
    _DOMAINS[domain.id] = domain


def get_domain(domain_id: str) -> Domain:
    if domain_id not in _DOMAINS:
        raise UnknownDomainError(
            f"Unknown domain '{domain_id}'. Available: {sorted(_DOMAINS)}"
        )
    return _DOMAINS[domain_id]


def list_domains() -> list[str]:
    return sorted(_DOMAINS)


def domain_is_registered(domain_id: str) -> bool:
    return domain_id in _DOMAINS
