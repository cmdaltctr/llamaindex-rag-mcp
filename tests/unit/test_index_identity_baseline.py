"""Stage 1 baseline record for ``source_index_identity`` (task 1.9).

Pins the CURRENT payload shape emitted by ``build_index_identity`` and the
current ``_INDEX_IDENTITY_SCHEMA`` value, so the stage 2/3 identity
extensions (OCR routing in task 2.13, tokenizer/splitter in task 3.11)
land as a visible, reviewable diff instead of an incidental change.

The payload is captured by wrapping the module-local ``json`` binding, so
the recorded structure is exactly what gets canonicalised and hashed —
not a re-implementation of the payload builder.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from omrg.core.ingestion import source_state
from omrg.core.settings import EffectiveSettings, MetadataBlock

EXPECTED_TOP_LEVEL_KEYS = {
    "schema",
    "embedding",
    "embedding_text",
    "parser",
    "chunking",
    "metadata_shape",
}
EXPECTED_EMBEDDING_KEYS = {"runtime", "configured_provider", "configured_model"}
EXPECTED_EMBEDDING_TEXT_KEYS = {"excluded_keys"}
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
    settings = EffectiveSettings(metadata=MetadataBlock(extraction_mode="disabled"))
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
    """Baseline: the schema is 3 before the OCR/tokenizer extensions bump it."""
    assert source_state._INDEX_IDENTITY_SCHEMA == 3


def test_index_identity_payload_shape_is_recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the exact key structure of the schema-3 payload (task 1.9).

    Stage 2/3 add ``ocr_routing``/``ocr_capability`` and
    ``tokenizer``/``resolved_splitter`` blocks alongside the existing ones
    and bump the schema once; this pin makes that diff reviewable.
    """
    payload, _ = _baseline_payload(monkeypatch)

    assert set(payload) == EXPECTED_TOP_LEVEL_KEYS
    assert payload["schema"] == 3
    assert set(payload["embedding"]) == EXPECTED_EMBEDDING_KEYS
    assert set(payload["embedding_text"]) == EXPECTED_EMBEDDING_TEXT_KEYS
    assert set(payload["parser"]) == EXPECTED_PARSER_KEYS
    assert set(payload["chunking"]) == EXPECTED_CHUNKING_KEYS
    assert set(payload["chunking"]["settings"]) == EXPECTED_CHUNKING_SETTINGS_KEYS
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


def test_recorded_payload_is_exactly_what_is_hashed(monkeypatch: pytest.MonkeyPatch) -> None:
    """The captured structure is the canonicalised input to the sha256."""
    payload, identity = _baseline_payload(monkeypatch)

    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    assert identity == hashlib.sha256(canonical.encode("utf-8")).hexdigest()
