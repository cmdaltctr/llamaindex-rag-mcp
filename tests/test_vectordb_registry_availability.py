"""TDD RED tests: registry availability metadata and sparse capability.

Spec source: openspec/changes/make-lancedb-default-and-isolate-chromadb

- specs/vector-store-registry/spec.md — availability SHALL be registry
  metadata (unknown/absent/partial/broken) with generic, branch-free
  dispatch, and sparse capability SHALL follow the selected store.
- specs/chroma-cloud-backend/spec.md — Chroma requires the optional extra;
  composition must never fall back to LanceDB when Chroma is selected but
  uninstalled.

Written test-first: the registry currently exposes only
``register/get/available`` with no availability metadata, so most tests
here FAIL (RED) on the missing API until the change lands.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

from rag_mcp.compose import build_vector_store, resolve_sparse_backend
from rag_mcp.config import Settings
from rag_mcp.core.vectordb import registry

_REPO_ROOT = Path(__file__).resolve().parents[1]
_COMPOSE_SOURCE = _REPO_ROOT / "src" / "rag_mcp" / "compose.py"


@pytest.fixture(autouse=True)
def _purge_throwaway_registrations():
    """Remove ``_test_``-prefixed registrations after each test.

    The conftest cache-clear fixture only clears ``_cache``; a registration
    made here must not leak into other tests in the session.
    """
    yield
    try:
        for name in [n for n in registry._registry if n.startswith("_test_")]:
            del registry._registry[name]
            registry._cache.pop(name, None)
    except AttributeError:
        # Best-effort hygiene: never mask a real test failure.
        pass


def _scrub_chroma_from_sys_modules(monkeypatch: pytest.MonkeyPatch) -> None:
    """Drop every chroma-related module from sys.modules (restored on teardown).

    Covers chromadb itself plus the two wrapper modules that import it at
    module top level, so a later re-import is a genuine fresh import.
    """
    prefixes = (
        "chromadb",
        "rag_mcp.core.vectordb.chroma",
        "llama_index.vector_stores.chroma",
    )
    for key in list(sys.modules):
        if any(key == p or key.startswith(p + ".") for p in prefixes):
            monkeypatch.delitem(sys.modules, key, raising=False)


def _chroma_modules_loaded() -> list[str]:
    """Return the chromadb top-level/submodule keys currently loaded."""
    return [k for k in sys.modules if k == "chromadb" or k.startswith("chromadb.")]


def test_unknown_backend_reports_unknown() -> None:
    """Unregistered names report 'unknown' and composition fails with names listed.

    Spec: vectordb-abstraction, scenario 'Unknown store value'.
    """
    assert registry.availability("nope") == "unknown"
    with pytest.raises(ValueError) as excinfo:
        build_vector_store(Settings(vector_store="nope"))
    assert "nope" in str(excinfo.value)


def test_absent_backend_error_names_extra_and_packages() -> None:
    """An absent backend's ImportError names backend, packages, extra, and hint.

    Spec: vector-store-registry, scenario 'Optional backend is absent'.
    """
    registry.register(
        "_test_absent",
        "fakepkg_absent_xyz_mod:build",
        requires={"fakepkg_absent_xyz": "fakepkg-absent-xyz"},
        extra="fake",
        install_hint="install with rag-mcp[fake]",
    )
    assert registry.availability("_test_absent") == "absent"
    with pytest.raises(ImportError) as excinfo:
        registry.verify_available("_test_absent")
    message = str(excinfo.value)
    assert "_test_absent" in message
    assert "fakepkg_absent_xyz" in message
    assert "fakepkg-absent-xyz" in message
    assert "fake" in message
    assert "rag-mcp[fake]" in message


def test_partial_backend_detected() -> None:
    """Some declared packages present and some absent reports 'partial'.

    Spec: vector-store-registry, scenario 'Optional backend is partially
    installed' — the error names the partial installation.
    """
    registry.register(
        "_test_partial",
        "fakepkg_absent_xyz_mod:build",
        requires={
            "json": "stdlib-json-ok",
            "fakepkg_absent_xyz": "fakepkg-absent-xyz",
        },
        extra="fake",
    )
    assert registry.availability("_test_partial") == "partial"
    with pytest.raises(ImportError) as excinfo:
        registry.verify_available("_test_partial")
    assert "partial" in str(excinfo.value).lower()


def test_broken_backend_preserves_cause(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A factory module that raises on import reports 'broken' with the cause.

    Spec: vector-store-registry, scenario 'Factory import fails' — the
    original exception is retained as diagnostic context.
    """
    (tmp_path / "broken_test_mod.py").write_text("raise RuntimeError('boom-origin')\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    registry.register("_test_broken", "broken_test_mod:factory")
    assert registry.availability("_test_broken") == "broken"
    with pytest.raises(ImportError) as excinfo:
        registry.verify_available("_test_broken")
    cause = excinfo.value.__cause__
    diagnosed = str(excinfo.value) + (f" {cause}" if cause is not None else "")
    assert "boom-origin" in diagnosed


def test_registry_entries_declare_metadata() -> None:
    """Built-in entries declare import paths, requirements, extras, and probes.

    Spec: vector-store-registry — availability SHALL be registry metadata;
    the sparse capability probe is entry metadata (None for lancedb).
    """
    chroma = registry.describe("chroma")
    assert chroma["requires"]["chromadb"] == "chromadb"
    assert (
        chroma["requires"]["llama_index.vector_stores.chroma"] == "llama-index-vector-stores-chroma"
    )
    assert chroma["extra"] == "chroma"
    assert chroma["native_sparse_probe"]

    lancedb = registry.describe("lancedb")
    assert lancedb["extra"] is None
    assert lancedb["requires"]["lancedb"] == "lancedb"
    assert lancedb["native_sparse_probe"] is None


def test_dispatch_has_no_store_name_branch() -> None:
    """The composition root dispatches by registry lookup, never by name branch.

    Spec: vectordb-abstraction — 'Selection SHALL be a registry lookup,
    not a branch over store names.'
    """
    source = _COMPOSE_SOURCE.read_text()
    assert '== "chroma"' not in source
    assert '== "lancedb"' not in source
    assert "== 'chroma'" not in source
    assert "== 'lancedb'" not in source


def test_explicit_chroma_without_extra_fails_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Selected-but-unimportable Chroma fails composition; no LanceDB fallback.

    Spec: chroma-cloud-backend, scenario 'Chroma backend without the
    complete extra'. ``sys.modules['chromadb'] = None`` makes any import
    of chromadb raise ImportError, simulating the absent extra without
    patching registry internals.
    """
    _scrub_chroma_from_sys_modules(monkeypatch)
    monkeypatch.setitem(sys.modules, "chromadb", None)
    with pytest.raises((ImportError, ModuleNotFoundError, RuntimeError, ValueError)) as excinfo:
        build_vector_store(Settings(vector_store="chroma"))
    assert "lancedb" not in str(excinfo.value).lower()


def test_sparse_capability_follows_selected_store(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Sparse capability follows the SELECTED store, not the installed extras.

    Spec: vector-store-registry, scenarios 'LanceDB selected while Chroma
    extra is installed' and 'Chroma-only native mode is requested for
    LanceDB'.
    """
    # (a) lancedb + auto resolves bm25 even though chromadb is importable
    # in this environment — selection, not installation, decides.
    auto_settings = Settings(
        vector_store="lancedb",
        retrieval={"hybrid_sparse_backend": "auto"},
    )
    assert resolve_sparse_backend(auto_settings) == "bm25"

    # (b) lancedb + native falls back to bm25 with a warning and never
    # probes Chroma: scrub every chroma module, resolve, assert none
    # reappeared.
    _scrub_chroma_from_sys_modules(monkeypatch)
    assert _chroma_modules_loaded() == []
    native_settings = Settings(
        vector_store="lancedb",
        retrieval={"hybrid_sparse_backend": "native"},
    )
    with caplog.at_level(logging.WARNING):
        assert resolve_sparse_backend(native_settings) == "bm25"
    assert _chroma_modules_loaded() == []
    assert any(record.levelno >= logging.WARNING for record in caplog.records)

    # (c) Explicit bm25 short-circuits regardless of the selected backend.
    bm25_settings = Settings(
        vector_store="chroma",
        retrieval={"hybrid_sparse_backend": "bm25"},
    )
    assert resolve_sparse_backend(bm25_settings) == "bm25"
