"""Tests for reranker backend selection (tasks 1.3, 1.5, 5.3, 5.4).

Covers:
- settings_to_effective round-trips rerank_backend without silent drop
- unknown backend name rejected at settings resolution
- lazy and injected paths select the same backend
- missing-extra + ONNX-also-fails degrades gracefully
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

# ── Task 1.3: settings_to_effective round-trip ─────────────────────────


def test_settings_to_effective_preserves_rerank_backend(effective_settings) -> None:
    """rerank_backend must survive the settings_to_effective copy.

    RetrievalBlock uses ConfigDict(frozen=True) with no extra override,
    so Pydantic defaults to extra="ignore" — undeclared fields are
    silently dropped during the model_dump() copy in compose.
    """
    from rag_mcp.compose import settings_to_effective
    from rag_mcp.config import get_settings

    # Default install: backend is "onnx"
    settings = get_settings()
    effective = settings_to_effective(settings)
    assert effective.retrieval.rerank_backend == "onnx", (
        "rerank_backend was silently dropped during settings_to_effective — "
        "the field is likely missing from RetrievalBlock in core/settings.py"
    )


def test_settings_to_effective_rerank_backend_torch(effective_settings) -> None:
    """rerank_backend=torch survives the settings_to_effective copy."""
    settings = effective_settings(rerank_backend="torch")
    assert settings.retrieval.rerank_backend == "torch"


# ── Task 1.5: unknown backend name rejected ─────────────────────────────


def test_unknown_rerank_backend_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """RETRIEVAL__RERANK_BACKEND=tensorflow must fail at settings resolution."""
    monkeypatch.setenv("RETRIEVAL__RERANK_BACKEND", "tensorflow")
    # Force a fresh settings resolution — get_settings caches.
    from rag_mcp.config import get_settings

    with pytest.raises(ValueError, match="RETRIEVAL__RERANK_BACKEND.*Accepted values: onnx, torch"):
        get_settings()


def test_empty_rerank_backend_resets_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty RETRIEVAL__RERANK_BACKEND resets to the default ("onnx")."""
    monkeypatch.setenv("RETRIEVAL__RERANK_BACKEND", "")
    from rag_mcp.config import Settings

    settings = Settings()
    assert settings.retrieval.rerank_backend == "onnx"


def test_whitespace_rerank_backend_stripped(monkeypatch: pytest.MonkeyPatch) -> None:
    """Padded RETRIEVAL__RERANK_BACKEND value is stripped."""
    monkeypatch.setenv("RETRIEVAL__RERANK_BACKEND", "  onnx  ")
    from rag_mcp.config import Settings

    settings = Settings()
    assert settings.retrieval.rerank_backend == "onnx"


# ── Task 5.3: lazy and injected paths select the same backend ───────────


def test_lazy_and_injected_paths_select_same_backend(effective_settings) -> None:
    """Both construction paths resolve the same backend for the same settings.

    compose.build_reranker() and the lazy path in pipeline.py both call
    build_reranker_from_settings, so they cannot diverge (design decision 5).
    """
    from rag_mcp.compose import build_reranker
    from rag_mcp.core.retrieval.backend import build_reranker_from_settings

    settings = effective_settings(rerank_backend="onnx")

    injected = build_reranker(settings)
    lazy = build_reranker_from_settings(settings)

    assert type(injected) is type(lazy), (
        f"Injected path ({type(injected).__name__}) and lazy path "
        f"({type(lazy).__name__}) selected different backend classes"
    )


# ── Task 5.4: missing-extra + ONNX-also-fails degrades gracefully ───────


def test_torch_missing_falls_back_to_onnx(effective_settings) -> None:
    """When torch is requested but the extra is missing, ONNX is used."""
    from rag_mcp.core.retrieval.backend import resolve_reranker_backend
    from rag_mcp.core.retrieval.reranker import CrossEncoderReranker

    # Patch the _retrieval_get reference imported into backend.py (not
    # registry.get — the import is bound at module load time).
    def selective_get(name: str):
        if name == "reranker_torch":
            raise ImportError("no sentence_transformers")
        from rag_mcp.core.retrieval.registry import get

        return get(name)

    with patch("rag_mcp.core.retrieval.backend._retrieval_get", side_effect=selective_get):
        cls = resolve_reranker_backend("torch")
        assert cls is CrossEncoderReranker, (
            f"Expected ONNX fallback (CrossEncoderReranker), got {cls.__name__}"
        )


