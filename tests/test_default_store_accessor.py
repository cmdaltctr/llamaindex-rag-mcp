"""TDD RED tests: the process-wide store accessor requires prior composition.

Spec source: openspec/changes/make-lancedb-default-and-isolate-chromadb

- specs/vector-store-registry/spec.md — 'Process-wide store access SHALL
  require prior composition' (access before/after composition).
- specs/config-composition-root/spec.md — 'compose.py SHALL remain the sole
  vector-store constructor' (the accessor must not construct, import, or
  name any concrete backend).

Written test-first: the pre-change accessor lazily builds a ChromaDB store,
so these are expected to FAIL (RED) until the change lands.
"""

from __future__ import annotations

import types
from pathlib import Path

import pytest

from omrg.core.vectordb import (
    get_default_store,
    reset_default_store,
    set_default_store,
)

_ACCESSOR_SOURCE = (
    Path(__file__).resolve().parents[1] / "src" / "omrg" / "core" / "vectordb" / "__init__.py"
)


@pytest.fixture(autouse=True)
def _reset_store_after_test():
    """Leave the process-wide slot empty whatever a test installed."""
    yield
    reset_default_store()


def test_access_before_composition_raises() -> None:
    """With no store installed the accessor raises instead of building one.

    Spec: vector-store-registry, scenario 'Access before composition' — the
    error must instruct the caller to run ``ensure_runtime_setup`` (compose
    or inject a store) and must not import or construct a backend.
    """
    reset_default_store()
    with pytest.raises(RuntimeError) as excinfo:
        get_default_store()
    assert "ensure_runtime_setup" in str(excinfo.value).lower()


def test_access_after_composition_returns_instance() -> None:
    """The accessor returns the exact instance installed by composition.

    Spec: vector-store-registry, scenario 'Access after composition'.
    ``set_default_store`` accepts any object, so a plain namespace stands
    in for a real store without touching the VectorStore ABC.
    """
    fake = types.SimpleNamespace(mark="fake-store")
    set_default_store(fake)
    assert get_default_store() is fake


def test_accessor_module_has_no_construction_imports() -> None:
    """The accessor module constructs, imports, and names no concrete store.

    Spec: config-composition-root, scenario 'Uncomposed process-wide
    access' — no backend module may be imported by the accessor, and the
    accessor module must not name either concrete backend.
    """
    source = _ACCESSOR_SOURCE.read_text()
    assert "from .chroma" not in source
    assert "import chromadb" not in source
    assert "build_chroma_vector_store" not in source
    assert "lancedb" not in source
