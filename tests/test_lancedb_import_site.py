"""Import-site and dependency boundaries for the LanceDB backend.

Guards two ``lancedb-vector-store`` spec scenarios:

* **Single lancedb import site** — a direct ``import lancedb`` /
  ``from lancedb`` may appear only in modules under ``core/vectordb/``.
  ``from llama_index.vector_stores.lancedb import ...`` is a
  llama_index module and must NOT be flagged; the regex anchors
  ``lancedb`` immediately after the ``import``/``from`` keyword so the
  adapter import can never match.
* **No PyTorch on the base path** — importing the registry and the
  filter translator (the modules a default retrieval path touches
  before any store is constructed) must not pull ``torch`` into
  ``sys.modules`` (ONNX-only hard boundary).
"""

from __future__ import annotations

import re
import subprocess
import sys
import textwrap
from pathlib import Path

_SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "rag_mcp"

# Matches ``import lancedb`` / ``import lancedb.expr`` / ``from lancedb
# import ...`` at the start of a line (leading whitespace allowed).
# ``from llama_index.vector_stores.lancedb`` does not match because the
# text between ``from`` and ``lancedb`` is not just whitespace.
_DIRECT_LANCEDB_IMPORT = re.compile(r"^\s*(?:import|from)\s+lancedb\b", re.MULTILINE)


def test_lancedb_imports_confined_to_vectordb() -> None:
    """Every direct ``lancedb`` import must live under ``core/vectordb/``."""
    offenders: list[str] = []
    for path in sorted(_SRC_ROOT.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        if _DIRECT_LANCEDB_IMPORT.search(source):
            rel = path.relative_to(_SRC_ROOT).as_posix()
            if not rel.startswith("core/vectordb/"):
                offenders.append(rel)
    assert not offenders, (
        f"Direct lancedb imports found outside core/vectordb/: {offenders}. "
        "Only the vector-store layer may import lancedb directly."
    )


def test_regex_ignores_llama_index_adapter_import() -> None:
    """The llama_index LanceDB adapter must not count as a direct import.

    Regression guard for the confinement regex itself: if someone
    weakens it, this test fails before the real boundary silently
    starts blocking legitimate adapter imports.
    """
    assert not _DIRECT_LANCEDB_IMPORT.search(
        "from llama_index.vector_stores.lancedb import LanceDBVectorStore\n"
    )
    # …while genuine direct imports still match.
    assert _DIRECT_LANCEDB_IMPORT.search("import lancedb\n")
    assert _DIRECT_LANCEDB_IMPORT.search("from lancedb.expr import col\n")


def test_registry_and_filter_imports_stay_torch_free() -> None:
    """Importing the registry and filter translator must not import torch.

    Runs in a fresh interpreter: an in-process variant could be fooled
    by ``sys.modules`` caching when another test imported the modules
    first — the import would be a cache hit and never re-executed, so
    a ``torch`` import added at module top level would go unnoticed.
    """
    program = textwrap.dedent(
        """
        import importlib
        import sys

        importlib.import_module("rag_mcp.core.vectordb.registry")
        importlib.import_module("rag_mcp.core.vectordb.lance_filter")

        assert "torch" not in sys.modules, "torch leaked onto the base import path"
        """
    )
    proc = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (
        "Importing the vector-store registry or the LanceDB filter translator "
        f"pulled torch into the process; the base path is ONNX-only. stderr: {proc.stderr}"
    )
