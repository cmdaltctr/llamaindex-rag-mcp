"""Baseline record for ``source_index_identity`` (task 1.9, updated by 2.13).

Pins the CURRENT payload shape emitted by ``build_index_identity`` and the
current ``_INDEX_IDENTITY_SCHEMA`` value, so the tokenizer and resolved
splitter extension remains a visible, reviewable diff instead of an
incidental change. Task 2.13 itself was reviewed exactly
this way: the pre-change pin recorded schema 3 with top-level keys
``schema/embedding/embedding_text/parser/chunking/metadata_shape`` and
neither OCR block; the diff to this file shows the schema-4 extension
(OCR routing + resolved worker fingerprint).

The payload is captured by wrapping the module-local ``json`` binding, so
the recorded structure is exactly what gets canonicalised and hashed —
not a re-implementation of the payload builder.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from omrg.core.ingestion import source_state
from omrg.core.settings import EmbeddingBlock, EffectiveSettings, MetadataBlock

EXPECTED_TOP_LEVEL_KEYS = {
    "schema",
    "embedding",
    "embedding_text",
    "tokenizer",
    "resolved_splitter",
    "parser",
    "chunking",
    "ocr_routing",
    "ocr_worker_fingerprint",
    "metadata_shape",
}
EXPECTED_EMBEDDING_KEYS = {"runtime", "configured_provider", "configured_model"}
EXPECTED_EMBEDDING_TEXT_KEYS = {"excluded_keys"}
EXPECTED_TOKENIZER_KEYS = {"model", "revision"}
EXPECTED_PARSER_KEYS = {
    "content_type",
    "text_format",
    "document_backend",
    "pdf_reader",
    "liteparse_num_workers",
    "liteparse_ocr_enabled",
    "azure_doc_intelligence_model",
}
EXPECTED_CHUNKING_KEYS = {"settings", "effective_chunk_size", "effective_chunk_overlap"}
EXPECTED_CHUNKING_SETTINGS_KEYS = {
    "chunk_size",
    "chunk_overlap",
    "markdown_chunk_size",
    "code_chunk_lines",
    "code_chunk_lines_overlap",
    "code_max_chars",
    "markdown_heading_prepend",
    "markdown_min_chunk_fraction",
    "strategy_fallback",
}
EXPECTED_OCR_ROUTING_KEYS = {"enabled", "min_confidence", "page_fraction"}
EXPECTED_OCR_FINGERPRINT_KEYS = {
    "available",
    "protocol_version",
    "packages",
    "pipeline_identity",
    "pipeline_revision",
    "model_identity",
    "model_revision",
    "output_schema_id",
    "output_schema_version",
}
EXPECTED_METADATA_SHAPE_KEYS = {
    "extraction_mode",
    "keyword_rules",
    "ollama_classify_model",
    "taxonomy_mode",
    "classify_max_attempts",
    "classify_timeout",
    "pipeline_timeout",
    "llamacpp_classify_timeout_override",
    "ollama_classify_timeout_override",
    "openrouter_classify_timeout_override",
    "llamacpp_pipeline_timeout_override",
    "ollama_pipeline_timeout_override",
    "openrouter_pipeline_timeout_override",
    "metadata_llm_provider",
    "local_backend",
    "cloud_backend",
    "llamacpp_chat_model",
    "openrouter_llm_model",
}


class _RecordingJSON:
    """Module-local json shim that records every payload handed to dumps()."""

    def __init__(self) -> None:
        self.payloads: list = []

    def dumps(self, payload, **kwargs):
        self.payloads.append(payload)
        return json.dumps(payload, **kwargs)


def _baseline_payload(monkeypatch: pytest.MonkeyPatch) -> tuple[dict, str]:
    # The tokenizer fields pin the empty legacy identity: this baseline
    # pins the schema-4 payload shape deterministically, and the promoted
    # packaged default (ADR-063) would otherwise resolve against the
    # machine's Hugging Face cache, varying the payload between machines.
    settings = EffectiveSettings(
        metadata=MetadataBlock(extraction_mode="disabled"),
        embedding=EmbeddingBlock(tokenizer_model="", tokenizer_revision=""),
    )
    recorder = _RecordingJSON()
    monkeypatch.setattr(source_state, "json", recorder)

    identity = source_state.build_index_identity(
        settings,
        content_type="text/plain",
        chunk_size=512,
        chunk_overlap=100,
    )
    assert len(recorder.payloads) == 1
    return recorder.payloads[0], identity


def test_index_identity_schema_value_is_pinned() -> None:
    """Baseline: schema is 4 after task 2.13's single shared Stage 2/3 bump.

    The pre-change pin (task 1.9) recorded schema 3; task 2.13 raised it
    exactly once for the OCR routing gate and resolved worker fingerprint,
    and task 3.11 extends the SAME schema-4 payload with the tokenizer
    identity and resolved splitter instead of bumping again.
    """
    assert source_state._INDEX_IDENTITY_SCHEMA == 4


def test_index_identity_payload_shape_is_recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the exact key structure of the schema-4 payload after Stage 3."""
    payload, _ = _baseline_payload(monkeypatch)

    assert set(payload) == EXPECTED_TOP_LEVEL_KEYS
    assert payload["schema"] == 4
    assert set(payload["embedding"]) == EXPECTED_EMBEDDING_KEYS
    assert set(payload["embedding_text"]) == EXPECTED_EMBEDDING_TEXT_KEYS
    assert set(payload["tokenizer"]) == EXPECTED_TOKENIZER_KEYS
    assert payload["resolved_splitter"] == "legacy_fallback"
    assert set(payload["parser"]) == EXPECTED_PARSER_KEYS
    assert set(payload["chunking"]) == EXPECTED_CHUNKING_KEYS
    assert set(payload["chunking"]["settings"]) == EXPECTED_CHUNKING_SETTINGS_KEYS
    assert set(payload["ocr_routing"]) == EXPECTED_OCR_ROUTING_KEYS
    assert set(payload["ocr_worker_fingerprint"]) == EXPECTED_OCR_FINGERPRINT_KEYS
    assert set(payload["metadata_shape"]) == EXPECTED_METADATA_SHAPE_KEYS


