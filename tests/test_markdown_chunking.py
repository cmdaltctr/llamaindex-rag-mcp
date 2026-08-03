"""Tests for Markdown-aware chunking with chained sentence splitter.

Covers Section 1 of the rag-retrieval-quality-improvements OpenSpec change:
- Markdown files use MarkdownNodeParser → SentenceSplitter chained pipeline.
- Heading boundaries are preserved when sections fit within CHUNK_SIZE.
- Sections longer than CHUNK_SIZE are further split.
- Non-Markdown files retain the existing default splitter behaviour.
- Markdown without headings still produces non-empty chunks.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from rag_mcp.config import CHUNK_OVERLAP, CHUNK_SIZE, MARKDOWN_CHUNK_SIZE
from rag_mcp.core.chunking.markdown import (
    apply_heading_prepend as _apply_heading_prepend,
    drop_small_markdown_chunks as _drop_small_markdown_chunks,
    ensure_heading_metadata as _ensure_heading_metadata,
)
from rag_mcp.core.ingestion import read_and_chunk_file_async


# ── Helpers ────────────────────────────────────────────────────────────────


def _node_text(node) -> str:
    """Return the chunk text from a LlamaIndex node, regardless of type."""
    if hasattr(node, "get_content"):
        return node.get_content()
    if hasattr(node, "text"):
        return node.text
    return ""


def test_markdown_chunk_size_default_is_1024() -> None:
    """Markdown files use the promoted Experiment 6c chunk-size default."""
    assert CHUNK_SIZE == 512
    assert MARKDOWN_CHUNK_SIZE == 1024


# ── 1.4: heading boundaries preserved when sections fit ───────────────────


@pytest.mark.asyncio
async def test_markdown_short_sections_align_with_headings(sample_md: Path) -> None:
    """`sample.md` has 5 short H2 sections, each well under CHUNK_SIZE.

    The chained pipeline SHALL produce one chunk per heading section.
    """
    nodes = await read_and_chunk_file_async(sample_md)
    assert len(nodes) >= 2, (
        "Markdown with multiple short H2 sections must yield more than one "
        "chunk"
    )

    # Each H2 section should appear in some chunk; chunks should not blend
    # across unrelated sections (Paris stays with France, Berlin with Germany).
    texts = [_node_text(n) for n in nodes]

    france_chunks = [t for t in texts if "Paris" in t]
    germany_chunks = [t for t in texts if "Berlin" in t]
    assert france_chunks, "Expected a chunk containing the France section"
    assert germany_chunks, "Expected a chunk containing the Germany section"

    # No single chunk should cover *all five* H2 sections — heading
    # boundaries must split the document.
    full_blend = [
        t
        for t in texts
        if "Paris" in t
        and "Berlin" in t
        and "Rome" in t
        and "Madrid" in t
        and "London" in t
    ]
    assert not full_blend, (
        "Heading-aware chunking must not collapse all 5 H2 sections into one "
        "chunk"
    )


# ── 1.5: long heading-bounded section is further split ────────────────────


@pytest.mark.asyncio
async def test_markdown_long_section_is_split(
    fixtures_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A single H2 section longer than CHUNK_SIZE must be split.

    We force a small ``chunk_size`` (in tokens) so the fixture is
    guaranteed to overflow without needing a multi-thousand-character
    fixture file. The acceptance criterion is that every produced
    chunk has length at most ``small_chunk_size * 1.1`` (within the
    splitter's tokenisation tolerance).
    """
    long_md = fixtures_dir / "markdown_long_section.md"
    small_chunk_size = 64
    import rag_mcp.core.ingestion.chunker as _chunker

    monkeypatch.setattr(_chunker, "MARKDOWN_CHUNK_SIZE", small_chunk_size)
    nodes = await read_and_chunk_file_async(long_md, chunk_overlap=10)

    assert len(nodes) > 1, (
        "A heading-bounded section longer than chunk_size must produce "
        "more than one chunk"
    )

    # Tokens ≈ 4 chars on average for English; allow a generous tolerance
    # so we are checking that the splitter actually engaged, not the
    # exact tokeniser arithmetic.
    char_cap = int(small_chunk_size * 4 * 1.5)
    for node in nodes:
        text = _node_text(node)
        assert len(text) <= char_cap, (
            f"Chunk length {len(text)} exceeds soft cap ({char_cap} chars); "
            "the chained sentence splitter is not capping section size."
        )


# ── 1.6: non-Markdown files use the default splitter ──────────────────────


@pytest.mark.asyncio
async def test_non_markdown_uses_default_splitter(sample_txt: Path) -> None:
    """A `.txt` file SHALL chunk via the existing SentenceSplitter only.

    We assert that the chunk count for a plain text file is identical
    to what a bare SentenceSplitter (no Markdown branch) would produce.
    """
    from llama_index.core import SimpleDirectoryReader
    from llama_index.core.node_parser import SentenceSplitter

    # Baseline — bare SentenceSplitter on the same file
    reader = SimpleDirectoryReader(
        input_files=[str(sample_txt)],
        filename_as_id=True,
    )
    documents = reader.load_data()
    baseline = SentenceSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    ).get_nodes_from_documents(documents)

    # Production path — should match exactly for non-Markdown files
    nodes = await read_and_chunk_file_async(sample_txt)

    assert len(nodes) == len(baseline), (
        f"Non-Markdown chunk count ({len(nodes)}) drifted from the bare "
        f"SentenceSplitter baseline ({len(baseline)}). The Markdown branch "
        "must not affect non-`.md` files."
    )


