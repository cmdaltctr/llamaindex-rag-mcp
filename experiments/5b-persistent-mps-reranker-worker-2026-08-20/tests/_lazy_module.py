"""Lazy module proxy for red-first tests (Experiment 5b, task 4.1).

Tests for not-yet-implemented harness modules must FAIL with an ImportError
now and pass once the module lands.  A module-level ``import`` would abort
pytest collection for the whole suite, hiding green tests from the
registered single command (``PYTHONPATH=../..:. uv run --no-sync pytest
tests/ -q``).  This proxy defers the import to first attribute access
inside each test: the missing module still raises ``ModuleNotFoundError``
(an ``ImportError`` subclass) per test, and implemented modules import
transparently.  It never skips or xfails anything.
"""

from __future__ import annotations

import importlib
from types import ModuleType
from typing import Any


class LazyModule:
    """Resolve the named experiment module on first attribute access."""

    def __init__(self, name: str) -> None:
        self._name = name
        self._module: ModuleType | None = None

    def __getattr__(self, attr: str) -> Any:
        if self._module is None:
            self._module = importlib.import_module(self._name)
        return getattr(self._module, attr)

    def __setattr__(self, attr: str, value: Any) -> None:
        """Forward writes to the real module so monkeypatch reaches it."""
        if attr in ("_name", "_module"):
            object.__setattr__(self, attr, value)
            return
        if self._module is None:
            self._module = importlib.import_module(self._name)
        setattr(self._module, attr, value)

    def __delattr__(self, attr: str) -> None:
        if self._module is None:
            self._module = importlib.import_module(self._name)
        delattr(self._module, attr)
