"""Clean-base install tripwire (task 5.4, make-lancedb-default-and-isolate-chromadb).

Proves the base environment contains neither Chroma distribution, that the
installed project metadata keeps both packages behind the ``chroma`` extra
marker, and that the default runtime path (settings → compose → retrieval)
never loads a Chroma module. The whole module skips when the ``chroma``
extra IS installed — the chroma-extra CI job runs the complement suite.
"""

from __future__ import annotations

from importlib import import_module, metadata
from importlib.util import find_spec

import pytest

_CHROMA_INSTALLED = find_spec("chromadb") is not None

pytestmark = pytest.mark.skipif(
    _CHROMA_INSTALLED,
    reason="chroma extra installed; this tripwire asserts the clean base install",
)

_CHROMA_DISTS = ("chromadb", "llama-index-vector-stores-chroma")


def _scrub_chroma_modules() -> list[str]:
    """Remove chromadb and its submodules from sys.modules; return names."""
    import sys

    names = [name for name in sys.modules if name == "chromadb" or name.startswith("chromadb.")]
    for name in names:
        del sys.modules[name]
    return names


def test_installed_distributions_exclude_chroma() -> None:
    """A base install must contain neither Chroma distribution."""
    installed = {dist.metadata["Name"].lower() for dist in metadata.distributions()}
    for dist in _CHROMA_DISTS:
        assert dist not in installed, f"{dist} is installed in the base environment"


def test_project_requires_keep_chroma_behind_extra_marker() -> None:
    """Built-package metadata must not declare Chroma as unconditional Requires-Dist.

    The wheel-level check (task 1.3) inspects the built artefact directly;
    this tripwire inspects the *installed* distribution metadata, which is
    what a fresh ``pip install rag-mcp`` environment resolves against.
    """
    requires = metadata.requires("rag-mcp") or []
    for req in requires:
        normalised = req.lower().replace("_", "-")
        assert not normalised.startswith("chromadb(") or "extra ==" in req, (
            f"unconditional chromadb requirement: {req}"
        )
        assert not normalised.startswith("llama-index-vector-stores-chroma") or (
            "extra ==" in req
        ), f"unconditional chroma-vector-store requirement: {req}"
    # And the extra-marked entries must exist.
    marked = [r for r in requires if "chromadb" in r.lower() and "extra ==" in r]
    assert marked, "expected a chromadb requirement behind the chroma extra marker"


def test_default_runtime_loads_no_chroma_modules() -> None:
    """Importing the default runtime path must not load any Chroma module."""
    _scrub_chroma_modules()
    import_module("rag_mcp.compose")
    import_module("rag_mcp.core.retrieval")
    import_module("rag_mcp.core.ingestion")

    import sys

    leaked = [name for name in sys.modules if name == "chromadb" or name.startswith("chromadb.")]
    assert not leaked, f"default runtime imported chroma modules: {leaked}"


def test_base_default_search_runs_without_chroma() -> None:
    """A search against an empty default collection returns [] with Chroma absent.

    Exercises the settings → store resolution → dense query path end to
    end (no results expected — the store is empty), proving the base
    install's default path is functional without the chroma extra.
    """
    _scrub_chroma_modules()
    from rag_mcp.core.retrieval import search

    results = search("tripwire query", top_k=3, hybrid=False)
    assert results == []

    import sys

    leaked = [name for name in sys.modules if name == "chromadb" or name.startswith("chromadb.")]
    assert not leaked, f"search imported chroma modules: {leaked}"
