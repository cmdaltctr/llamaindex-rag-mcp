"""Clean-base install tripwire (task 5.4, make-lancedb-default-and-isolate-chromadb).

Proves the base environment contains neither Chroma distribution, that the
installed project metadata keeps both packages behind the ``chroma`` extra
marker, and that the default runtime path (settings → compose → retrieval)
never loads a Chroma module. The whole module skips when the ``chroma``
extra IS installed — the chroma-extra CI job runs the complement suite.
"""

from __future__ import annotations

import re
import subprocess
import sys
from importlib import import_module, metadata
from importlib.util import find_spec
from pathlib import Path

import pytest

_CHROMA_INSTALLED = find_spec("chromadb") is not None

pytestmark = pytest.mark.skipif(
    _CHROMA_INSTALLED,
    reason="chroma extra installed; this tripwire asserts the clean base install",
)

_CHROMA_DISTS = ("chromadb", "llama-index-vector-stores-chroma")

# ── Base-skip manifest (task 5.2) ─────────────────────────────────────
# The only sanctioned base skips are the named Chroma-gated files. These
# pinned counts come from a clean base install at
# make-lancedb-default-and-isolate-chromadb (commits 869105b..c73f9b4),
# measured via `uv sync --frozen` (the CI-equivalent base state); bump
# them only when the suite legitimately changes. The executed and
# skipped counts come from the self-ignored ``-rs`` run summary line.
_BASE_EXECUTED = 1603  # Includes Exp14, PDF-reader default, registry drift, and review-fix pins.
_BASE_SKIPPED = 83  # self-ignored run: skipped
_BASE_DESELECTED = 14  # -m "not slow" deselection
_CHROMA_GATED_FILES = frozenset(
    {
        "test_chroma_cloud.py",
        "test_compose.py",
        "test_experiment_storage.py",
        "test_hybrid_retrieval.py",
        "test_lancedb_store.py",
        "test_metadata_extractor.py",
        "test_vectordb_contract.py",
    }
)


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


def _base_suite_run() -> subprocess.CompletedProcess[str]:
    """Run the fast base suite in this environment, ignoring this module.

    The subprocess reuses the running interpreter so the assertion holds
    for the exact environment under test. This module is ignored to avoid
    recursing into itself.
    """
    root = Path(__file__).resolve().parent.parent
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-m",
            "not slow",
            "-q",
            "-rs",
            "--ignore=tests/test_clean_base_tripwire.py",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=1800,
    )


def test_base_skip_manifest_is_exact() -> None:
    """The clean-base suite pins its executed/skipped counts and Chroma guards.

    Task 5.2: the only sanctioned base skips are the named Chroma-gated
    files, and every one of those cases must run in the chroma-extra CI
    job (which fails if anything skips with the ``chroma extra not
    installed`` reason). The pinned counts come from the ``-rs`` summary
    line — always printed — while the Chroma-skip sources are asserted
    statically, because module-level ``importorskip`` output differs
    across invocation contexts and is not reliably parseable.
    """
    proc = _base_suite_run()
    assert proc.returncode == 0, f"base suite failed:\n{proc.stdout}\n{proc.stderr}"
    output = proc.stdout

    summary = re.search(r"(\d+) passed, (\d+) skipped, (\d+) deselected", output)
    assert summary, f"unparseable base suite summary:\n{output[-500:]}"
    passed, skipped, deselected = (int(v) for v in summary.groups())

    assert passed == _BASE_EXECUTED, f"base executed count drifted: {passed}"
    assert skipped == _BASE_SKIPPED, f"base skipped count drifted: {skipped}"
    assert deselected == _BASE_DESELECTED, f"base deselected count drifted: {deselected}"

    # Static guard check: every declared chroma-gated file must carry its
    # Chroma guard, and no other test file may name the chroma-extra skip
    # reason (a mis-scoped guard would leak that string elsewhere).
    tests_dir = Path(__file__).parent
    guarded: set[str] = set()
    for path in tests_dir.glob("test_*.py"):
        if path.name == Path(__file__).name:
            continue  # this manifest file mentions the reason in prose
        text = path.read_text(encoding="utf-8")
        if "chroma extra not installed" in text:
            guarded.add(path.name)
    missing = _CHROMA_GATED_FILES - guarded
    assert not missing, (
        f"declared chroma-gated files no longer carry their guard: {sorted(missing)}"
    )
    unexpected = guarded - _CHROMA_GATED_FILES
    assert not unexpected, (
        f"chroma-gated skip reason found outside the allowed files: {sorted(unexpected)}"
    )
