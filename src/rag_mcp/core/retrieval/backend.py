"""Shared reranker backend resolution.

Maps ``settings.retrieval.rerank_backend`` to a registry name and
resolves it.  Both ``compose.build_reranker()`` and the lazy path in
``pipeline.py`` call this helper so the two construction paths cannot
diverge (design decision 5).

On ``ImportError`` (the ``torch`` extra is not installed), logs at ERROR
naming ``uv sync --extra torch`` and falls back to the ONNX backend
rather than crashing.  If the ONNX backend also fails, the caller's
graceful-degradation path returns un-reranked results — the resolution
helper constructs the fallback object, and the ``rerank()`` method
handles the model-load failure.
"""

from __future__ import annotations

import logging
from typing import Any

from .registry import get as _retrieval_get

logger = logging.getLogger(__name__)

# Maps the settings value to the registry name.
_BACKEND_REGISTRY_NAME: dict[str, str] = {
    "onnx": "reranker_onnx",
    "torch": "reranker_torch",
}


def resolve_reranker_backend(backend: str) -> Any:
    """Resolve the reranker class for the given backend name.

    Args:
        backend: The settings value (``"onnx"`` or ``"torch"``).

    Returns:
        The resolved reranker class (callable).  On ``ImportError`` for
        the torch backend (extra not installed), falls back to the ONNX
        backend and logs at ERROR severity.

    Raises:
        KeyError: If *backend* is not a recognised value.  This should
            not happen — settings validation rejects unknown values at
            startup — but the guard is here for safety.
    """
    registry_name = _BACKEND_REGISTRY_NAME.get(backend)
    if registry_name is None:
        # Unreachable in production: settings validation rejects unknown
        # values.  Defensive guard for direct callers in tests.
        raise KeyError(
            f"Unknown reranker backend {backend!r}. Available: {sorted(_BACKEND_REGISTRY_NAME)}"
        )

    try:
        return _retrieval_get(registry_name)
    except ImportError:
        if backend == "torch":
            logger.error(
                "Torch reranker backend requested but the 'torch' optional "
                "extra is not installed. Install it with "
                "'uv sync --extra torch'. Falling back to the ONNX backend."
            )
            return _retrieval_get("reranker_onnx")
        raise


def build_reranker_from_settings(
    settings: Any,
    backend: str | None = None,
) -> Any:
    """Construct a reranker instance from resolved settings.

    Both ``compose.build_reranker()`` and the lazy path in
    ``pipeline.py`` call this so the two paths share identical fallback
    behaviour.

    Args:
        settings: An object with a ``retrieval`` attribute carrying
            ``rerank_backend`` and ``rerank_model``.
        backend: Override the backend name.  When ``None``, reads it
            from ``settings.retrieval.rerank_backend``.

    Returns:
        A constructed reranker instance wired to the settings-selected
        model ID.  On ``ImportError`` (torch extra missing), falls back
        to the ONNX backend.
    """
    if backend is None:
        backend = settings.retrieval.rerank_backend
    if not backend:
        backend = "onnx"
    reranker_cls = resolve_reranker_backend(backend)
    return reranker_cls(model_id=settings.retrieval.rerank_model)
