"""Cross-encoder reranker for re-scoring vector search results.

Uses a small cross-encoder model (default:
``cross-encoder/ms-marco-MiniLM-L-6-v2``, ~23 MB quantised ONNX) to
re-score query-document pairs for better retrieval precision.

Inference runs entirely through **ONNX Runtime** — no PyTorch or
optimum is imported at runtime.  The pre-exported ONNX model is
downloaded from HuggingFace Hub on first use and cached locally.
Tokenisation uses the pure-Rust **``tokenizers``** package, which
cannot pull ``torch`` the way ``transformers`` can.

Raw logit outputs are normalised to the (0, 1) range with a sigmoid
transform so that scores are directly comparable with vector cosine
similarity.

The reranker is a plain class constructed by ``rag_mcp.compose`` with
injected settings (model ID).  The underlying ONNX session and tokenizer
are cached **process-wide** keyed by ``(backend_name, model_id)``,
preserving the load-once semantics of the former ``__new__`` singleton:
the model is downloaded and loaded exactly once per process regardless
of how many reranker instances are constructed.

If loading fails transiently, the next call will retry.  If it
fails permanently, ``rerank()`` gracefully falls back to returning
the original results un-reranked.
"""

from __future__ import annotations

import logging
import math
import os
import platform
from typing import Any

from ._reranker_cache import (  # noqa: F401
    _CACHE_LOCK,
    _MODEL_CACHE,
    _record_failure,
    _reset_failure_state,
    reset_model_cache,
)

# Backend name used as the cache-key axis.  Each backend module sets its
# own so the ``(backend_name, model_id)`` key never collides across
# backends — see ``_reranker_cache.py``.
_BACKEND_NAME = "onnx"

logger = logging.getLogger(__name__)

# NOTE: the ``RERANK_MODEL`` module-level alias was removed in the
# architecture-v2 conformance change.  It was an import-time snapshot of
# ``settings.rerank_model`` (ADR-033 Part 2 forbids these), and its only
# consumer was the ``rag_mcp.reranker`` v1 shim, itself deleted in the same
# change.  The model ID is now injected: ``compose.build_reranker()`` passes
# ``model_id`` explicitly.

# Fallback model ID, used only when a caller constructs the reranker directly
# without one; production always goes through ``compose.build_reranker()``.
# MUST match ``RetrievalSettings.rerank_model`` in core/retrieval/settings.py,
# which is the single source of truth for the default.
DEFAULT_RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

