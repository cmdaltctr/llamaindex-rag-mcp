"""Embedding-text composition contract (fix-embedding-and-structure-fidelity-1).

Red-first coverage for the 2026-09-01 audit finding: only the eight lineage
keys are excluded from embedding text, so reader diagnostics (``pdf_reader``,
``pdf_type``, ``pdf_confidence``, ``page_count``) and the machine-specific
``file_path`` are embedded into every PDF chunk vector.

Spec: openspec/changes/fix-embedding-and-structure-fidelity-1/specs/
embedding-text-composition/spec.md — "Embedding text is a declared contract".

The chunk under test is produced by the real production read-and-chunk path
with the real ``pdf_inspector`` package (the configured default reader),
then stamped through ``stamp_source_lineage`` exactly as the replacement
path does — that function is the single owner of the exclusion contract
(design D1). Filesystem bookkeeping and extracted-metadata keys are
completed onto the nodes to the shape the reader chain and metadata ladder
produce, so every declared key is genuinely asserted rather than trivially
absent.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from llama_index.core.schema import MetadataMode

from rag_mcp.core.ingestion.chunker import read_and_chunk_file_async
from rag_mcp.core.ingestion.source_state import stamp_source_lineage

#: Parser telemetry named by the spec scenario "Parser telemetry never
#: reaches the embedding model".
TELEMETRY_KEYS = (
    "pdf_reader",
    "pdf_type",
    "pdf_confidence",
    "page_count",
)

#: Filesystem bookkeeping named by the spec scenario "Filesystem
#: bookkeeping never reaches the embedding model".
BOOKKEEPING_KEYS = (
    "file_path",
    "file_type",
    "file_size",
    "creation_date",
    "last_modified_date",
    "last_accessed_date",
)

#: Keys the spec requires to survive in embedding text (design D2 keeps
#: ``file_name``; the extraction ladder output carries topical signal).
RETAINED_KEYS = (
    "file_name",
    "category",
    "keywords",
    "summary",
)

#: Distinctive values that must never leak into embedding text even if a
#: renderer changed its ``key: value`` layout.
_FORBIDDEN_VALUES = (
    "pdf_inspector",  # pdf_reader value
    "text_based",  # pdf_type value
)


async def _stamped_pdf_inspector_nodes(fixtures_dir: Path, effective_settings) -> list:
    """Return pdf_inspector-parsed, lineage-stamped nodes for the smoke PDF.

    Reads ``smoke_text.pdf`` through the production reader chain with the
    real ``pdf_inspector`` package, completes the metadata to the shape the
    reader chain (filesystem bookkeeping) and metadata ladder (category,
    keywords, summary) produce on ingest, and stamps lineage through the
    same function the replacement path calls.
    """
    settings = effective_settings(
        pdf_reader="pdf_inspector",
        # The factory builds fresh blocks with class defaults; pin the
        # conftest-tested extraction mode so the helper never performs
        # real LLM calls (conftest docstring: class defaults hang tests).
        extraction_mode="disabled",
    )
    pdf = fixtures_dir / "smoke_text.pdf"
    nodes = await read_and_chunk_file_async(
        pdf,
        chunk_size=512,
        chunk_overlap=50,
        content_type=None,
        fallback_strategy="auto",
        taxonomy_mode="off",
        settings=settings,
    )
    assert nodes, "smoke_text.pdf must produce at least one chunk"
    for node in nodes:
        node.metadata.update(
            {
                # Filesystem bookkeeping the reader chain attaches when a
                # file is read without a custom extractor (the production
                # shape for non-PDF files; completed here so every declared
                # key is present and every absence is the contract's doing).
                "file_type": "application/pdf",
                "file_size": 4096,
                "creation_date": "2026-09-01T00:00:00+00:00",
                "last_modified_date": "2026-09-01T00:00:00+00:00",
                "last_accessed_date": "2026-09-01T00:00:00+00:00",
                # Extracted-metadata shape the chunker flattens onto nodes
                # when the metadata ladder is enabled (lists become
                # ", "-joined strings, so the string form is the stored
                # production shape).
                "category": "testing",
                "keywords": "embedding, metadata, contract",
                "summary": "A smoke document for the embedding-text contract.",
            }
        )
    stamp_source_lineage(
        nodes,
        file_path=str(pdf),
        source_id="src_embedding_text_contract",
        content_hash="c" * 64,
        index_identity="i" * 64,
        source_version="v" * 64,
        source_attempt="attempt-contract-1",
    )
    return nodes


class TestTelemetryNeverReachesEmbeddingModel:
    """Task 1.1 — parser telemetry and filesystem bookkeeping stay out."""

    async def test_pdf_inspector_chunk_embed_text_excludes_declared_keys(
        self, fixtures_dir, effective_settings
    ) -> None:
        """No declared telemetry or bookkeeping key renders into EMBED text."""
        nodes = await _stamped_pdf_inspector_nodes(fixtures_dir, effective_settings)

        for node in nodes:
            embed_text = node.get_content(metadata_mode=MetadataMode.EMBED)
            for key in (*TELEMETRY_KEYS, *BOOKKEEPING_KEYS):
                assert f"{key}:" not in embed_text, (
                    f"{key!r} leaked into embedding text: {embed_text[:200]!r}"
                )
            for value in _FORBIDDEN_VALUES:
                assert value not in embed_text
            # The machine-specific source path must not leak either.
            assert str(fixtures_dir) not in embed_text

    async def test_pdf_inspector_chunk_embed_text_keeps_chunk_text(
        self, fixtures_dir, effective_settings
    ) -> None:
        """The chunk's own text survives the exclusion contract unchanged."""
        nodes = await _stamped_pdf_inspector_nodes(fixtures_dir, effective_settings)

        node = nodes[0]
        embed_text = node.get_content(metadata_mode=MetadataMode.EMBED)
        bare_text = node.get_content(metadata_mode=MetadataMode.NONE)
        assert bare_text in embed_text
        assert "Smoke Test Document" in embed_text


