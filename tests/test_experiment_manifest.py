"""Fast tests for the shared D13 runtime manifest (Stage 4, task 4.1).

No network, no models, no Ollama, no Chroma server.  The reranker is a
fake attribute-compatible object; repo facts (git commit, uv.lock hash)
are read from the real worktree, which is cheap and deterministic.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from experiments._lib.manifest import (
    build_runtime_manifest,
    observe_chunking,
    observe_document_reader,
    observe_torch_device,
    scrub_secrets,
    sha256_file,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

_FLAT_D13_FIELDS = {
    "repo_commit",
    "dependency_lock_hash",
    "experiment_id",
    "protocol_version",
    "corpus_identity",
    "query_set_identity",
    "qrels_identity",
}


class _FakeSession:
    """Minimal stand-in for an onnxruntime InferenceSession."""

    @staticmethod
    def get_providers() -> list[str]:
        return ["CPUExecutionProvider"]


class _FakeOnnxReranker:
    """Attribute-compatible stand-in for a loaded CrossEncoderReranker."""

    backend_name = "onnx"
    _model_id = "fake/model"
    _session: Any = _FakeSession()
    last_loaded_variant = "onnx/model_quantized.onnx"
    last_loaded_device = None


def _maximal_manifest(tmp_path: Path) -> dict[str, Any]:
    """Build a manifest with every D13 input populated."""
    corpus = tmp_path / "corpus.jsonl"
    corpus.write_text('{"doc": 1}\n', encoding="utf-8")
    queries = tmp_path / "queries.json"
    queries.write_text("[]", encoding="utf-8")
    qrels = tmp_path / "qrels.json"
    qrels.write_text("{}", encoding="utf-8")
    return build_runtime_manifest(
        experiment_id="unit-manifest",
        protocol_version="1.0",
        embedding={
            "requested_provider": "local",
            "effective_provider": "OllamaEmbedding",
            "model": "nomic-embed-text",
        },
        vector_store={
            "backend": "chroma_local",
            "mode": "persistent_local",
            "score_kind": "dense_similarity_v1",
        },
        sparse={
            "requested_backend": "bm25",
            "effective_backend": "bm25",
            "cache_namespace": "documents",
        },
        reranker=_FakeOnnxReranker(),
        reranker_requested_backend="onnx",
        chunking={"requested": "code", "effective": "code", "fallback_reason": None},
        document_backend={"requested": "pypdf", "effective": "pypdf"},
        retrieval={
            "top_k": 10,
            "fetch_k": 150,
            "hybrid": True,
            "rrf_k": 60,
            "threshold": 0.3,
            "threshold_score_kind": "dense_similarity_v1",
            "rerank_policy_reason": None,
        },
        corpus_path=corpus,
        query_set_path=queries,
        qrels_path=qrels,
        index_identity="idx-unit",
        project_root=REPO_ROOT,
    )


def test_maximal_manifest_has_exact_d13_sections(tmp_path: Path) -> None:
    manifest = _maximal_manifest(tmp_path)

    assert set(manifest["embedding"]) == {"requested_provider", "effective_provider", "model"}
    assert set(manifest["vector_store"]) == {"backend", "mode", "index_identity", "score_kind"}
    assert set(manifest["sparse"]) == {
        "requested_backend",
        "effective_backend",
        "cache_namespace",
    }
    assert set(manifest["reranker"]) == {
        "requested_backend",
        "effective_backend",
        "model",
        "device",
        "execution_provider",
        "variant_or_precision",
    }
    assert set(manifest["chunker"]) == {"requested", "effective", "fallback_reason"}
    assert set(manifest["document_backend"]) == {"requested", "effective"}
    assert set(manifest["retrieval"]) == {
        "top_k",
        "fetch_k",
        "hybrid",
        "rrf_k",
        "threshold",
        "threshold_score_kind",
        "rerank_policy_reason",
    }
    assert _FLAT_D13_FIELDS <= set(manifest)


def test_maximal_manifest_observes_effective_values(tmp_path: Path) -> None:
    manifest = _maximal_manifest(tmp_path)

    assert manifest["experiment_id"] == "unit-manifest"
    assert manifest["protocol_version"] == "1.0"
    assert manifest["corpus_identity"] == sha256_file(tmp_path / "corpus.jsonl")
    assert manifest["query_set_identity"].startswith("sha256:")
    assert manifest["qrels_identity"].startswith("sha256:")
    # The explicit parameter wins over the (absent) mapping key.
    assert manifest["vector_store"]["index_identity"] == "idx-unit"
    assert manifest["reranker"]["requested_backend"] == "onnx"
    assert manifest["reranker"]["effective_backend"] == "onnx"
    assert manifest["reranker"]["model"] == "fake/model"
    assert manifest["reranker"]["execution_provider"] == ["CPUExecutionProvider"]
    assert manifest["reranker"]["variant_or_precision"] == "onnx/model_quantized.onnx"
    assert manifest["chunker"] == {
        "requested": "code",
        "effective": "code",
        "fallback_reason": None,
    }
    # fallback_reason None with a provided observation is by design (no
    # fallback occurred), so it must NOT carry a null reason.
    assert "chunker.fallback_reason" not in manifest["null_reasons"]
    # rerank_policy_reason None inside a provided mapping IS recorded.
    assert "retrieval.rerank_policy_reason" in manifest["null_reasons"]
    assert isinstance(manifest["timestamp_utc"], str)
    assert isinstance(manifest["git_dirty"], bool)


def test_missing_inputs_are_explicit_nulls_with_reasons() -> None:
    manifest = build_runtime_manifest(
        experiment_id="empty",
        protocol_version="1",
        project_root=REPO_ROOT,
    )

    assert manifest["corpus_identity"] is None
    assert "corpus_identity" in manifest["null_reasons"]
    assert manifest["query_set_identity"] is None
    assert manifest["qrels_identity"] is None
    assert all(value is None for value in manifest["reranker"].values())
    for leaf in (
        "effective_backend",
        "model",
        "device",
        "execution_provider",
        "variant_or_precision",
    ):
        assert manifest["reranker"][leaf] is None
        assert f"reranker.{leaf}" in manifest["null_reasons"]
    assert manifest["embedding"]["model"] is None
    assert "embedding.model" in manifest["null_reasons"]
    assert manifest["chunker"]["requested"] is None
    assert "chunker.requested" in manifest["null_reasons"]


def test_requested_backend_recorded_without_reranker_object() -> None:
    manifest = build_runtime_manifest(
        experiment_id="no-object",
        protocol_version="1",
        reranker_requested_backend="onnx",
        project_root=REPO_ROOT,
    )

    assert manifest["reranker"]["requested_backend"] == "onnx"
    assert manifest["reranker"]["effective_backend"] is None
    assert "reranker.requested_backend" not in manifest["null_reasons"]


def test_manifest_json_round_trip(tmp_path: Path) -> None:
    manifest = _maximal_manifest(tmp_path)

    serialised = json.dumps(manifest, sort_keys=True)
    assert json.loads(serialised) == manifest


def test_sha256_file_matches_manual_hash(tmp_path: Path) -> None:
    target = tmp_path / "corpus.txt"
    target.write_text("hello manifest", encoding="utf-8")

    expected = "sha256:" + hashlib.sha256(b"hello manifest").hexdigest()
    assert sha256_file(target) == expected


def test_repo_commit_and_lock_hash_from_real_repo() -> None:
    manifest = build_runtime_manifest(
        experiment_id="repo-facts",
        protocol_version="1",
        project_root=REPO_ROOT,
    )

    assert manifest["repo_commit"] is not None
    assert len(manifest["repo_commit"]) == 40
    assert all(char in "0123456789abcdef" for char in manifest["repo_commit"])
    assert manifest["dependency_lock_hash"] is not None
    assert len(manifest["dependency_lock_hash"]) == 64
    assert manifest["repo_commit"] not in manifest["null_reasons"]
    assert manifest["dependency_lock_hash"] not in manifest["null_reasons"]


def test_git_and_lock_missing_fall_back_to_null(tmp_path: Path) -> None:
    manifest = build_runtime_manifest(
        experiment_id="bare-dir",
        protocol_version="1",
        project_root=tmp_path,
    )

    assert manifest["repo_commit"] is None
    assert manifest["dependency_lock_hash"] is None
    assert manifest["git_dirty"] is None
    assert manifest["null_reasons"]["repo_commit"]
    assert manifest["null_reasons"]["dependency_lock_hash"]
    assert manifest["null_reasons"]["git_dirty"]


def test_observe_document_reader_resolves_auto_and_passes_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from rag_mcp.integrations.pdf import factory

    monkeypatch.setattr(factory, "_resolve_auto", lambda: "liteparse")
    assert observe_document_reader("auto") == {"requested": "auto", "effective": "liteparse"}
    # A concrete requested value passes through without probing.
    assert observe_document_reader("pypdf") == {"requested": "pypdf", "effective": "pypdf"}


def test_observe_chunking_reads_real_code_chunk_result() -> None:
    from rag_mcp.core.chunking.code import CodeChunkResult

    result = CodeChunkResult([], effective_strategy="code")
    assert observe_chunking(result) == {
        "requested": "code",
        "effective": "code",
        "fallback_reason": None,
    }


def test_observe_chunking_accepts_plain_mapping() -> None:
    mapping = {
        "requested": "code",
        "effective": "sentence",
        "fallback_reason": "ValueError: bad parse tree",
    }
    assert observe_chunking(mapping) == mapping


def test_scrub_secrets_redacts_nested_secret_without_mutation(tmp_path: Path) -> None:
    secret = "sk-super-secret-123"  # noqa: S105 — deliberate fake secret to prove redaction
    manifest = build_runtime_manifest(
        experiment_id="scrub",
        protocol_version="1",
        project_root=REPO_ROOT,
        extra={"notes": {"api": f"key {secret} inlined"}},
    )

    scrubbed = scrub_secrets(manifest, [secret])

    assert secret not in json.dumps(scrubbed)
    assert "***" in scrubbed["notes"]["api"]
    # The original manifest is unmutated.
    assert manifest["notes"]["api"] == f"key {secret} inlined"


def test_observe_torch_device_reads_cross_encoder_and_none() -> None:
    class _CrossEncoder:
        device = "mps"

    class _TorchReranker:
        _cross_encoder = _CrossEncoder()

    assert observe_torch_device(_TorchReranker()) == "mps"
    assert observe_torch_device(None) is None


def test_observe_torch_device_prefers_last_loaded_device() -> None:
    class _CrossEncoder:
        device = "mps"

    class _TorchReranker:
        last_loaded_device = "cuda:0"
        _cross_encoder = _CrossEncoder()

    assert observe_torch_device(_TorchReranker()) == "cuda:0"
