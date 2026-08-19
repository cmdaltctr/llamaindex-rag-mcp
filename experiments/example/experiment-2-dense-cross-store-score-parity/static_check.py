"""Static backend-opacity evidence for Experiment 2 hypothesis H5.

Protocol §2 H5 claims "core dense retrieval requires no backend-name
branch or native-distance interpretation".  This module records STATIC
evidence for that claim as a raw artefact:

1. An AST scan of ``src/rag_mcp/core/retrieval/dense.py`` asserting no
   string constant mentions a vector-store backend name and no
   subscript/attribute access reads ``native_distance``.
2. A citation scan of both adapters proving the native-distance-to-
   canonical-score conversion lives at the adapter boundary
   (``canonical_score_from_l2`` call sites) and that the canonical
   score kind is defined once in ``core/vectordb/score.py``.
3. A call-graph note that ``dense.py`` reaches stores only through the
   abstract ``store.query_dense`` seam.

The check is deliberately text/AST based so it stays loadable without
any store, model, or network.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DENSE_PY = PROJECT_ROOT / "src" / "rag_mcp" / "core" / "retrieval" / "dense.py"
ADAPTER_FILES = {
    "chroma": PROJECT_ROOT / "src" / "rag_mcp" / "core" / "vectordb" / "chroma.py",
    "lancedb": PROJECT_ROOT / "src" / "rag_mcp" / "core" / "vectordb" / "lancedb.py",
}
SCORE_PY = PROJECT_ROOT / "src" / "rag_mcp" / "core" / "vectordb" / "score.py"

_BACKEND_TOKENS = ("chroma", "lance")


def scan_dense_opacity() -> dict[str, Any]:
    """Return the static H5 evidence record for ``dense.py``.

    The record is JSON-serialisable so the harness can persist it as a
    raw artefact and the summariser can turn it into a verdict.

    H5 forbids backend BRANCHING and native-distance INTERPRETATION, so
    the string scan flags backend-name tokens only in executable string
    constants.  Docstring prose mentions are not control flow; they are
    recorded transparently under ``docstring_backend_mentions`` without
    failing the check.
    """
    source = DENSE_PY.read_text(encoding="utf-8")
    tree = ast.parse(source)

    docstring_nodes: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", None)
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                docstring_nodes.add(id(body[0].value))

    backend_literals: list[str] = []
    docstring_mentions: list[str] = []
    native_distance_accesses: list[int] = []
    query_dense_calls = 0

    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if any(token in node.value.lower() for token in _BACKEND_TOKENS):
                if id(node) in docstring_nodes:
                    docstring_mentions.append(node.value)
                else:
                    backend_literals.append(node.value)
        if isinstance(node, ast.Attribute) and node.attr == "native_distance":
            native_distance_accesses.append(node.lineno)
        if isinstance(node, ast.Subscript):
            slug = ast.unparse(node).replace(" ", "")
            if "native_distance" in slug:
                native_distance_accesses.append(node.lineno)
        if isinstance(node, ast.Attribute) and node.attr == "query_dense":
            query_dense_calls += 1

    adapter_citation: dict[str, Any] = {}
    for backend, path in ADAPTER_FILES.items():
        text = path.read_text(encoding="utf-8")
        adapter_citation[backend] = {
            "canonical_score_from_l2_calls": text.count("canonical_score_from_l2("),
            "dense_score_kind_import": "DENSE_SCORE_KIND" in text,
        }
    score_text = SCORE_PY.read_text(encoding="utf-8")

    failures: list[str] = []
    if backend_literals:
        failures.append(f"dense.py contains backend-name string literals: {backend_literals}")
    if native_distance_accesses:
        failures.append(f"dense.py interprets native_distance at lines {native_distance_accesses}")
    if query_dense_calls < 1:
        failures.append("dense.py never calls the abstract store.query_dense seam")
    for backend, citation in adapter_citation.items():
        if citation["canonical_score_from_l2_calls"] < 1:
            failures.append(f"{backend} adapter does not convert its native distance itself")
        if not citation["dense_score_kind_import"]:
            failures.append(f"{backend} adapter does not reference DENSE_SCORE_KIND")

    return {
        "checked_file": str(DENSE_PY.relative_to(PROJECT_ROOT)),
        "backend_name_literals": backend_literals,
        "docstring_backend_mentions": docstring_mentions,
        "native_distance_accesses": native_distance_accesses,
        "abstract_query_dense_call_sites": query_dense_calls,
        "adapter_score_conversion": adapter_citation,
        "score_kind_defined_in": str(SCORE_PY.relative_to(PROJECT_ROOT)),
        "dense_score_kind_constant": 'DENSE_SCORE_KIND = "dense_similarity_v1"' in score_text,
        "failures": failures,
        "pass": not failures,
    }