class TestExtractedMetadataIsRetained:
    """Task 1.2 — topical-signal keys stay in embedding text (design D2)."""

    async def test_pdf_inspector_chunk_embed_text_retains_signal_keys(
        self, fixtures_dir, effective_settings
    ) -> None:
        """file_name, category, keywords, summary remain present when present."""
        nodes = await _stamped_pdf_inspector_nodes(fixtures_dir, effective_settings)

        for node in nodes:
            embed_text = node.get_content(metadata_mode=MetadataMode.EMBED)
            for key in RETAINED_KEYS:
                assert f"{key}:" in embed_text, (
                    f"{key!r} missing from embedding text: {embed_text[:200]!r}"
                )
            assert "smoke_text.pdf" in embed_text
            assert "embedding, metadata, contract" in embed_text


class TestExclusionSetConstant:
    """Task 2.1 — the declared constant covers exactly the spec's keys."""

    def test_constant_contains_every_declared_key(self) -> None:
        """All telemetry and bookkeeping keys from the spec are members."""
        from rag_mcp.core.ingestion.source_state import EXCLUDED_EMBED_METADATA_KEYS

        members = set(EXCLUDED_EMBED_METADATA_KEYS)
        for key in (*TELEMETRY_KEYS, *BOOKKEEPING_KEYS):
            assert key in members
        # Page provenance and layout telemetry declared by the spec's
        # "Parser telemetry never reaches the embedding model" scenario.
        for key in ("page", "page_label", "column", "section_bbox", "bbox_schema_version"):
            assert key in members

    def test_constant_never_excludes_retained_keys(self) -> None:
        """Design D2: retained signal keys are absent from the exclusion set."""
        from rag_mcp.core.ingestion.source_state import EXCLUDED_EMBED_METADATA_KEYS

        members = set(EXCLUDED_EMBED_METADATA_KEYS)
        for key in (*RETAINED_KEYS, "header_path", "document_title", "content_type"):
            assert key not in members


