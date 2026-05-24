"""Teacher registry — name -> factory lookup.

Factories accept ``**kwargs`` so the CLI can thread options (``model``,
``base_url``) through uniformly. Built-in factories use only the keys they
care about and ignore the rest. The mock teacher is always available; cloud
and local adapters import their backing modules lazily so the core install
has no provider dependencies.
"""

from typing import Any, Callable

from dtaifm.teacher.base import Teacher
from dtaifm.teacher.mock_teacher import MockTeacher


class UnknownTeacherError(ValueError):
    """Raised when an unrecognized teacher name is requested."""


TeacherFactory = Callable[..., Teacher]


_TEACHERS: dict[str, TeacherFactory] = {}


def register_teacher(name: str, factory: TeacherFactory) -> None:
    """Register a teacher factory under a short name.

    Factories should accept ``**kwargs`` and may consume ``model`` and
    ``base_url``. They must ignore unknown options (typically via ``**_``).
    """
    _TEACHERS[name] = factory


def get_teacher(name: str, **options: Any) -> Teacher:
    if name not in _TEACHERS:
        raise UnknownTeacherError(
            f"Unknown teacher '{name}'. Available: {sorted(_TEACHERS)}"
        )
    return _TEACHERS[name](**options)


def available_teachers() -> list[str]:
    return sorted(_TEACHERS)


def teacher_is_registered(name: str) -> bool:
    return name in _TEACHERS


# ----------------------------------------------------------------------
# Built-in factories (lazy imports for optional / local adapters)
# ----------------------------------------------------------------------

def _make_mock(**_: Any) -> Teacher:
    return MockTeacher()


def _make_anthropic(*, model: str | None = None, **_: Any) -> Teacher:
    from dtaifm.teacher.adapters.anthropic_adapter import AnthropicTeacher
    return AnthropicTeacher(model=model)


def _make_ollama(*, model: str | None = None, base_url: str | None = None, **_: Any) -> Teacher:
    from dtaifm.teacher.adapters.ollama_adapter import OllamaTeacher
    return OllamaTeacher(model=model, base_url=base_url)


def _make_lemonade(*, model: str | None = None, base_url: str | None = None, **_: Any) -> Teacher:
    from dtaifm.teacher.adapters.lemonade_adapter import LemonadeTeacher
    return LemonadeTeacher(model=model, base_url=base_url)


register_teacher("mock", _make_mock)
register_teacher("anthropic", _make_anthropic)
register_teacher("ollama", _make_ollama)
register_teacher("lemonade", _make_lemonade)
