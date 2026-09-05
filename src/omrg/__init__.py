"""omrg — a retrieval framework with MCP, CLI and watcher transports.

Public API: ``Engine``, ``EffectiveSettings``, ``__version__``.
Importing this package constructs nothing — no settings are resolved,
no providers or stores are constructed, and no process-global state is
mutated. Use ``Engine.from_environment()`` or ``compose.build_engine()``
to construct an engine with resolved dependencies.
"""

from __future__ import annotations

import importlib.metadata

__all__ = ["Engine", "EffectiveSettings", "__version__"]


def __getattr__(name: str):
    """Lazy attribute access (PEP 562) so importing the package constructs nothing."""
    if name == "Engine":
        from .engine import Engine

        return Engine
    if name == "EffectiveSettings":
        from .core.settings import EffectiveSettings

        return EffectiveSettings
    if name == "__version__":
        return importlib.metadata.version("omrg")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    """Support ``dir(omrg)`` for PEP 562 lazy attributes."""
    return sorted(__all__ + list(globals().keys()))