class TestExclusionSetParticipatesInIdentity:
    """Task 1.6 — exclusion-set changes must invalidate source identity.

    Stage A covers the mechanism half: the canonicalisation
    ``build_index_identity`` uses (sorted-key JSON, SHA-256) is sensitive to
    the exclusion set, so folding ``EXCLUDED_EMBED_METADATA_KEYS`` into the
    identity payload (group 3, tasks 3.1-3.2) invalidates precisely when
    the set changes. The identity-level and reprocess-not-skip assertions
    land with group 3 and are pinned by the skipped test below.
    """

    @staticmethod
    def _fingerprint(keys) -> str:
        """Canonicalise a key set exactly as the identity payload does."""
        return hashlib.sha256(
            json.dumps(
                sorted(keys), separators=(",", ":"), ensure_ascii=True
            ).encode("utf-8")
        ).hexdigest()

    def test_fingerprint_is_sensitive_to_the_exclusion_set(self) -> None:
        """Removing one key changes the canonical fingerprint."""
        from rag_mcp.core.ingestion.source_state import EXCLUDED_EMBED_METADATA_KEYS

        baseline = self._fingerprint(EXCLUDED_EMBED_METADATA_KEYS)
        assert baseline == self._fingerprint(EXCLUDED_EMBED_METADATA_KEYS)
        for dropped in EXCLUDED_EMBED_METADATA_KEYS:
            reduced = [k for k in EXCLUDED_EMBED_METADATA_KEYS if k != dropped]
            assert self._fingerprint(reduced) != baseline, (
                f"dropping {dropped!r} did not change the fingerprint"
            )

    def test_identity_is_deterministic_for_identical_inputs(self, effective_settings) -> None:
        """Unchanged settings produce an unchanged identity (skip precondition)."""
        from rag_mcp.core.ingestion.source_state import build_index_identity

        settings = effective_settings()
        first = build_index_identity(
            settings, content_type=None, chunk_size=512, chunk_overlap=50
        )
        second = build_index_identity(
            settings, content_type=None, chunk_size=512, chunk_overlap=50
        )
        assert first == second

    def test_changing_the_exclusion_set_changes_source_index_identity(
        self, effective_settings, monkeypatch
    ) -> None:
        """Stage B (group 3): identity absorbs the exclusion set.

        Once task 3.2 folds ``EXCLUDED_EMBED_METADATA_KEYS`` into the
        identity payload, an otherwise byte-identical source under an
        unchanged everything-else must get a NEW ``source_index_identity``
        (so ``is_complete_current_version`` reports it not-current and the
        source is reprocessed rather than reported
        ``skipped_unchanged``). Remove this skip when group 3 lands.
        """
        import pytest

        pytest.skip(
            "Stage B (group 3, tasks 3.1-3.2): build_index_identity does not "
            "yet fold EXCLUDED_EMBED_METADATA_KEYS into its payload. Remove "
            "this skip when the identity change lands; the assertion body "
            "below is the stage-B acceptance."
        )
        import rag_mcp.core.ingestion.source_state as source_state
        from rag_mcp.core.ingestion.source_state import (
            EXCLUDED_EMBED_METADATA_KEYS,
            build_index_identity,
        )

        settings = effective_settings()
        before = build_index_identity(
            settings, content_type=None, chunk_size=512, chunk_overlap=50
        )
        reduced = tuple(k for k in EXCLUDED_EMBED_METADATA_KEYS if k != "page_count")
        monkeypatch.setattr(source_state, "EXCLUDED_EMBED_METADATA_KEYS", reduced)
        after = build_index_identity(
            settings, content_type=None, chunk_size=512, chunk_overlap=50
        )
        assert after != before, (
            "source_index_identity ignored the embedding-text exclusion set"
        )
