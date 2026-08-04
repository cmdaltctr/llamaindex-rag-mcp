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

The reranker is a plain class constructed by ``rag_mcp.compose`` with
injected settings (model ID).  The underlying ONNX session and tokenizer
are cached **process-wide** keyed by model ID, preserving the load-once
semantics of the former ``__new__`` singleton: the model is downloaded
and loaded exactly once per process regardless of how many reranker
instances are constructed.

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

from ...config import settings

logger = logging.getLogger(__name__)

# Model ID resolved from the structured settings (injected).  Kept as a
# module-level alias so legacy imports (and the ``rag_mcp.reranker``
# compat shim) keep working during migration.
RERANK_MODEL = settings.rerank_model

# Tokenizer max sequence length.  ModernBERT supports 8,192 tokens but
# processing full-length pairs increases latency.  2,048 balances context
# window utilisation with latency — most RAG chunks are 512-1,024 tokens.
TOKENIZER_MAX_LENGTH = int(os.getenv("RERANK_TOKENIZER_MAX_LENGTH", "2048"))

# ── Process-wide model cache ──────────────────────────────────────────
# Maps model ID -> (onnx session, tokenizer, effective max length).
# Populated on first successful load; reused by every reranker instance
# so the model is loaded once per process (former singleton semantics).

_MODEL_CACHE: dict[str, tuple[Any, Any, int]] = {}
_CACHE_LOCK: threading.Lock = threading.Lock()


def reset_model_cache() -> None:
    """Clear the process-wide model cache (test isolation hook).

    Replaces the former ``CrossEncoderReranker._instance = None`` reset.
    Tests that need a fresh model-load path call this in setup/teardown
    so no loaded session leaks across test cases.
    """
    with _CACHE_LOCK:
        _MODEL_CACHE.clear()


def _sigmoid(value: float) -> float:
    """Normalise a raw logit to (0, 1) via the sigmoid function.

    ``sigmoid(x) = 1 / (1 + exp(-x))``
    """
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-value))
    exp_val = math.exp(value)
    return exp_val / (1.0 + exp_val)


def _select_onnx_variant(model_id: str | None = None) -> list[str]:
    """Return candidate ONNX model paths in priority order.

    For ModernBERT-based models (e.g. ``gte-reranker-modernbert-base``),
    prefers standard quantised variants that work cross-platform via
    ``onnxruntime`` — no ARM-tuned ``qint8_arm64`` variant exists for
    these models.

    For legacy models that ship ARM-tuned variants (e.g.
    ``cross-encoder/ms-marco-MiniLM-L-6-v2``), uses the platform-specific
    preference on ARM64 and falls back to the generic fp32 model elsewhere.

    Args:
        model_id: HuggingFace model ID to select a variant for.
            If ``None``, defaults to the resolved ``settings.rerank_model``
            (read at call time so patches to the singleton are honoured).

    Returns:
        List of Hub-relative paths (e.g. ``"onnx/model_quantized.onnx"``)
        in priority order.  The caller should try each in turn until one
        downloads successfully.
    """
    if model_id is None:
        model_id = settings.rerank_model
    model_lower = model_id.lower()

    # ModernBERT models ship eight pre-exported ONNX variants.  Prefer the
    # standard int8 quantised graph (151 MB) on all platforms, then fall
    # back through smaller quantisation options to fp32.
    if "modernbert" in model_lower or "gte-reranker" in model_lower:
        return [
            "onnx/model_quantized.onnx",
            "onnx/model_int8.onnx",
            "onnx/model_fp16.onnx",
            "onnx/model.onnx",
        ]

    # Legacy models with ARM-tuned quantised variants.
    machine = platform.machine().lower()
    if machine in ("arm64", "aarch64"):
        return ["onnx/model_qint8_arm64.onnx", "onnx/model.onnx"]

    # Generic fallback — fp32, works everywhere.
    return ["onnx/model.onnx"]


