"""Assert dispatch modules have no module-level strategy imports.

Verifies that ``core/ingestion/chunker.py``, ``core/metadata/extractor.py``,
and ``core/retrieval/pipeline.py`` contain no module-level import of a
concrete strategy module — strategies must be resolved through the registry
at dispatch time (task 3.8, config-composition-root spec).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "omrg"


def _absolute_module_name(module_path: Path) -> str:
    """Return the dotted module name for a file under ``src/``.

    ``src/omrg/core/ingestion/chunker.py`` → ``omrg.core.ingestion.chunker``
    """
    rel = module_path.resolve().relative_to(_SRC_ROOT.parent)
    return ".".join(rel.with_suffix("").parts)


def _resolve_relative(importer: str, level: int, module: str | None) -> str:
    """Resolve a relative ``ImportFrom`` to its absolute dotted name.

    ``level`` is the number of leading dots.  Level 1 means "the importer's
    own package", level 2 means "one package above", and so on — the same
    semantics Python itself uses.

    Without this resolution a relative import such as
    ``from ..chunking.code import chunk_code_file_async`` inside
    ``omrg.core.ingestion.chunker`` yields the bare string
    ``"chunking.code"``, which can never match an absolute forbidden name —
    silently rendering this whole test decorative.
    """
    package_parts = importer.split(".")[:-1]  # drop the module itself
    if level > 1:
        package_parts = package_parts[: -(level - 1)] or []
    base = ".".join(package_parts)
    if not module:
        return base
    return f"{base}.{module}" if base else module


def _module_top_level_imports(module_path: Path) -> set[str]:
    """Return the set of module names imported at the top level of *module_path*.

    Only top-level (module body) ``Import`` and ``ImportFrom`` nodes are
    collected — imports inside function/class bodies are excluded.  Relative
    imports are resolved to their absolute dotted names so they can be
    matched against the forbidden set.
    """
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(module_path))
    importer = _absolute_module_name(module_path)
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                resolved = _resolve_relative(importer, node.level, node.module)
            else:
                resolved = node.module or ""
            if resolved:
                names.add(resolved.split(".")[0])
                names.add(resolved)
    return names


# The concrete strategy modules that must NOT appear as top-level imports.
_FORBIDDEN_STRATEGY_MODULES = {
    "omrg.core.chunking.code",
    "omrg.core.chunking.markdown",
    "omrg.core.chunking.sentence",
    "omrg.core.chunking.config_file",
    "omrg.core.metadata.keyword",
    "omrg.core.metadata.ollama",
    "omrg.core.metadata.llamaindex",
    "omrg.core.metadata.llamacpp",
    "omrg.core.retrieval.dense",
    "omrg.core.retrieval.fusion",
    "omrg.core.retrieval.policy",
    "omrg.core.retrieval.reranker",
    "omrg.core.retrieval.sparse",
    "omrg.core.community.louvain",
    "omrg.core.community.leiden",
    "omrg.integrations.pdf.liteparse",
    "omrg.integrations.pdf.pypdf",
    "omrg.integrations.pdf.pypdfium",
    # register-document-backend-strategies (task 4.2): the chunker and the
    # backends orchestrator must resolve adapters through the registry —
    # never a module-level import of either concrete backend.
    "omrg.core.ingestion.backends.local",
    "omrg.integrations.azure",
}


@pytest.mark.parametrize(
    "rel_path",
    [
        "core/ingestion/chunker.py",
        "core/metadata/extractor.py",
        "core/retrieval/pipeline.py",
        "core/community/__init__.py",
        "integrations/pdf/factory.py",
    ],
)
def test_no_module_level_strategy_import(rel_path: str) -> None:
    """The dispatch module must not import concrete strategies at top level."""
    assert _SRC_ROOT.is_dir(), f"configured source root is missing: {_SRC_ROOT}"
    module_path = _SRC_ROOT / rel_path
    imports = _module_top_level_imports(module_path)

    # Check both the short form (e.g. "omrg") and full dotted paths.
    offenders = imports & _FORBIDDEN_STRATEGY_MODULES
    assert not offenders, (
        f"{rel_path} has module-level imports of concrete strategy modules: "
        f"{sorted(offenders)}. Strategies must be resolved through the "
        f"registry at dispatch time."
    )


_ORCHESTRATOR_RELPATH = "core/ingestion/backends/orchestrator.py"


def test_orchestrator_has_no_module_level_backend_imports() -> None:
    """The backend orchestrator resolves adapters lazily (task 4.2).

    The orchestrator must import neither the local backend module nor
    the Azure integration at module scope — both resolve through the
    registry at dispatch time.
    """
    module_path = _SRC_ROOT / _ORCHESTRATOR_RELPATH
    assert module_path.exists(), f"orchestrator module missing: {_ORCHESTRATOR_RELPATH}"
    imports = _module_top_level_imports(module_path)
    offenders = imports & _FORBIDDEN_STRATEGY_MODULES
    assert not offenders, (
        f"{_ORCHESTRATOR_RELPATH} has module-level imports of concrete "
        f"backend adapters: {sorted(offenders)}."
    )
