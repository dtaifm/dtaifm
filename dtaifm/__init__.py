"""dtaifm — Deterministic-first Teaching AI Framework Middleware.

AI proposes. The deterministic layer disposes.
"""

# Framework version is read by dtaifm.bundle (and by tests); set it BEFORE the
# bundle re-exports so that `from dtaifm import __version__` inside bundle.py
# resolves on the partially-loaded package.
__version__ = "0.1.3"

# Public Python API. The CLI is a thin wrapper over these functions.
from dtaifm.bundle import (  # noqa: E402
    inspect_bundle,
    replay,
    review,
)

__all__ = [
    "__version__",
    "review",
    "replay",
    "inspect_bundle",
]
