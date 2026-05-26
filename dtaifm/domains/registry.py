"""Domain registry — name -> Domain lookup.

A domain becomes available three ways, all funneling through register_domain():

1. **Built-in packs** self-register as import side effects (see
   dtaifm/domains/__init__.py).
2. **Installed third-party packs** are auto-discovered from the ``dtaifm.domains``
   entry-point group (see _discover_entry_point_domains).
3. **Any caller** may register a Domain directly via register_domain() — e.g. a
   local module imported through the CLI's ``--domain-module`` flag.
"""

import warnings

from dtaifm.domains.base import Domain


ENTRY_POINT_GROUP = "dtaifm.domains"


class UnknownDomainError(ValueError):
    """Raised when an unrecognized domain id is requested."""


_DOMAINS: dict[str, Domain] = {}
_discovered = False


def register_domain(domain: Domain) -> None:
    _DOMAINS[domain.id] = domain


def _discover_entry_point_domains() -> None:
    """Load and register domains advertised under the ``dtaifm.domains`` group.

    Each entry point must resolve to a ``Domain`` instance or to a zero-argument
    callable returning one. Runs once per process. A broken third-party entry
    point is warned about and skipped — it must never break domain resolution.
    """
    global _discovered
    if _discovered:
        return
    _discovered = True  # set first: a failing scan must not retrigger on every lookup

    from importlib import metadata

    try:
        entry_points = metadata.entry_points(group=ENTRY_POINT_GROUP)
    except Exception as exc:  # pragma: no cover - defensive against metadata API quirks
        warnings.warn(
            f"dtaifm: could not read '{ENTRY_POINT_GROUP}' entry points: {exc}",
            RuntimeWarning, stacklevel=2,
        )
        return

    for ep in entry_points:
        try:
            obj = ep.load()
            domain = obj() if (callable(obj) and not isinstance(obj, Domain)) else obj
            if isinstance(domain, Domain):
                register_domain(domain)
            else:
                warnings.warn(
                    f"dtaifm: entry point '{ep.name}' ({ep.value}) did not yield a Domain; skipped",
                    RuntimeWarning, stacklevel=2,
                )
        except Exception as exc:  # noqa: BLE001 - a bad plugin must not break the CLI
            warnings.warn(
                f"dtaifm: failed to load domain entry point '{ep.name}': {exc}",
                RuntimeWarning, stacklevel=2,
            )


def get_domain(domain_id: str) -> Domain:
    if domain_id not in _DOMAINS:
        _discover_entry_point_domains()
    if domain_id not in _DOMAINS:
        raise UnknownDomainError(
            f"Unknown domain '{domain_id}'. Available: {sorted(_DOMAINS)}"
        )
    return _DOMAINS[domain_id]


def list_domains() -> list[str]:
    _discover_entry_point_domains()
    return sorted(_DOMAINS)


def domain_is_registered(domain_id: str) -> bool:
    if domain_id not in _DOMAINS:
        _discover_entry_point_domains()
    return domain_id in _DOMAINS