# Tokenizer max sequence length.  ModernBERT supports 8,192 tokens but
# processing full-length pairs increases latency.  2,048 balances context
# window utilisation with latency — most RAG chunks are 512-1,024 tokens.
TOKENIZER_MAX_LENGTH = int(os.getenv("RERANK_TOKENIZER_MAX_LENGTH", "2048"))


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
            Required — the composition root resolves it from the injected
            settings.  Passing ``None`` is a programming error.

    Returns:
        List of Hub-relative paths (e.g. ``"onnx/model_quantized.onnx"``)
        in priority order.  The caller should try each in turn until one
        downloads successfully.
    """
    if model_id is None:
        raise ValueError(
            "model_id is required; compose.build_reranker() resolves it from the injected settings"
        )
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


def _read_max_position_embeddings(model_id: str) -> int:
    """Read ``max_position_embeddings`` from the model's ``config.json``.

    Thin wrapper around ``_model_config.read_max_position_embeddings``
    that supplies the configured ``TOKENIZER_MAX_LENGTH`` as the
    fallback, so callers within this module don't repeat the env-var
    read. Kept here (rather than inlined at the call site) because the
    test suite imports it as ``reranker._read_max_position_embeddings``.
    """
    from ._model_config import read_max_position_embeddings

    return read_max_position_embeddings(model_id, TOKENIZER_MAX_LENGTH)


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

    # Backend name surfaced through pipeline diagnostics
    # (``rerank_backend``).  Matches the registry name suffix.
    backend_name: str = "onnx"

    def __init__(
        self,
        model_id: str | None = None,
        tokenizer_max_length: int | None = None,
    ) -> None:
        """Initialise the reranker with injected settings.

        Args:
            model_id: HuggingFace model ID to use.  Supplied by
                ``compose.build_reranker()`` from the injected settings.
                Falls back to the ADR-028 default only for direct
                construction in tests.
            tokenizer_max_length: Tokenizer sequence-length cap.  When
                ``None``, defaults to the module-level
                ``TOKENIZER_MAX_LENGTH``.
        """
        self._model_id: str = model_id or DEFAULT_RERANK_MODEL
        self._session: Any = None
        self._tokenizer: Any = None
        self._loaded: bool = False
        self._load_attempted: bool = False
        self._load_error: str | None = None
        self._effective_max_length: int = tokenizer_max_length or TOKENIZER_MAX_LENGTH
        # Per-call failure reason surfaced through pipeline diagnostics
        # (`rerank_reason`).  Unlike `_FAILURE_STATE`, this is instance
        # state deliberately — it describes only this call, not a
        # process-wide streak, and a fresh reranker is built per search().
        self.last_failure_reason: str | None = None

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
            cached = _MODEL_CACHE.get((_BACKEND_NAME, self._model_id))
            if cached is not None:
                self._session, self._tokenizer, self._effective_max_length = cached
                self._loaded = True
                self._load_attempted = True
                self._load_error = None
                self.last_failure_reason = None
                # Deliberately do NOT call _reset_failure_state() here.
                # A cache hit means the model loaded successfully in the
                # past, but inference may be persistently failing (the
                # ADR-029 CoreML shape).  Resetting the streak on every
                # cache hit would prevent escalation from ever firing
                # through the un-injected search() path, which builds a
                # fresh reranker per call.
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
                from tokenizers import Tokenizer

                logger.info(
                    "Loading reranker model: %s",
                    self._model_id,
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
                            candidate,
                            self._model_id,
                            download_exc,
                        )

                if onnx_path is None:
                    raise RuntimeError(
                        f"No ONNX variant available for {self._model_id}. "
                        f"Tried: {', '.join(candidates)}"
                    )

                self._tokenizer = Tokenizer.from_pretrained(self._model_id)
                # Cap max_length at the model's own limit.  MiniLM supports
                # 512 tokens; ModernBERT supports 8192.  Using a max_length
                # larger than the model's position embeddings causes an ONNX
                # broadcast error at runtime.  The tokenizers package does
                # not expose model_max_length, so read it from config.json.
                model_max = _read_max_position_embeddings(self._model_id)
                self._effective_max_length = min(self._effective_max_length, model_max)
                # Configure truncation and padding on the tokenizer once.
                # The tokenizer is cached process-wide, so these settings
                # persist for the process lifetime — subsequent instances
                # reuse the already-configured tokenizer from the cache.
                self._tokenizer.enable_truncation(max_length=self._effective_max_length)
                # Read the model's pad token config so padding uses the
                # correct pad_id and pad_token for non-BERT-family models
                # (e.g. RoBERTa uses pad_id=1, pad_token="<pad>").  Falls
                # back to library defaults when config is unavailable.
                from ._model_config import read_pad_token_config

                pad_id, pad_token = read_pad_token_config(self._model_id)
                _pad_kwargs: dict[str, int | str] = {}
                if pad_id is not None:
                    _pad_kwargs["pad_id"] = pad_id
                if pad_token is not None:
                    _pad_kwargs["pad_token"] = pad_token
                self._tokenizer.enable_padding(**_pad_kwargs)
                # CoreML does not support the dynamic sequence lengths that
                # cross-encoder tokenisation produces (variable batch padding).
                # It fails with "Error in dynamically resizing for sequence
                # length" and silently degrades to un-reranked results.
                # Default to CPU-only, which handles dynamic shapes correctly.
                # Override with RERANK_ONNX_PROVIDER=coreml to re-enable CoreML
                # (e.g. for fixed-input models or future CoreML versions).
                _onnx_provider = os.getenv("RERANK_ONNX_PROVIDER", "cpu")
                available = ort.get_available_providers()
                if _onnx_provider == "coreml" and "CoreMLExecutionProvider" in available:
                    providers = ["CoreMLExecutionProvider", "CPUExecutionProvider"]
                else:
                    providers = ["CPUExecutionProvider"]
                self._session = ort.InferenceSession(
                    onnx_path,
                    providers=providers,
                )
                self._loaded = True
                self._load_error = None
                self.last_failure_reason = None
                _reset_failure_state()
                _MODEL_CACHE[(_BACKEND_NAME, self._model_id)] = (
                    self._session,
                    self._tokenizer,
                    self._effective_max_length,
                )
                logger.info(
                    "Reranker model loaded successfully (variant: %s)",
                    onnx_filename,
                )
            except Exception as exc:
                self._load_error = str(exc)
                self.last_failure_reason = f"model load failed: {exc}"
                level = _record_failure(exc)
                logger.log(
                    level,
                    "Failed to load reranker model '%s': %s. Falling back to un-reranked results.",
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
        # Reset per-call failure state so a stale reason from a prior call on
        # the same instance (the MCP server reuses one reranker) cannot leak
        # into this call's diagnostics. It is set fresh below on a real failure.
        self.last_failure_reason = None
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

            # Determine which inputs the ONNX graph declares.  BERT-family
            # models produce token_type_ids; some other families do not.
            # Passing an undeclared input to ORT raises a cryptic input-name
            # error, so omit it when the graph does not ask for it.
            input_names = {inp.name for inp in self._session.get_inputs()}

            # Batch inference: processing all candidates in a single ONNX
            # call causes excessive memory allocation and poor cache
            # utilisation.  Batches of 32 balance throughput and latency.
            BATCH_SIZE = 32
            all_logits: list[float] = []
            for i in range(0, len(pairs), BATCH_SIZE):
                batch = pairs[i : i + BATCH_SIZE]
                # tokenizers.Tokenizer.encode_batch returns a list of
                # Encoding objects.  Property mapping differs from the
                # transformers AutoTokenizer: Encoding.ids → input_ids,
                # Encoding.attention_mask → attention_mask,
                # Encoding.type_ids → token_type_ids.  tokenizers returns
                # Python lists (u32 underneath); ORT expects int64 arrays.
                encodings = self._tokenizer.encode_batch(batch)
                feed: dict[str, Any] = {
                    "input_ids": np.asarray([enc.ids for enc in encodings], dtype=np.int64),
                    "attention_mask": np.asarray(
                        [enc.attention_mask for enc in encodings], dtype=np.int64
                    ),
                }
                if "token_type_ids" in input_names:
                    feed["token_type_ids"] = np.asarray(
                        [enc.type_ids for enc in encodings], dtype=np.int64
                    )
                outputs = self._session.run(None, feed)
                batch_logits = np.asarray(outputs[0]).flatten()
                all_logits.extend(float(v) for v in batch_logits)

            # Normalise raw logits to (0, 1) via sigmoid.
            scores: list[float] = [_sigmoid(v) for v in all_logits]
        except Exception as exc:
            self.last_failure_reason = f"inference failed: {exc}"
            with _CACHE_LOCK:
                level = _record_failure(exc)
            logger.log(
                level,
                "Reranker inference failed: %s. Returning un-reranked results.",
                exc,
            )
            for r in results:
                r["_reranked"] = False
            return results[:top_k]

        # Assign normalised scores and sort.  Guard against an ONNX output
        # whose cardinality does not match ``results``: silently truncating
        # (or ignoring excess scores) would leave results without a
        # ``_reranked`` flag.  Fall back to the un-reranked path instead.
        if len(scores) != len(results):
            logger.warning(
                "Reranker score cardinality mismatch: %d scores for %d "
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
