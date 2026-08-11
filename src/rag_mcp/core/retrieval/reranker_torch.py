"""Torch cross-encoder reranker backed by ``sentence-transformers.CrossEncoder``.

Satisfies the same public contract as ``core/retrieval/reranker.py``:
re-score query-document pairs, return results sorted by descending
relevance, truncate to ``top_k``, set the ``_reranked`` provenance flag,
and normalise raw model outputs to ``(0, 1)`` via a sigmoid transform
shared with the ONNX backend so scores stay comparable across backends.

``sentence_transformers`` is imported **lazily** inside ``_load_model``,
never at module top level.  This keeps the registry import cheap and
makes the missing-extra case catchable (design decision 5).

This backend is opt-in: it lives behind the ``torch`` optional extra.
The default install never imports ``torch``.
"""

from __future__ import annotations

import logging
from typing import Any

from ._reranker_cache import (
    _CACHE_LOCK,
    _MODEL_CACHE,
    _record_failure,
    _reset_failure_state,
)
from .reranker import DEFAULT_RERANK_MODEL, TOKENIZER_MAX_LENGTH, _sigmoid

# Backend name used as the cache-key axis — see ``_reranker_cache.py``.
_BACKEND_NAME = "torch"

logger = logging.getLogger(__name__)


class SentenceTransformerReranker:
    """Plain-class cross-encoder reranker backed by ``sentence-transformers``.

    Constructed by the composition root or the lazy pipeline path when
    ``RETRIEVAL__RERANK_BACKEND=torch``.  The underlying
    ``CrossEncoder`` is cached process-wide keyed by
    ``("torch", model_id)``, so the model is loaded at most once per
    process.

    Matches :class:`CrossEncoderReranker`'s constructor signature
    (``model_id``, ``tokenizer_max_length``) and public surface
    (``rerank``, ``last_failure_reason``).

    Loads the model lazily on first use.  Thread-safe via the shared
    cache lock.  If model loading fails, ``rerank()`` returns inputs
    unchanged (truncated to ``top_k``) and will retry on the next call.
    """

    # Backend name surfaced through pipeline diagnostics
    # (``rerank_backend``).  Matches the registry name suffix.
    backend_name: str = "torch"

    def __init__(
        self,
        model_id: str | None = None,
        tokenizer_max_length: int | None = None,
    ) -> None:
        """Initialise the reranker with injected settings.

        Args:
            model_id: HuggingFace model ID to use.  Supplied by
                ``compose.build_reranker()`` from the injected settings.
                Falls back to the default only for direct construction
                in tests.
            tokenizer_max_length: Tokenizer sequence-length cap.  When
                ``None``, defaults to the module-level
                ``TOKENIZER_MAX_LENGTH``.
        """
        self._model_id: str = model_id or DEFAULT_RERANK_MODEL
        self._cross_encoder: Any = None
        self._loaded: bool = False
        self._load_attempted: bool = False
        self._load_error: str | None = None
        self._effective_max_length: int = tokenizer_max_length or TOKENIZER_MAX_LENGTH
        # Per-call failure reason surfaced through pipeline diagnostics
        # (``rerank_reason``).  Instance state — describes only this call,
        # not a process-wide streak.
        self.last_failure_reason: str | None = None

    # ── Model loading ──────────────────────────────────────────────────

    def _load_model(self) -> None:
        """Attempt to load the cross-encoder model via sentence-transformers.

        Imports ``sentence_transformers`` lazily so the missing-extra case
        is catchable.  Consults the process-wide cache first; retries on
        each call if the previous attempt failed.
        """
        if self._loaded:
            return

        with _CACHE_LOCK:
            cached = _MODEL_CACHE.get((_BACKEND_NAME, self._model_id))
            if cached is not None:
                self._cross_encoder = cached[0]
                self._loaded = True
                self._load_attempted = True
                self._load_error = None
                self.last_failure_reason = None
                return

            if self._load_attempted and not self._loaded:
                logger.info(
                    "Retrying torch reranker model load (previous error: %s)",
                    self._load_error,
                )

            self._load_attempted = True

            try:  # pragma: no cover — requires torch extra, covered by dedicated CI job
                # Lazy import: sentence_transformers pulls torch, which is
                # an optional extra.  Importing here keeps the registry
                # import cheap and makes the missing-extra case catchable.
                import torch  # noqa: F401 — imported to pass Identity to predict()
                from sentence_transformers import CrossEncoder

                logger.info(
                    "Loading torch reranker model: %s",
                    self._model_id,
                )

                self._cross_encoder = CrossEncoder(self._model_id)
                self._loaded = True
                self._load_error = None
                self.last_failure_reason = None
                _reset_failure_state()
                _MODEL_CACHE[(_BACKEND_NAME, self._model_id)] = (self._cross_encoder,)
                logger.info("Torch reranker model loaded successfully")
            except Exception as exc:
                self._load_error = str(exc)
                self.last_failure_reason = f"model load failed: {exc}"
                level = _record_failure(exc)
                logger.log(
                    level,
                    "Failed to load torch reranker model '%s': %s. "
                    "Falling back to un-reranked results.",
                    self._model_id,
                    exc,
                )

    # ── Public API ─────────────────────────────────────────────────────

    def rerank(
        self,
        query: str,
        results: list[dict],
        top_k: int = 5,
    ) -> list[dict]:
        """Re-score search results using the cross-encoder model.

        Raw logit outputs are normalised to (0, 1) via the shared
        ``_sigmoid`` function so scores are comparable with the ONNX
        backend and with vector cosine similarity.

        ``CrossEncoder.predict()`` applies ``nn.Sigmoid()`` by default
        for ``num_labels=1`` models.  This method overrides that with
        ``torch.nn.Identity()`` and applies ``_sigmoid`` once — otherwise
        the logits would be double-sigmoided, compressing scores to
        roughly ``[0.5, 0.73]`` and silently breaking the ÷30 threshold
        (design decision 3).

        Args:
            query: The user's search query string.
            results: List of result dicts, each with at least a
                ``text`` key and a ``score`` key.
            top_k: Number of top results to return after re-scoring.

        Returns:
            Results sorted by the reranker's relevance score
            (descending, 0–1 normalised), truncated to ``top_k``.
            Each result includes a ``_reranked`` metadata key set to
            ``True``.  If the model is unavailable, returns the
            original results unchanged with ``_reranked`` set to
            ``False``.
        """
        # Reset per-call failure state so a stale reason from a prior call
        # cannot leak into this call's diagnostics.
        self.last_failure_reason = None
        if not results:
            return results

        self._load_model()

        if not self._loaded:
            for r in results:
                r["_reranked"] = False
            return results[:top_k]

        pairs = [(query, r["text"]) for r in results]

        try:  # pragma: no cover — requires torch extra, covered by dedicated CI job
            import torch

            # Suppress the library's default sigmoid (applied when
            # num_labels=1) and apply our own _sigmoid once.  Passing
            # activation_fn=None would NOT disable activation — it
            # resolves to nn.Sigmoid() for num_labels=1, double-applying
            # sigmoid and compressing scores to [0.5, 0.73].
            raw_logits = self._cross_encoder.predict(
                pairs,
                activation_fn=torch.nn.Identity(),
                convert_to_numpy=True,
            )
            scores: list[float] = [_sigmoid(float(v)) for v in raw_logits]
        except Exception as exc:
            self.last_failure_reason = f"inference failed: {exc}"
            with _CACHE_LOCK:
                level = _record_failure(exc)
            logger.log(
                level,
                "Torch reranker inference failed: %s. Returning un-reranked results.",
                exc,
            )
            for r in results:
                r["_reranked"] = False
            return results[:top_k]

        # Guard against a score cardinality mismatch.
        if len(scores) != len(results):
            logger.warning(
                "Torch reranker score cardinality mismatch: %d scores for %d "
                "results. Returning un-reranked results.",
                len(scores),
                len(results),
            )
            for r in results:
                r["_reranked"] = False
            return results[:top_k]

        for result, score in zip(results, scores, strict=True):
            result["score"] = score
            result["_reranked"] = True

        self.last_failure_reason = None
        with _CACHE_LOCK:
            _reset_failure_state()

        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:top_k]