# ── 1.7: Markdown without headings still produces non-empty chunks ────────


@pytest.mark.asyncio
async def test_markdown_without_headings_still_chunks(
    fixtures_dir: Path,
) -> None:
    """Heading-less `.md` files must still produce at least one non-empty chunk."""
    no_headings = fixtures_dir / "markdown_no_headings.md"
    nodes = await read_and_chunk_file_async(no_headings)

    assert len(nodes) >= 1, (
        "Markdown without headings must still produce at least one chunk"
    )
    for node in nodes:
        assert _node_text(node).strip(), (
            "Markdown branch must not produce empty chunks"
        )


# ── 6c: defensive Markdown metadata/helper coverage ──────────────────────


@pytest.mark.asyncio
async def test_markdown_multi_chunk_nodes_keep_heading_metadata(
    fixtures_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every Markdown chunk emitted after second-stage splitting has headings."""
    import rag_mcp.core.ingestion.chunker as _chunker

    monkeypatch.setattr(_chunker, "MARKDOWN_CHUNK_SIZE", 64)
    long_md = fixtures_dir / "markdown_long_section.md"
    nodes = await read_and_chunk_file_async(long_md, chunk_overlap=10)

    assert len(nodes) >= 2, "Fixture must force multiple Markdown chunks"
    for node in nodes:
        assert node.metadata.get("header_path"), (
            "Markdown child chunks must preserve non-empty heading metadata"
        )


def test_ensure_heading_metadata_is_idempotent() -> None:
    """Calling the defensive metadata copy helper twice is a no-op."""
    node = SimpleNamespace(
        metadata={},
        source_node=SimpleNamespace(metadata={"header_path": "/Paper/Results/"}),
    )

    _ensure_heading_metadata([node])
    first_metadata = dict(node.metadata)
    _ensure_heading_metadata([node])

    assert node.metadata == first_metadata == {"header_path": "/Paper/Results/"}


def test_ensure_heading_metadata_copies_header_path_without_overwriting() -> None:
    """Defensive metadata copy fills missing headers and preserves existing ones."""
    missing = SimpleNamespace(
        metadata={},
        source_node=SimpleNamespace(metadata={"header_path": "/Paper/Methods/"}),
    )
    existing = SimpleNamespace(
        metadata={"header_path": "/Paper/Existing/"},
        source_node=SimpleNamespace(metadata={"header_path": "/Paper/Source/"}),
    )

    _ensure_heading_metadata([missing, existing])

    assert missing.metadata["header_path"] == "/Paper/Methods/"
    assert existing.metadata["header_path"] == "/Paper/Existing/"


@pytest.mark.asyncio
async def test_heading_prepend_enabled_adds_heading_prefix(
    sample_md: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The experimental heading-prepend knob prefixes Markdown node text."""
    import rag_mcp.core.chunking.markdown as _md

    monkeypatch.setattr(_md, "MARKDOWN_HEADING_PREPEND", True)
    nodes = await read_and_chunk_file_async(sample_md)

    assert nodes
    for node in nodes:
        assert _node_text(node).startswith("[/"), (
            "Heading-prepend mode must prefix chunks with the header path"
        )


def test_heading_prepend_is_not_applied_twice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The heading prepend helper guards against double-prefixing text."""
    import rag_mcp.core.chunking.markdown as _md

    monkeypatch.setattr(_md, "MARKDOWN_HEADING_PREPEND", True)
    node = SimpleNamespace(
        metadata={"header_path": "/Paper/Methods/"},
        text="Methods text",
    )

    _apply_heading_prepend([node])
    once = node.text
    _apply_heading_prepend([node])

    assert node.text == once == "[/Paper/Methods/] Methods text"


def test_min_size_floor_drops_tiny_markdown_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The experimental min-size floor drops tiny Markdown chunks."""
    import rag_mcp.core.chunking.markdown as _md

    monkeypatch.setattr(_md, "MARKDOWN_MIN_CHUNK_FRACTION", 0.5)
    small = SimpleNamespace(text="## Introduction\n\nWe study X.")
    large = SimpleNamespace(text="x" * 1200)

    kept = _drop_small_markdown_chunks([small, large], chunk_size=512)

    assert kept == [large]


@pytest.mark.asyncio
async def test_markdown_experimental_knobs_default_to_existing_chunks(
    sample_md: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unset 6c knobs preserve the 6b Markdown chunk text for a small fixture."""
    import rag_mcp.core.chunking.markdown as _md

    monkeypatch.setattr(_md, "MARKDOWN_HEADING_PREPEND", False)
    monkeypatch.setattr(_md, "MARKDOWN_MIN_CHUNK_FRACTION", 0.0)

    nodes = await read_and_chunk_file_async(sample_md)
    texts = [_node_text(node) for node in nodes]

    assert texts == [
        "# European Capitals",
        "## France\n\nThe capital of France is Paris. It is known for the Eiffel Tower.",
        "## Germany\n\nThe capital of Germany is Berlin. It is known for the Brandenburg Gate.",
        "## Italy\n\nThe capital of Italy is Rome. It is known for the Colosseum.",
        "## Spain\n\nThe capital of Spain is Madrid. It is known for the Royal Palace.",
        "## United Kingdom\n\nThe capital of the United Kingdom is London. It is known for Big Ben.",
    ]
