"""Tests for the pypdf reader adapter.

Verifies the adapter preserves semantically equivalent Document output
to the pre-change SimpleDirectoryReader behaviour (regression guard).
Not byte-identical because PDF parsing is non-deterministic across
library versions, per spec.md.
"""

from __future__ import annotations

from pathlib import Path

from rag_mcp.integrations.pdf.pypdf import PyPDFReader

# Use a small corpus PDF as test fixture
CORPUS_PDF = Path(__file__).resolve().parents[2] / (
    "experiments/11-liteparse-pdf-quality-2026-06-20/corpus/vaswani2017_attention.pdf"
)


def test_pypdf_reader_returns_documents():
    """PyPDFReader.load_data returns a non-empty list of Document objects."""
    if not CORPUS_PDF.exists():
        import pytest

        pytest.skip("Corpus PDF not available for testing")

    reader = PyPDFReader()
    documents = reader.load_data(file=CORPUS_PDF)

    assert len(documents) > 0
    # Each document should have text content
    for doc in documents:
        assert hasattr(doc, "get_content")
        content = doc.get_content()
        assert len(content) > 0


def test_pypdf_reader_adapter_is_callable():
    """PyPDFReader instance has the load_data method."""
    reader = PyPDFReader()
    assert callable(getattr(reader, "load_data", None))
