"""Tests for #9: external/custom domain discovery.

Covers the two supported mechanisms — installed-package entry points
(`dtaifm.domains` group) and the `--domain-module` CLI flag — plus a clear
error when an unknown domain is requested.
"""

import sys
import textwrap
from pathlib import Path

import pytest

from dtaifm.cli import main
from dtaifm.domains import registry
from dtaifm.domains.base import Domain


EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "smart_rules"
CONSTRAINTS = str(EXAMPLES / "constraints.yaml")
RULES = str(EXAMPLES / "rules.yaml")


def _make_domain(domain_id: str) -> Domain:
    return Domain(
        id=domain_id,
        version="0.1",
        description="test domain",
        trigger_events=frozenset({"ping"}),
        condition_types=frozenset({"time_range"}),
        action_kinds=frozenset({"notify"}),
    )


class _FakeEntryPoint:
    def __init__(self, name, value, target):
        self.name = name
        self.value = value
        self.group = registry.ENTRY_POINT_GROUP
        self._target = target

    def load(self):
        return self._target


@pytest.fixture
def reset_discovery():
    """Force entry-point discovery to re-run for this test and clean up after."""
    saved = registry._discovered
    before = set(registry._DOMAINS)
    registry._discovered = False
    try:
        yield
    finally:
        for k in set(registry._DOMAINS) - before:
            registry._DOMAINS.pop(k, None)
        registry._discovered = saved


def _patch_entry_points(monkeypatch, eps):
    monkeypatch.setattr(
        "importlib.metadata.entry_points",
        lambda **kw: list(eps) if kw.get("group") == registry.ENTRY_POINT_GROUP else [],
    )


# ----------------------------------------------------------------------
# Entry-point discovery
# ----------------------------------------------------------------------

def test_entry_point_resolving_to_domain_object_is_discovered(monkeypatch, reset_discovery):
    dom = _make_domain("__ep_object__")
    _patch_entry_points(monkeypatch, [_FakeEntryPoint("ep_object", "pkg.mod:DOMAIN", dom)])
    assert "__ep_object__" in registry.list_domains()
    assert registry.get_domain("__ep_object__") is dom


def test_entry_point_resolving_to_callable_is_discovered(monkeypatch, reset_discovery):
    dom = _make_domain("__ep_callable__")
    _patch_entry_points(monkeypatch, [_FakeEntryPoint("ep_callable", "pkg.mod:build", lambda: dom)])
    assert registry.get_domain("__ep_callable__") is dom


def test_broken_entry_point_is_warned_and_skipped(monkeypatch, reset_discovery):
    good = _make_domain("__ep_good__")

    class _Boom:
        name = "boom"
        value = "pkg:explode"
        group = registry.ENTRY_POINT_GROUP

        def load(self):
            raise RuntimeError("kaboom")

    _patch_entry_points(monkeypatch, [_Boom(), _FakeEntryPoint("ep_good", "pkg:DOMAIN", good)])
    with pytest.warns(RuntimeWarning):
        domains = registry.list_domains()
    assert "__ep_good__" in domains  # the good one still loaded despite the broken one


def test_entry_point_yielding_non_domain_is_skipped(monkeypatch, reset_discovery):
    _patch_entry_points(monkeypatch, [_FakeEntryPoint("bad", "pkg:NOT_A_DOMAIN", "just a string")])
    with pytest.warns(RuntimeWarning):
        registry.list_domains()  # does not raise


def test_discovery_runs_only_once(monkeypatch, reset_discovery):
    calls = {"n": 0}

    def counting(**kw):
        calls["n"] += 1
        return []

    monkeypatch.setattr("importlib.metadata.entry_points", counting)
    registry.list_domains()
    registry.list_domains()
    registry.get_domain("smart_home")
    assert calls["n"] == 1  # cached after first discovery


# ----------------------------------------------------------------------
# --domain-module
# ----------------------------------------------------------------------

def test_domain_module_flag_loads_custom_domain(tmp_path, monkeypatch, capsys):
    mod = tmp_path / "mylocaldomain.py"
    mod.write_text(textwrap.dedent('''
        from dtaifm.domains.base import Domain
        from dtaifm.domains.registry import register_domain

        register_domain(Domain(
            id="__local_dom__",
            version="0.1",
            trigger_events=frozenset({"ping"}),
            condition_types=frozenset({"time_range"}),
            action_kinds=frozenset({"notify"}),
        ))
    '''))
    monkeypatch.syspath_prepend(str(tmp_path))
    try:
        rc = main([
            "prompt", CONSTRAINTS,
            "--teacher", "mock",
            "--domain", "__local_dom__",
            "--domain-module", "mylocaldomain",
        ])
        assert rc == 0
        assert "__local_dom__" in capsys.readouterr().out
    finally:
        registry._DOMAINS.pop("__local_dom__", None)
        sys.modules.pop("mylocaldomain", None)


def test_domain_module_bad_value_fails_clearly(capsys):
    rc = main([
        "prompt", CONSTRAINTS,
        "--teacher", "mock",
        "--domain", "smart_home",
        "--domain-module", "no.such.module__xyz",
    ])
    assert rc == 2
    err = capsys.readouterr().err
    assert "--domain-module" in err
    assert "no.such.module__xyz" in err


# ----------------------------------------------------------------------
# Unknown-domain error
# ----------------------------------------------------------------------

def test_unknown_domain_error_lists_available(capsys):
    rc = main(["validate", CONSTRAINTS, RULES, "--domain", "__nope__"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "Unknown domain '__nope__'" in err
    assert "smart_home" in err  # the error names what IS available
