"""Unit tests for document ingestion and listing.

Tests cover:
- ingest_path() validation: non-existent path, unsupported extension, empty dir
- list_documents() with no collection
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from rag_mcp.ingestion import ingest_path, list_documents


# ── ingest_path validation ─────────────────────────────────────────────────


class TestIngestPathValidation:
    """Tests for ingest_path() input validation (no Ollama needed)."""

    def test_nonexistent_path_returns_error(self) -> None:
        """ingest_path with a non-existent path must return an error."""
        result = ingest_path("/nonexistent/directory/path")
        assert result["status"] == "error"
        assert "not found" in result["message"].lower()

    def test_unsupported_extension_returns_error(self, tmp_path: Path) -> None:
        """ingest_path with an unsupported file extension must return error."""
        bad_file = tmp_path / "test.xyz"
        bad_file.write_text("some content")
        result = ingest_path(str(bad_file))
        assert result["status"] == "error"
        assert "unsupported" in result["message"].lower()

    def test_empty_directory_returns_success_zero_counts(
        self, tmp_path: Path
    ) -> None:
        """ingest_path on an empty directory must return ok with zero counts."""
        empty_dir = tmp_path / "empty_dir"
        empty_dir.mkdir()
        result = ingest_path(str(empty_dir))
        assert result["status"] == "ok"
        assert result["files_indexed"] == 0
        assert result["chunks_created"] == 0


# ── list_documents ─────────────────────────────────────────────────────────


class TestListDocuments:
    """Tests for list_documents() edge cases."""

    def test_empty_store_returns_empty_list(self) -> None:
        """list_documents() with no indexed documents must return []."""
        result = list_documents()
        assert result == []


# ── 9.5-9.6 Collection routing tests ──────────────────────────────────────


class TestCollectionRouting:
    """Tests for collection-aware ingestion."""

    def test_ingest_into_named_collection(
        self, sample_txt,
    ):
        """ingest_path with collection_name must store in the named collection."""
        from rag_mcp.ingestion import ingest_path

        result = ingest_path(str(sample_txt), collection_name="research")
        assert result["status"] == "ok"
        assert result["collection"] == "research"
        assert result["files_indexed"] == 1

        # Verify the file is in the research collection, not documents
        from rag_mcp.ingestion import list_documents
        research_docs = list_documents(collection_name="research")
        assert len(research_docs) == 1

        # Default collection should be empty
        default_docs = list_documents(collection_name="documents")
        assert len(default_docs) == 0

    def test_ingest_default_collection(
        self, sample_md,
    ):
        """ingest_path without collection_name must use 'documents'."""
        from rag_mcp.ingestion import ingest_path

        result = ingest_path(str(sample_md))
        assert result["status"] == "ok"
        assert result["collection"] == "documents"

    def test_ingest_into_different_collections(
        self, sample_txt, sample_md,
    ):
        """Two files ingested into different collections must be isolated."""
        from rag_mcp.ingestion import ingest_path, list_documents

        # Ingest txt into "research"
        result1 = ingest_path(str(sample_txt), collection_name="research")
        assert result1["collection"] == "research"

        # Ingest md into "code"
        result2 = ingest_path(str(sample_md), collection_name="code")
        assert result2["collection"] == "code"

        # Verify isolation
        research = list_documents(collection_name="research")
        code = list_documents(collection_name="code")
        default = list_documents(collection_name="documents")

        assert len(research) == 1
        assert len(code) == 1
        assert len(default) == 0


# ── 9.7 Metadata attachment tests ──────────────────────────────────────────


class TestMetadataAttachment:
    """Tests for metadata attachment during ingestion."""

    def test_metadata_attached_to_chunks(
        self, tmp_path, monkeypatch,
    ):
        """Metadata must be attached to chunks when METADATA_EXTRACTION_MODE=keyword."""
        # Enable keyword extraction for this test
        import rag_mcp.metadata_extractor as _me
        monkeypatch.setattr(_me, "METADATA_EXTRACTION_MODE", "keyword")
        monkeypatch.setattr(_me, "METADATA_KEYWORD_RULES", None)

        # Create a test file with AI-related content
        test_file = tmp_path / "ai_paper.txt"
        test_file.write_text(
            "The transformer architecture uses attention mechanisms. "
            "Deep learning models with neural networks have revolutionised NLP. "
            "Embeddings capture semantic meaning in vector space."
        )

        from rag_mcp.ingestion import ingest_path

        result = ingest_path(str(test_file), collection_name="test_metadata")
        assert result["status"] == "ok"

        # Verify metadata in ChromaDB
        import chromadb
        from rag_mcp.config import CHROMA_PERSIST_DIR

        db = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
        collection = db.get_collection("test_metadata")
        data = collection.get(include=["metadatas"])

        # At least one chunk should have category metadata
        categories = []
        for meta in data.get("metadatas", []) or []:
            if meta and "category" in meta:
                categories.append(meta["category"])

        assert len(categories) > 0
        # With our test text, it should be categorised as AI
        assert all(c == "AI" for c in categories)

    def test_no_metadata_when_disabled(
        self, tmp_path, monkeypatch,
    ):
        """When METADATA_EXTRACTION_MODE=disabled, no category metadata."""
        # Disable keyword extraction
        import rag_mcp.metadata_extractor as _me
        monkeypatch.setattr(_me, "METADATA_EXTRACTION_MODE", "disabled")

        test_file = tmp_path / "whatever.txt"
        test_file.write_text("Some random content about biology and proteins.")

        from rag_mcp.ingestion import ingest_path

        result = ingest_path(str(test_file), collection_name="test_disabled_meta")
        assert result["status"] == "ok"

        import chromadb
        from rag_mcp.config import CHROMA_PERSIST_DIR

        db = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
        collection = db.get_collection("test_disabled_meta")
        data = collection.get(include=["metadatas"])

        # No chunk should have category metadata
        for meta in data.get("metadatas", []) or []:
            if meta is not None:
                assert "category" not in meta


# ── Document deletion tests ────────────────────────────────────────────────


class TestDocumentDeletion:
    """Tests for remove_document, remove_by_metadata, remove_collection."""

    # ── remove_document ───────────────────────────────────────────────────

    def test_remove_document_deletes_existing_chunks(self, sample_txt):
        """remove_document must delete all chunks for an ingested file."""
        from rag_mcp.ingestion import ingest_path, remove_document, list_documents

        # First ingest
        result = ingest_path(str(sample_txt))
        assert result["status"] == "ok"
        assert result["files_indexed"] == 1

        # Verify chunks exist
        docs_before = list_documents()
        total_before = sum(d["chunks"] for d in docs_before)
        assert total_before > 0

        # Delete the document
        del_result = remove_document(str(sample_txt))
        assert del_result["status"] == "ok"
        assert del_result["chunks_removed"] == total_before

        # Verify no chunks remain
        docs_after = list_documents()
        assert docs_after == []

    def test_remove_document_non_existent_file(self, sample_txt):
        """remove_document on unknown file (collection exists) must return ok."""
        from rag_mcp.ingestion import ingest_path, remove_document

        # First create the collection by ingesting something
        ingest_path(str(sample_txt))

        # Now call remove_document with a different file path
        result = remove_document("/nonexistent/file.pdf")
        assert result["status"] == "ok"
        assert result["chunks_removed"] == 0

    def test_remove_document_non_existent_collection(self):
        """remove_document on non-existent collection must return error."""
        from rag_mcp.ingestion import remove_document

        result = remove_document(
            "/some/file.pdf", collection_name="nonexistent_coll"
        )
        assert result["status"] == "error"
        assert "does not exist" in result.get("message", "").lower()

    # ── remove_by_metadata ────────────────────────────────────────────────

    def test_remove_by_metadata_deletes_matching_chunks(self, tmp_path):
        """remove_by_metadata must delete chunks matching the filter."""
        from rag_mcp.ingestion import (
            ingest_path,
            remove_by_metadata,
            list_documents,
        )

        test_file = tmp_path / "paper.txt"
        test_file.write_text(
            "This is a document about artificial intelligence."
        )
        result = ingest_path(
            str(test_file), collection_name="test_meta_delete"
        )
        assert result["status"] == "ok"

        # Verify chunks exist
        docs = list_documents(collection_name="test_meta_delete")
        total = sum(d["chunks"] for d in docs)
        assert total > 0

        # Delete by file_path metadata
        del_result = remove_by_metadata(
            {"file_path": str(test_file)},
            collection_name="test_meta_delete",
        )
        assert del_result["status"] == "ok"
        assert del_result["chunks_removed"] == total

        # Verify empty
        assert list_documents(collection_name="test_meta_delete") == []

    def test_remove_by_metadata_empty_filter(self):
        """remove_by_metadata with empty filter must return error."""
        from rag_mcp.ingestion import remove_by_metadata

        result = remove_by_metadata({})
        assert result["status"] == "error"
        assert "empty" in result.get("message", "").lower()

    def test_remove_by_metadata_non_existent_collection(self):
        """remove_by_metadata on non-existent collection must return error."""
        from rag_mcp.ingestion import remove_by_metadata

        result = remove_by_metadata(
            {"category": "test"},
            collection_name="nonexistent_coll",
        )
        assert result["status"] == "error"
        assert "does not exist" in result.get("message", "").lower()

    # ── remove_collection ─────────────────────────────────────────────────

    def test_remove_collection_drops_collection(self, sample_txt):
        """remove_collection must permanently delete the collection."""
        from rag_mcp.ingestion import ingest_path, remove_collection
        from rag_mcp.retrieval import list_collections

        # Ingest into a named collection
        result = ingest_path(
            str(sample_txt), collection_name="test_drop_me"
        )
        assert result["status"] == "ok"

        # Verify collection exists
        colls_before = list_collections()
        names_before = {c["name"] for c in colls_before}
        assert "test_drop_me" in names_before

        # Drop it
        drop_result = remove_collection("test_drop_me")
        assert drop_result["status"] == "ok"

        # Verify it's gone
        colls_after = list_collections()
        names_after = {c["name"] for c in colls_after}
        assert "test_drop_me" not in names_after

    def test_remove_collection_non_existent(self):
        """remove_collection on non-existent collection must return error."""
        from rag_mcp.ingestion import remove_collection

        result = remove_collection("nonexistent_coll")
        assert result["status"] == "error"
        assert "does not exist" in result.get("message", "").lower()

    # ── Re-ingestion upsert ───────────────────────────────────────────────

    def test_reingestion_replaces_chunks(self, tmp_path):
        """Re-ingesting same file must replace old chunks (no duplicates)."""
        from rag_mcp.ingestion import ingest_path, list_documents

        test_file = tmp_path / "reingest.txt"
        test_file.write_text(
            "First version of this document. " * 20
        )

        # First ingest
        result1 = ingest_path(
            str(test_file), collection_name="test_reingest"
        )
        assert result1["status"] == "ok"
        chunks1 = result1.get("chunks_created", 0)
        assert chunks1 > 0

        # Verify chunks exist
        docs1 = list_documents(collection_name="test_reingest")
        total1 = sum(d["chunks"] for d in docs1)
        assert total1 == chunks1

        # Modify the file
        test_file.write_text(
            "Second version with different content. " * 30
        )

        # Second ingest (should replace, not append)
        result2 = ingest_path(
            str(test_file), collection_name="test_reingest"
        )
        assert result2["status"] == "ok"
        chunks2 = result2.get("chunks_created", 0)
        assert chunks2 > 0

        # Verify total chunks are from the second ingest only (no duplicates)
        docs2 = list_documents(collection_name="test_reingest")
        total2 = sum(d["chunks"] for d in docs2)
        # The total should be exactly the new chunks (not old + new)
        assert total2 == chunks2
        # The chunks_removed should match the old count
        assert result2.get("chunks_removed", 0) == chunks1

    def test_reingestion_first_time_no_removed(self, tmp_path):
        """First-time ingest must show chunks_removed: 0."""
        from rag_mcp.ingestion import ingest_path

        test_file = tmp_path / "first.txt"
        test_file.write_text("Brand new document never ingested before.")

        result = ingest_path(
            str(test_file), collection_name="test_first_ingest"
        )
        assert result["status"] == "ok"
        assert result["chunks_removed"] == 0
        assert result["chunks_created"] > 0
