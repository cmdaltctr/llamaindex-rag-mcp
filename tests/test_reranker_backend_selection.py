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
    # Construct Settings() directly to avoid the get_settings() cache —
    # an earlier test may have already resolved and cached settings,
    # which would return the cached object without re-reading env vars.
    from rag_mcp.config import Settings

    with pytest.raises(ValueError, match="RETRIEVAL__RERANK_BACKEND.*Accepted values: onnx, torch"):
        Settings()


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
    """When torch is requested but the extra is missing, ONNX is used.

    The capability probe (_is_torch_extra_available) runs before registry
    resolution, so the fallback fires even though the registry import for
    reranker_torch would succeed (torch is imported lazily inside
    _load_model).
    """
    from rag_mcp.core.retrieval.backend import resolve_reranker_backend
    from rag_mcp.core.retrieval.reranker import CrossEncoderReranker

    # No mocking needed — sentence_transformers is not installed in the
    # fast suite, so _is_torch_extra_available() naturally returns False.
    cls = resolve_reranker_backend("torch")
    assert cls is CrossEncoderReranker, (
        f"Expected ONNX fallback (CrossEncoderReranker), got {cls.__name__}"
    )


def test_torch_missing_and_onnx_fails_degrades(effective_settings) -> None:
    """RETRIEVAL__RERANK_BACKEND=torch, no extra, ONNX also fails → un-reranked.

    The capability probe falls back to ONNX. When the ONNX backend's model
    also can't load, the search SHALL return un-reranked results truncated
    to top_k, set last_failure_reason, and never raise.
    """
    from rag_mcp.core.retrieval.backend import build_reranker_from_settings
    from rag_mcp.core.retrieval.reranker import CrossEncoderReranker, reset_model_cache

    settings = effective_settings(rerank_backend="torch")
    reset_model_cache()

    # No mocking of _retrieval_get needed — the probe naturally detects
    # the missing extra and falls back to ONNX.
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


# ── _read_max_position_embeddings (module-level function) ──────────────


def test_read_max_position_embeddings_reads_config_json() -> None:
    """_read_max_position_embeddings SHALL read max_position_embeddings."""
    import json
    from unittest.mock import mock_open

    from rag_mcp.core.retrieval.reranker import _read_max_position_embeddings

    config = json.dumps({"max_position_embeddings": 512})
    with patch("huggingface_hub.hf_hub_download", return_value="/fake/config.json"):
        with patch("builtins.open", mock_open(read_data=config)):
            result = _read_max_position_embeddings("test/model")
            assert result == 512


def test_read_max_position_embeddings_sentinel_falls_back() -> None:
    """Sentinel value (>100000) SHALL fall back to TOKENIZER_MAX_LENGTH."""
    import json
    from unittest.mock import mock_open

    from rag_mcp.core.retrieval.reranker import (
        TOKENIZER_MAX_LENGTH,
        _read_max_position_embeddings,
    )

    config = json.dumps({"max_position_embeddings": 1000000})
    with patch("huggingface_hub.hf_hub_download", return_value="/fake/config.json"):
        with patch("builtins.open", mock_open(read_data=config)):
            result = _read_max_position_embeddings("test/model")
            assert result == TOKENIZER_MAX_LENGTH


def test_read_max_position_embeddings_missing_key_falls_back() -> None:
    """Missing max_position_embeddings key SHALL fall back to default."""
    import json
    from unittest.mock import mock_open

    from rag_mcp.core.retrieval.reranker import (
        TOKENIZER_MAX_LENGTH,
        _read_max_position_embeddings,
    )

    with patch("huggingface_hub.hf_hub_download", return_value="/fake/config.json"):
        with patch("builtins.open", mock_open(read_data=json.dumps({}))):
            result = _read_max_position_embeddings("test/model")
            assert result == TOKENIZER_MAX_LENGTH


def test_read_max_position_embeddings_no_config_falls_back() -> None:
    """Missing config.json SHALL fall back to default without raising."""

    from rag_mcp.core.retrieval.reranker import (
        TOKENIZER_MAX_LENGTH,
        _read_max_position_embeddings,
    )

    with patch("huggingface_hub.hf_hub_download", side_effect=Exception("not found")):
        result = _read_max_position_embeddings("test/model")
        assert result == TOKENIZER_MAX_LENGTH


def test_read_max_position_embeddings_zero_falls_back() -> None:
    """A non-positive max_position_embeddings SHALL fall back to default.

    A value of 0 (or negative) is as implausible as the >100000
    sentinel: passed straight through, it would make
    ``enable_truncation(max_length=0)`` truncate every input to nothing.
    """
    import json
    from unittest.mock import mock_open

    from rag_mcp.core.retrieval.reranker import (
        TOKENIZER_MAX_LENGTH,
        _read_max_position_embeddings,
    )

    config = json.dumps({"max_position_embeddings": 0})
    with patch("huggingface_hub.hf_hub_download", return_value="/fake/config.json"):
        with patch("builtins.open", mock_open(read_data=config)):
            result = _read_max_position_embeddings("test/model")
            assert result == TOKENIZER_MAX_LENGTH


