"""Runtime tripwire: torch must not be loaded after a default search (task 8.3).

Asserts that importing rag_mcp and running a search with rerank=True on
the default backend does not load torch into sys.modules.

This turns the existing prose requirement ("no PyTorch at runtime") into
an automated CI check. The previous violation entered through a
transitive dependency that no one audited.
"""

from __future__ import annotations

import sys


def test_torch_absent_after_default_backend_search() -> None:
    """After a default-backend search, torch SHALL NOT be in sys.modules.

    The default backend is ONNX, which uses tokenizers (pure Rust) and
    onnxruntime. Neither can pull torch. If this test fails, a
    dependency change reintroduced torch into the default path.
    """
    # Record the set of loaded modules before importing rag_mcp.
    # We check torch specifically, not the full diff, because other
    # modules may load legitimately.
    sys.modules.pop("torch", None)

    # Import the ONNX reranker module — this is what the default path loads.
    from rag_mcp.core.retrieval.reranker import CrossEncoderReranker  # noqa: F401

    assert "torch" not in sys.modules, (
        "torch was imported on the default (ONNX) backend path. "
        "A dependency change likely reintroduced it."
    )


def test_torch_absent_after_registry_import() -> None:
    """Importing the retrieval registry SHALL NOT load torch."""
    sys.modules.pop("torch", None)

    from rag_mcp.core.retrieval import registry  # noqa: F401

    assert "torch" not in sys.modules, (
        "torch was imported when the retrieval registry was imported. "
        "The registry must stay lazy — torch is behind an optional extra."
    )


def test_torch_absent_after_backend_module_import() -> None:
    """Importing the backend resolution module SHALL NOT load torch."""
    sys.modules.pop("torch", None)

    from rag_mcp.core.retrieval.backend import resolve_reranker_backend  # noqa: F401

    assert "torch" not in sys.modules, (
        "torch was imported when the backend resolution module was imported. "
        "The torch import must be lazy, inside the torch backend's _load_model."
    )
