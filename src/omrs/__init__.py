"""omrs — a retrieval framework with MCP, CLI and watcher transports.

Public API: ``Engine``, ``EffectiveSettings``, the graph types
``PipelineDefinition``, ``PipelineResult``, ``PipelineEvent`` and
``PipelineValidationError``, and ``__version__``. Names absent from
``__all__`` are internal.
Importing this package constructs nothing — no settings are resolved,
no providers or stores are constructed, and no process-global state is
mutated. Use ``Engine.from_environment()`` or ``compose.build_engine()``
to construct an engine with resolved dependencies.
"""

from __future__ import annotations

import importlib.metadata

__all__ = [
    "Engine",
    "EffectiveSettings",
    "PipelineDefinition",
    "PipelineResult",
    "PipelineEvent",
    "PipelineValidationError",
    "__version__",
]

# Graph types: public name -> defining module under omrs.core.pipelines.
_PIPELINE_EXPORTS = {
    "PipelineDefinition": "models",
    "PipelineResult": "results",
    "PipelineEvent": "results",
    "PipelineValidationError": "errors",
}


def __getattr__(name: str):
    """Lazy attribute access (PEP 562) so importing the package constructs nothing."""
    if name == "Engine":
        from .engine import Engine

        return Engine
    if name == "EffectiveSettings":
        from .core.settings import EffectiveSettings

        return EffectiveSettings
    if name in _PIPELINE_EXPORTS:
        module = importlib.import_module(f".core.pipelines.{_PIPELINE_EXPORTS[name]}", __name__)
        return getattr(module, name)
    if name == "__version__":
        return importlib.metadata.version("omrs")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    """Support ``dir(omrs)`` for PEP 562 lazy attributes."""
    return sorted(__all__ + list(globals().keys()))