class CrossEncoderReranker:
    """Plain-class cross-encoder reranker backed by pure ONNX Runtime.

    Constructed by the composition root (``rag_mcp.compose``) with an
    injected model ID.  The underlying ONNX session and tokenizer are
    cached process-wide keyed by model ID, so the model is loaded at
    most once per process (former ``__new__`` singleton semantics).

    Loads the model lazily on first use.  Thread-safe via a lock.
    If model loading fails, ``rerank()`` returns inputs unchanged
    and will retry on the next call (transient failure recovery).
    """

    def __init__(
        self,
        model_id: str | None = None,
        tokenizer_max_length: int | None = None,
    ) -> None:
        """Initialise the reranker with injected settings.

        Args:
            model_id: HuggingFace model ID to use.  When ``None``,
                defaults to the resolved ``settings.rerank_model``
                (read at call time, so tests patching the singleton
                after import are honoured).
            tokenizer_max_length: Tokenizer sequence-length cap.  When
                ``None``, defaults to the module-level
                ``TOKENIZER_MAX_LENGTH``.
        """
        self._model_id: str = model_id or settings.rerank_model
        self._session: Any = None
        self._tokenizer: Any = None
        self._loaded: bool = False
        self._load_attempted: bool = False
        self._load_error: str | None = None
        self._effective_max_length: int = (
            tokenizer_max_length or TOKENIZER_MAX_LENGTH
        )

    # ── Model loading ──────────────────────────────────────────────────

    def _load_model(self) -> None:
        """Attempt to load the cross-encoder ONNX model.

        Consults the process-wide model cache first: if another instance
        already loaded the same model ID, the session and tokenizer are
        reused without re-downloading.  Retries on each call if the
        previous attempt failed (transient error recovery).  Once loaded
        successfully, the model is reused for the process lifetime.
        """
        if self._loaded:
            return

        with _CACHE_LOCK:
            cached = _MODEL_CACHE.get(self._model_id)
            if cached is not None:
                self._session, self._tokenizer, self._effective_max_length = cached
                self._loaded = True
                self._load_attempted = True
                self._load_error = None
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
                    "Loading reranker model: %s", self._model_id,
                )

                # Download the pre-exported ONNX model from HuggingFace Hub.
                # Try candidate variants in priority order — the preferred
                # quantised variant may occasionally be unavailable.
                candidates = _select_onnx_variant(self._model_id)
                onnx_path = None
                onnx_filename = None
                for candidate in candidates:
                    try:
                        onnx_path = hf_hub_download(
                            repo_id=self._model_id,
                            filename=candidate,
                        )
                        onnx_filename = candidate
                        break
                    except Exception as download_exc:
                        logger.debug(
                            "ONNX variant %s unavailable for %s: %s",
                            candidate, self._model_id, download_exc,
                        )

                if onnx_path is None:
                    raise RuntimeError(
                        f"No ONNX variant available for {self._model_id}. "
                        f"Tried: {', '.join(candidates)}"
                    )

                self._tokenizer = AutoTokenizer.from_pretrained(
                    self._model_id,
                )
                # Cap max_length at the model's own limit.  MiniLM supports
                # 512 tokens; ModernBERT supports 8192.  Using a max_length
                # larger than the model's position embeddings causes an ONNX
                # broadcast error at runtime.
                model_max = getattr(
                    self._tokenizer, "model_max_length", TOKENIZER_MAX_LENGTH
                )
                # Some tokenizers return a sentinel (e.g. 1000000) for
                # "very large" — cap at our configured default in that case.
                if not isinstance(model_max, int) or model_max > 100000:
                    model_max = TOKENIZER_MAX_LENGTH
                self._effective_max_length = min(TOKENIZER_MAX_LENGTH, model_max)
                # CoreML does not support the dynamic sequence lengths that
                # cross-encoder tokenisation produces (variable batch padding).
                # It fails with "Error in dynamically resizing for sequence
                # length" and silently degrades to un-reranked results.
                # Default to CPU-only, which handles dynamic shapes correctly.
                # Override with RERANK_ONNX_PROVIDER=coreml to re-enable CoreML
                # (e.g. for fixed-input models or future CoreML versions).
                _onnx_provider = os.getenv("RERANK_ONNX_PROVIDER", "cpu")
                available = ort.get_available_providers()
                if (
                    _onnx_provider == "coreml"
                    and "CoreMLExecutionProvider" in available
                ):
                    providers = ["CoreMLExecutionProvider", "CPUExecutionProvider"]
                else:
                    providers = ["CPUExecutionProvider"]
                self._session = ort.InferenceSession(
                    onnx_path,
                    providers=providers,
                )
                self._loaded = True
                self._load_error = None
                _MODEL_CACHE[self._model_id] = (
                    self._session,
                    self._tokenizer,
                    self._effective_max_length,
                )
                logger.info(
                    "Reranker model loaded successfully "
                    "(variant: %s)", onnx_filename,
                )
            except Exception as exc:
                self._load_error = str(exc)
                logger.warning(
                    "Failed to load reranker model '%s': %s. "
                    "Falling back to un-reranked results.",
                    self._model_id, exc,
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
            import numpy as np  # lightweight; always available with onnxruntime

            # Batch inference: processing all candidates in a single ONNX
            # call causes excessive memory allocation and poor cache
            # utilisation.  Batches of 32 balance throughput and latency.
            BATCH_SIZE = 32
            all_logits: list[float] = []
            for i in range(0, len(pairs), BATCH_SIZE):
                batch = pairs[i:i + BATCH_SIZE]
                encoded = self._tokenizer(
                    batch,
                    padding=True,
                    truncation=True,
                    max_length=self._effective_max_length,
                    return_tensors="np",
                )
                outputs = self._session.run(
                    None,
                    dict(encoded.items()),
                )
                batch_logits = np.asarray(outputs[0]).flatten()
                all_logits.extend(float(v) for v in batch_logits)

            # Normalise raw logits to (0, 1) via sigmoid.
            scores: list[float] = [_sigmoid(v) for v in all_logits]
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