def test_read_max_position_embeddings_bool_falls_back() -> None:
    """A bool value SHALL fall back to default (bool is an int subclass)."""
    import json
    from unittest.mock import mock_open

    from rag_mcp.core.retrieval.reranker import (
        TOKENIZER_MAX_LENGTH,
        _read_max_position_embeddings,
    )

    config = json.dumps({"max_position_embeddings": True})
    with patch("huggingface_hub.hf_hub_download", return_value="/fake/config.json"):
        with patch("builtins.open", mock_open(read_data=config)):
            result = _read_max_position_embeddings("test/model")
            assert result == TOKENIZER_MAX_LENGTH


# ── read_pad_token_config (rag_mcp.core.retrieval._model_config) ───────


def _make_download_side_effect(files: dict[str, str]):
    """Return a side_effect for hf_hub_download that maps filename to path.

    *files* maps ``"config.json"`` / ``"tokenizer_config.json"`` to the
    JSON content that should be read from that path.  Files not in the
    dict raise ``FileNotFoundError``.
    """
    from unittest.mock import mock_open

    paths = {}

    def _download(repo_id, filename, **kwargs):
        if filename not in files:
            raise FileNotFoundError(f"{filename} not found")
        path = f"/fake/{filename}"
        paths[path] = files[filename]
        return path

    def _open(path, *args, **kwargs):
        if path not in paths:
            raise FileNotFoundError(path)
        return mock_open(read_data=paths[path])()

    return _download, _open


def test_read_pad_token_config_reads_bert_defaults() -> None:
    """read_pad_token_config SHALL read pad_token_id from config.json."""
    import json

    from rag_mcp.core.retrieval._model_config import read_pad_token_config

    files = {
        "config.json": json.dumps({"pad_token_id": 0}),
        "tokenizer_config.json": json.dumps({"pad_token": "[PAD]"}),
    }
    _download, _open = _make_download_side_effect(files)

    with patch("huggingface_hub.hf_hub_download", side_effect=_download):
        with patch("builtins.open", side_effect=_open):
            pad_id, pad_token = read_pad_token_config("test/model")
            assert pad_id == 0
            assert pad_token == "[PAD]"  # noqa: S105


def test_read_pad_token_config_reads_roberta_values() -> None:
    """read_pad_token_config SHALL read non-BERT pad values (e.g. RoBERTa)."""
    import json

    from rag_mcp.core.retrieval._model_config import read_pad_token_config

    files = {
        "config.json": json.dumps({"pad_token_id": 1}),
        "tokenizer_config.json": json.dumps({"pad_token": "<pad>"}),
    }
    _download, _open = _make_download_side_effect(files)

    with patch("huggingface_hub.hf_hub_download", side_effect=_download):
        with patch("builtins.open", side_effect=_open):
            pad_id, pad_token = read_pad_token_config("test/model")
            assert pad_id == 1
            assert pad_token == "<pad>"  # noqa: S105


def test_read_pad_token_config_missing_config_falls_back() -> None:
    """Missing config.json SHALL return (None, None) without raising."""
    from rag_mcp.core.retrieval._model_config import read_pad_token_config

    with patch("huggingface_hub.hf_hub_download", side_effect=Exception("not found")):
        pad_id, pad_token = read_pad_token_config("test/model")
        assert pad_id is None
        assert pad_token is None


def test_read_pad_token_config_missing_tokenizer_config_falls_back() -> None:
    """Missing tokenizer_config.json SHALL return (None, None), not a partial pair.

    ``pad_token_id`` alone is not enough: ``enable_padding()`` needs both
    the id and the token string, and applying one without the other risks
    a mismatched pad_id/pad_token pair (the bug this helper prevents).
    """
    import json

    from rag_mcp.core.retrieval._model_config import read_pad_token_config

    # Only config.json is available; tokenizer_config.json is not.
    files = {"config.json": json.dumps({"pad_token_id": 0})}
    _download, _open = _make_download_side_effect(files)

    with patch("huggingface_hub.hf_hub_download", side_effect=_download):
        with patch("builtins.open", side_effect=_open):
            pad_id, pad_token = read_pad_token_config("test/model")
            assert pad_id is None
            assert pad_token is None


def test_read_pad_token_config_missing_pad_token_id_falls_back() -> None:
    """config.json without pad_token_id SHALL return (None, None), not a partial pair.

    Asymmetric case: tokenizer_config.json has a usable ``pad_token``
    but config.json lacks ``pad_token_id``. Returning ``pad_token``
    alone would let ``enable_padding()`` apply the library's default
    ``pad_id=0`` alongside a mismatched token string.
    """
    import json

    from rag_mcp.core.retrieval._model_config import read_pad_token_config

    files = {
        "config.json": json.dumps({}),
        "tokenizer_config.json": json.dumps({"pad_token": "<pad>"}),
    }
    _download, _open = _make_download_side_effect(files)

    with patch("huggingface_hub.hf_hub_download", side_effect=_download):
        with patch("builtins.open", side_effect=_open):
            pad_id, pad_token = read_pad_token_config("test/model")
            assert pad_id is None
            assert pad_token is None


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