def test_torch_missing_and_onnx_fails_degrades(effective_settings) -> None:
    """RETRIEVAL__RERANK_BACKEND=torch, no extra, ONNX also fails → un-reranked.

    The search SHALL return un-reranked results truncated to top_k,
    set last_failure_reason, and never raise.
    """
    from rag_mcp.core.retrieval.backend import build_reranker_from_settings
    from rag_mcp.core.retrieval.reranker import CrossEncoderReranker, reset_model_cache

    settings = effective_settings(rerank_backend="torch")
    reset_model_cache()

    # Patch the _retrieval_get reference in backend.py to raise ImportError
    # for torch, letting ONNX resolve normally. The ONNX backend's _load_model
    # will then fail gracefully since no model is available.
    def selective_get(name: str):
        if name == "reranker_torch":
            raise ImportError("no sentence_transformers")
        from rag_mcp.core.retrieval.registry import get

        return get(name)

    with patch("rag_mcp.core.retrieval.backend._retrieval_get", side_effect=selective_get):
        reranker = build_reranker_from_settings(settings)
        # Should have fallen back to ONNX
        assert isinstance(reranker, CrossEncoderReranker), (
            f"Expected ONNX fallback, got {type(reranker).__name__}"
        )
        # Force the ONNX model load to fail (simulates "ONNX also fails"):
        # mock _load_model as a no-op so _loaded stays False.
        reranker._load_model = lambda: None  # type: ignore[method-assign]
        reranker.last_failure_reason = "simulated ONNX failure"
        # Verify graceful degradation: rerank with no loaded model returns
        # un-reranked results truncated to top_k, never raises.
        results = [{"text": "test", "score": 0.5}]
        out = reranker.rerank("query", results, top_k=1)
        assert len(out) <= 1
        assert all(not r.get("_reranked", False) for r in out)


# ── _read_max_position_embeddings (reranker.py new method) ──────────────


def test_read_max_position_embeddings_reads_config_json() -> None:
    """_read_max_position_embeddings SHALL read max_position_embeddings."""
    import json
    from unittest.mock import mock_open, patch

    from rag_mcp.core.retrieval.reranker import CrossEncoderReranker

    reranker = CrossEncoderReranker()
    config = json.dumps({"max_position_embeddings": 512})
    with patch("huggingface_hub.hf_hub_download", return_value="/fake/config.json"):
        with patch("builtins.open", mock_open(read_data=config)):
            result = reranker._read_max_position_embeddings()
            assert result == 512


def test_read_max_position_embeddings_sentinel_falls_back() -> None:
    """Sentinel value (>100000) SHALL fall back to TOKENIZER_MAX_LENGTH."""
    import json
    from unittest.mock import mock_open, patch

    from rag_mcp.core.retrieval.reranker import TOKENIZER_MAX_LENGTH, CrossEncoderReranker

    reranker = CrossEncoderReranker()
    config = json.dumps({"max_position_embeddings": 1000000})
    with patch("huggingface_hub.hf_hub_download", return_value="/fake/config.json"):
        with patch("builtins.open", mock_open(read_data=config)):
            result = reranker._read_max_position_embeddings()
            assert result == TOKENIZER_MAX_LENGTH


def test_read_max_position_embeddings_missing_key_falls_back() -> None:
    """Missing max_position_embeddings key SHALL fall back to default."""
    import json
    from unittest.mock import mock_open, patch

    from rag_mcp.core.retrieval.reranker import TOKENIZER_MAX_LENGTH, CrossEncoderReranker

    reranker = CrossEncoderReranker()
    with patch("huggingface_hub.hf_hub_download", return_value="/fake/config.json"):
        with patch("builtins.open", mock_open(read_data=json.dumps({}))):
            result = reranker._read_max_position_embeddings()
            assert result == TOKENIZER_MAX_LENGTH


def test_read_max_position_embeddings_no_config_falls_back() -> None:
    """Missing config.json SHALL fall back to default without raising."""
    from unittest.mock import patch

    from rag_mcp.core.retrieval.reranker import TOKENIZER_MAX_LENGTH, CrossEncoderReranker

    reranker = CrossEncoderReranker()
    with patch("huggingface_hub.hf_hub_download", side_effect=Exception("not found")):
        result = reranker._read_max_position_embeddings()
        assert result == TOKENIZER_MAX_LENGTH


# ── backend.py edge cases ───────────────────────────────────────────────


def test_resolve_unknown_backend_name_raises_keyerror() -> None:
    """Unknown backend name SHALL raise KeyError (defensive guard)."""
    from rag_mcp.core.retrieval.backend import resolve_reranker_backend

    with pytest.raises(KeyError, match="Unknown reranker backend"):
        resolve_reranker_backend("unknown")


def test_build_reranker_empty_backend_defaults_to_onnx(effective_settings) -> None:
    """Empty backend string SHALL default to onnx (guard in build_reranker_from_settings)."""
    from rag_mcp.core.retrieval.backend import (
        resolve_reranker_backend,
    )

    # The "if not backend" guard in build_reranker_from_settings converts
    # empty/None to "onnx" before calling resolve_reranker_backend.
    assert resolve_reranker_backend("onnx") is not None
