"""Process-wide model cache and failure-escalation state for reranker backends.

Shared between the ONNX backend (``reranker.py``) and the torch backend
(``reranker_torch.py``).  Keyed by ``(backend_name, model_id)`` so two
backends asked for the same model ID do not collide — the tuple shape
also differs between backends (an ``onnxruntime.InferenceSession`` is not
a ``sentence_transformers.CrossEncoder``).

``_FAILURE_STATE`` stays a single process-wide counter, unkeyed.  That
was deliberate — the docstring below records the split-counter trap.
Adding a backend axis would reintroduce it.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

# ── Process-wide model cache ──────────────────────────────────────────
# Maps (backend_name, model_id) -> backend-specific cached tuple.
# For the ONNX backend: (onnx session, tokenizer, effective max length).
# For the torch backend: (cross_encoder, tokenizer, effective max length).
# Populated on first successful load; reused by every reranker instance
# so the model is loaded once per process (former singleton semantics).

_MODEL_CACHE: dict[tuple[str, str], tuple[Any, ...]] = {}

# RLock (not Lock): _record_failure/_reset_failure_state are called from
# inside a backend's load method under _CACHE_LOCK as well as standalone
# from rerank(), so the lock must support reentrant acquisition.
_CACHE_LOCK: threading.RLock = threading.RLock()

# ── Process-wide failure-escalation state (ADR-029 decision #3) ────────
# Tracks consecutive same-signature failures across both the load and
# inference failure paths so a persistent outage escalates from WARNING
# to ERROR instead of repeating an invisible warning on every call.
#
# Single process-wide count, NOT keyed by model ID or backend: the
# pipeline's un-injected path (``core/retrieval/registry.py``) constructs
# a reranker with no model_id, falling back to the default model, while
# compose.build_reranker() passes the configured model — keying by model
# ID would split one outage's failures across two counters, neither of
# which would reach the threshold (design.md "split-counter trap").
# Adding a backend axis would reintroduce the same trap.
_FAILURE_THRESHOLD = 3
_FAILURE_STATE: dict[str, Any] = {"count": 0, "last_signature": None}


def _record_failure(error: BaseException) -> int:
    """Record a reranker failure and return the log level to use.

    Compares the new error's string signature against the stored one:
    the same signature increments the consecutive count, a different one
    resets it to 1.  Must be called with ``_CACHE_LOCK`` held.

    Returns:
        ``logging.ERROR`` once the count reaches ``_FAILURE_THRESHOLD``,
        otherwise ``logging.WARNING``.
    """
    signature = str(error)
    if _FAILURE_STATE["last_signature"] == signature:
        _FAILURE_STATE["count"] += 1
    else:
        _FAILURE_STATE["count"] = 1
        _FAILURE_STATE["last_signature"] = signature
    if _FAILURE_STATE["count"] >= _FAILURE_THRESHOLD:
        return logging.ERROR
    return logging.WARNING


def _reset_failure_state() -> None:
    """Clear the consecutive-failure count. Must be called with ``_CACHE_LOCK`` held."""
    _FAILURE_STATE["count"] = 0
    _FAILURE_STATE["last_signature"] = None


def reset_model_cache() -> None:
    """Clear the process-wide model cache (test isolation hook).

    Replaces the former ``CrossEncoderReranker._instance = None`` reset.
    Tests that need a fresh model-load path call this in setup/teardown
    so no loaded session leaks across test cases.  Also clears the
    failure-escalation state so no consecutive-failure count leaks
    across test cases.

    Re-exported from both ``reranker.py`` and ``reranker_torch.py`` so
    the existing test teardown import path (gotcha 2 in CLAUDE.md) keeps
    working from either site.
    """
    with _CACHE_LOCK:
        _MODEL_CACHE.clear()
        _reset_failure_state()
