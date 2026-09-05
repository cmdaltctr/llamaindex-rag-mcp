"""Grounded answering — turning retrieved chunks into cited answers.

The package's public surface is the async ``answer`` operation; it is
imported lazily (PEP 562 ``__getattr__``, the established registry
pattern) so importing ``omrg.core.answer`` costs nothing until the
operation is actually used — keeping discovery and test collection free
of the LlamaIndex synthesis imports.
"""

from __future__ import annotations

from typing import Any


def __getattr__(name: str) -> Any:
    """Lazily resolve ``answer`` (and submodules) on first access."""
    if name == "answer":
        from .pipeline import answer

        return answer
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["answer"]
