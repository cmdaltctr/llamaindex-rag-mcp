"""Regression tests for per-backend storage summaries (task 2.6, design D5).

Spec source: openspec/changes/make-lancedb-default-and-isolate-chromadb
specs/config-composition-root/spec.md — the startup storage summary
belongs to the SELECTED store and dispatches through registry metadata,
never a store-name branch in the composition root.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from omrg.core.vectordb import registry
from omrg.core.vectordb.summary import storage_summary


@pytest.fixture(autouse=True)
def _purge_throwaway_registrations():
    """Remove ``_test_``-prefixed registrations after each test."""
    yield
    for name in [n for n in registry._registry if n.startswith("_test_")]:
        del registry._registry[name]
        registry._cache.pop(name, None)
        registry._metadata.pop(name, None)


def test_storage_summary_dispatches_registered_summary() -> None:
    """The selected store's registry metadata resolves the summary function."""
    settings = SimpleNamespace(vector_store="lancedb", lancedb_uri="/tmp/summary-check")
    assert storage_summary(settings) == "lancedb uri=/tmp/summary-check"


def test_storage_summary_falls_back_without_metadata() -> None:
    """A backend without a summary reference yields a plain message."""
    registry.register("_test_plain", "json:dumps")
    settings = SimpleNamespace(vector_store="_test_plain")
    assert storage_summary(settings) == "_test_plain storage configured"