def test_index_identity_payload_values_echo_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    """The recorded payload echoes the injected settings, not ambient state."""
    payload, _ = _baseline_payload(monkeypatch)

    assert payload["parser"]["content_type"] == "text/plain"
    assert payload["parser"]["text_format"] is None
    assert payload["chunking"]["effective_chunk_size"] == 512
    assert payload["chunking"]["effective_chunk_overlap"] == 100
    assert payload["embedding_text"]["excluded_keys"] == sorted(
        source_state.EXCLUDED_EMBED_METADATA_KEYS
    )
    assert payload["tokenizer"] == {"model": "", "revision": ""}
    # Direct callers that pass no OCR keyword arguments still get the
    # complete identity: routing falls back to the settings values and
    # the fingerprint contributes the stable unavailable payload.
    assert payload["ocr_routing"] == {
        "enabled": False,
        "min_confidence": 0.0,
        "page_fraction": 0.0,
    }
    fingerprint = payload["ocr_worker_fingerprint"]
    assert fingerprint["available"] is False
    assert fingerprint["protocol_version"] == ""
    assert fingerprint["packages"] == ()


def test_index_identity_tracks_resolved_markdown_chunking() -> None:
    """Tokenizer identity and the resolved splitter change the index identity."""
    settings = EffectiveSettings(
        metadata=MetadataBlock(extraction_mode="disabled"),
    )
    legacy = source_state.build_index_identity(
        settings,
        content_type="text/markdown",
        chunk_size=512,
        chunk_overlap=100,
        tokenizer={"model": "Qwen/Qwen3-Embedding-4B", "revision": "r1"},
        resolved_splitter="legacy_fallback",
    )
    model_aware = source_state.build_index_identity(
        settings,
        content_type="text/markdown",
        chunk_size=512,
        chunk_overlap=100,
        tokenizer={"model": "Qwen/Qwen3-Embedding-4B", "revision": "r1"},
        resolved_splitter="model_token_aware",
    )
    different_revision = source_state.build_index_identity(
        settings,
        content_type="text/markdown",
        chunk_size=512,
        chunk_overlap=100,
        tokenizer={"model": "Qwen/Qwen3-Embedding-4B", "revision": "r2"},
        resolved_splitter="model_token_aware",
    )

    assert legacy != model_aware
    assert model_aware != different_revision


def test_recorded_payload_is_exactly_what_is_hashed(monkeypatch: pytest.MonkeyPatch) -> None:
    """The captured structure is the canonicalised input to the sha256."""
    payload, identity = _baseline_payload(monkeypatch)

    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    assert identity == hashlib.sha256(canonical.encode("utf-8")).hexdigest()
