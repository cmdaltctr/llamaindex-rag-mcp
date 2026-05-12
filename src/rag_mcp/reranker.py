"""Cross-encoder reranker for re-scoring vector search results.

Uses a small cross-encoder model (default:
``cross-encoder/ms-marco-MiniLM-L-6-v2``, ~23 MB quantised ONNX) to
re-score query-document pairs for better retrieval precision.

Inference runs entirely through **ONNX Runtime** — no PyTorch or
optimum is imported at runtime.  The pre-exported ONNX model is
downloaded from HuggingFace Hub on first use and cached locally.

Raw logit outputs are normalised to the (0, 1) range with a sigmoid
transform so that scores are directly comparable with vector cosine
similarity.

The model is loaded once (singleton) and reused across calls.
If loading fails transiently, the next call will retry.  If it
fails permanently, ``rerank()`` gracefully falls back to returning
the original results un-reranked.
"""

from __future__ import annotations

import logging
import math
import os
import platform
import threading
from typing import Any

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

RERANK_MODEL = os.getenv(
    "RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2",
)


def _sigmoid(value: float) -> float:
    """Normalise a raw logit to (0, 1) via the sigmoid function.

    ``sigmoid(x) = 1 / (1 + exp(-x))``
    """
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-value))
    exp_val = math.exp(value)
    return exp_val / (1.0 + exp_val)


def _select_onnx_variant() -> str:
    """Pick the best ONNX model variant for the current platform.

    Returns the Hub-relative path (e.g. ``"onnx/model_qint8_arm64.onnx"``).
    Falls back to the generic fp32 model if no platform-specific
    quantised variant is available.
    """
    machine = platform.machine().lower()
    if machine in ("arm64", "aarch64"):
        return "onnx/model_qint8_arm64.onnx"
    # Generic fallback — fp32, works everywhere.
    return "onnx/model.onnx"


class CrossEncoderReranker:
    """Singleton cross-encoder reranker backed by pure ONNX Runtime.

    Loads the model lazily on first use.  Thread-safe via a lock.
    If model loading fails, ``rerank()`` returns inputs unchanged
    and will retry on the next call (transient failure recovery).
    """

    _instance: CrossEncoderReranker | None = None
    _lock: threading.Lock = threading.Lock()

    def __new__(cls) -> CrossEncoderReranker:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    # Per-instance state (set here so __init__ is not needed)
                    cls._instance._session: Any = None
                    cls._instance._tokenizer: Any = None
                    cls._instance._loaded: bool = False
                    cls._instance._load_attempted: bool = False
                    cls._instance._load_error: str | None = None
        return cls._instance

    # ── Model loading ──────────────────────────────────────────────────

    def _load_model(self) -> None:
        """Attempt to load the cross-encoder ONNX model.

        Retries on each call if the previous attempt failed (transient
        error recovery).  Once loaded successfully, the model is reused
        for the process lifetime.
        """
        if self._loaded:
            return

        with self._lock:
            if self._loaded:
                return

            # If a previous attempt failed, allow retry — the failure
            # may have been transient (e.g. network timeout).
            if self._load_attempted and not self._loaded:
                logger.info(
                    "Retrying reranker model load (previous error: %s)",
                    self._load_error,
                )

            self._load_attempted = True

            try:
                import onnxruntime as ort
                from huggingface_hub import hf_hub_download
                from transformers import AutoTokenizer

                logger.info(
                    "Loading reranker model: %s", RERANK_MODEL,
                )

                # Download the pre-exported ONNX model from HuggingFace Hub.
                onnx_filename = _select_onnx_variant()
                onnx_path = hf_hub_download(
                    repo_id=RERANK_MODEL,
                    filename=onnx_filename,
                )

                self._tokenizer = AutoTokenizer.from_pretrained(
                    RERANK_MODEL,
                )
                self._session = ort.InferenceSession(
                    onnx_path,
                    providers=["CPUExecutionProvider"],
                )
                self._loaded = True
                self._load_error = None
                logger.info(
                    "Reranker model loaded successfully "
                    "(variant: %s)", onnx_filename,
                )
            except Exception as exc:
                self._load_error = str(exc)
                logger.warning(
                    "Failed to load reranker model '%s': %s. "
                    "Falling back to un-reranked results.",
                    RERANK_MODEL, exc,
                )

    # ── Public API ─────────────────────────────────────────────────────

    def rerank(
        self,
        query: str,
        results: list[dict],
        top_k: int = 5,
    ) -> list[dict]:
        """Re-score search results using the cross-encoder model.

        Raw logit outputs are normalised to (0, 1) via sigmoid so
        scores are comparable with vector cosine similarity.

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
        if not results:
            return results

        self._load_model()

        if not self._loaded:
            # Model failed to load — return originals, truncated.
            for r in results:
                r["_reranked"] = False
            return results[:top_k]

        # Build query-document pairs for the cross-encoder.
        pairs = [(query, r["text"]) for r in results]

        try:
            # Tokenize the pairs (numpy arrays for onnxruntime).
            encoded = self._tokenizer(
                pairs,
                padding=True,
                truncation=True,
                return_tensors="np",
            )

            # Run ONNX inference.
            outputs = self._session.run(
                None,
                {k: v for k, v in encoded.items()},
            )
            # outputs[0] shape: (batch_size, 1) → squeeze to (batch_size,)
            import numpy as np
            logits = outputs[0].squeeze(-1)

            # Normalise raw logits to (0, 1) via sigmoid.
            scores: list[float] = [_sigmoid(float(v)) for v in logits]
        except Exception as exc:
            logger.warning(
                "Reranker inference failed: %s. "
                "Returning un-reranked results.", exc,
            )
            for r in results:
                r["_reranked"] = False
            return results[:top_k]

        # Assign normalised scores and sort.
        for result, score in zip(results, scores):
            result["score"] = score
            result["_reranked"] = True

        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:top_k]
