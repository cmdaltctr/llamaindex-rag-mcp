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

from rag_mcp.config import get_settings as _gs
from rag_mcp.core.chunking.markdown import (
    apply_heading_prepend as _apply_heading_prepend,
)
from rag_mcp.core.chunking.markdown import (
    drop_small_markdown_chunks as _drop_small_markdown_chunks,
)
from rag_mcp.core.chunking.markdown import (
    ensure_heading_metadata as _ensure_heading_metadata,
)
from rag_mcp.core.ingestion import read_and_chunk_file_async
from rag_mcp.core.settings import ChunkingBlock, EffectiveSettings

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
    assert _gs().chunking.chunk_size == 512
    assert _gs().chunking.markdown_chunk_size == 1024


# ── 1.4: heading boundaries preserved when sections fit ───────────────────


@pytest.mark.asyncio
async def test_markdown_short_sections_align_with_headings(sample_md: Path) -> None:
    """`sample.md` has 5 short H2 sections, each well under CHUNK_SIZE.

    The chained pipeline SHALL produce one chunk per heading section.
    """
    nodes = await read_and_chunk_file_async(sample_md)
    assert len(nodes) >= 2, (
        "Markdown with multiple short H2 sections must yield more than one chunk"
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
        if "Paris" in t and "Berlin" in t and "Rome" in t and "Madrid" in t and "London" in t
    ]
    assert not full_blend, (
        "Heading-aware chunking must not collapse all 5 H2 sections into one chunk"
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
    nodes = await read_and_chunk_file_async(
        long_md,
        chunk_overlap=10,
        settings=EffectiveSettings(chunking=ChunkingBlock(markdown_chunk_size=small_chunk_size)),
    )

    assert len(nodes) > 1, (
        "A heading-bounded section longer than chunk_size must produce more than one chunk"
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

    Task 5.4 strengthens the pin from chunk count to byte-for-byte
    content: the Markdown branch must not affect non-Markdown files.
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
        chunk_size=_gs().chunking.chunk_size,
        chunk_overlap=_gs().chunking.chunk_overlap,
    ).get_nodes_from_documents(documents)

    # Production path — should match exactly for non-Markdown files
    nodes = await read_and_chunk_file_async(sample_txt)

    assert len(nodes) == len(baseline), (
        f"Non-Markdown chunk count ({len(nodes)}) drifted from the bare "
        f"SentenceSplitter baseline ({len(baseline)}). The Markdown branch "
        "must not affect non-`.md` files."
    )
    assert [_node_text(n) for n in nodes] == [_node_text(b) for b in baseline], (
        "Non-Markdown chunk content drifted from the bare SentenceSplitter "
        "baseline; the reader-format routing must leave plain files untouched"
    )


@pytest.mark.asyncio
async def test_plain_reader_pdf_chunks_are_byte_for_byte_unchanged(
    fixtures_dir: Path,
    effective_settings,
) -> None:
    """Task 5.4 — a `.pdf` read by a plain-declaring reader is unchanged.

    Guards the narrowed "Non-Markdown files are unchanged" scenario: a
    plain-reader `.pdf` keeps the default splitter behaviour, matching a
    bare SentenceSplitter over the same documents byte-for-byte.
    """
    from llama_index.core import SimpleDirectoryReader
    from llama_index.core.node_parser import SentenceSplitter

    from rag_mcp.integrations.pdf import get_pdf_reader

    pdf = fixtures_dir / "smoke_text.pdf"
    settings = effective_settings(pdf_reader="pypdf", extraction_mode="disabled")

    reader = SimpleDirectoryReader(
        input_files=[str(pdf)],
        filename_as_id=True,
        file_extractor={".pdf": get_pdf_reader(settings.pdf_reader)},
    )
    documents = reader.load_data()
    baseline = SentenceSplitter(
        chunk_size=settings.chunking.chunk_size,
        chunk_overlap=settings.chunking.chunk_overlap,
    ).get_nodes_from_documents(documents)

    nodes = await read_and_chunk_file_async(pdf, settings=settings)

    assert nodes, "a plain-reader PDF must still produce chunks"
    assert len(nodes) == len(baseline)
    assert [_node_text(n) for n in nodes] == [_node_text(b) for b in baseline]


# ── 1.3: reader-declared Markdown routes the heading-aware path ────────


@pytest.mark.asyncio
async def test_markdown_declaring_pdf_reader_produces_header_path(
    fixtures_dir: Path,
    effective_settings,
) -> None:
    """A `.pdf` read by a markdown-declaring reader yields heading-aware chunks.

    Task 1.3 (red-first, fix-embedding-and-structure-fidelity-1): the
    chunker routes on the reader's declared text format, not on the
    `.md` suffix alone, so `pdf_inspector` output keeps its heading
    structure and every chunk carries `header_path`.
    """
    settings = effective_settings(
        pdf_reader="pdf_inspector",
        extraction_mode="disabled",
    )
    nodes = await read_and_chunk_file_async(
        fixtures_dir / "pdf_markdown_syntax.pdf", settings=settings
    )

    assert nodes, "a markdown-declaring reader must still produce chunks"
    for node in nodes:
        assert node.metadata.get("header_path"), (
            "Reader-produced Markdown must carry header_path after heading-aware chunking"
        )


@pytest.mark.asyncio
async def test_reader_produced_markdown_honours_the_markdown_budget(
    fixtures_dir: Path,
    effective_settings,
) -> None:
    """Task 5.2 — CHUNKING__MARKDOWN_CHUNK_SIZE caps reader-produced Markdown.

    Same acceptance as the `.md` path (``test_markdown_long_section_is_split``):
    the budget applies identically on the reader-produced path.
    """
    settings = effective_settings(
        pdf_reader="pdf_inspector",
        extraction_mode="disabled",
        markdown_chunk_size=128,
    )
    nodes = await read_and_chunk_file_async(
        fixtures_dir / "pdf_markdown_syntax.pdf",
        chunk_overlap=10,
        settings=settings,
    )

    assert len(nodes) > 1, "the markdown budget must split reader-produced sections"
    # Tokens ≈ 4 chars on average for English; a generous tolerance so
    # this checks that the splitter engaged, not tokeniser arithmetic.
    char_cap = int(128 * 4 * 1.5)
    for node in nodes:
        assert len(_node_text(node)) <= char_cap, (
            f"Chunk length {len(_node_text(node))} exceeds the soft cap "
            f"({char_cap} chars); the markdown budget is not applied to "
            "reader-produced Markdown"
        )


@pytest.mark.asyncio
async def test_reader_produced_markdown_honours_heading_prepend(
    fixtures_dir: Path,
    effective_settings,
) -> None:
    """Task 5.2 — apply_heading_prepend applies on the reader-produced path.

    Spec scenario "Reader-produced Markdown honours the recovery knobs":
    the three post-processing hooks apply with the same configured
    behaviour they have for `.md` files. ``ensure_heading_metadata`` is
    covered by the header_path assertions in the 1.3 test above.
    """
    settings = effective_settings(
        pdf_reader="pdf_inspector",
        extraction_mode="disabled",
        markdown_heading_prepend=True,
    )
    nodes = await read_and_chunk_file_async(
        fixtures_dir / "pdf_markdown_syntax.pdf", settings=settings
    )

    assert nodes
    for node in nodes:
        assert _node_text(node).startswith("[/"), (
            "Heading-prepend mode must prefix reader-produced chunks with "
            "the header path, exactly as for `.md` files"
        )


# ── 1.7: Markdown without headings still produces non-empty chunks ────────


@pytest.mark.asyncio
async def test_markdown_without_headings_still_chunks(
    fixtures_dir: Path,
) -> None:
    """Heading-less `.md` files must still produce at least one non-empty chunk."""
    no_headings = fixtures_dir / "markdown_no_headings.md"
    nodes = await read_and_chunk_file_async(no_headings)

    assert len(nodes) >= 1, "Markdown without headings must still produce at least one chunk"
    for node in nodes:
        assert _node_text(node).strip(), "Markdown branch must not produce empty chunks"


# ── 6c: defensive Markdown metadata/helper coverage ──────────────────────


@pytest.mark.asyncio
async def test_markdown_multi_chunk_nodes_keep_heading_metadata(
    fixtures_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every Markdown chunk emitted after second-stage splitting has headings."""
    long_md = fixtures_dir / "markdown_long_section.md"
    nodes = await read_and_chunk_file_async(
        long_md,
        chunk_overlap=10,
        settings=EffectiveSettings(chunking=ChunkingBlock(markdown_chunk_size=64)),
    )

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
    nodes = await read_and_chunk_file_async(
        sample_md,
        settings=EffectiveSettings(chunking=ChunkingBlock(markdown_heading_prepend=True)),
    )

    assert nodes
    for node in nodes:
        assert _node_text(node).startswith("[/"), (
            "Heading-prepend mode must prefix chunks with the header path"
        )


def test_heading_prepend_is_not_applied_twice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The heading prepend helper guards against double-prefixing text."""

    node = SimpleNamespace(
        metadata={"header_path": "/Paper/Methods/"},
        text="Methods text",
    )

    _apply_heading_prepend([node], heading_prepend=True)
    once = node.text
    _apply_heading_prepend([node], heading_prepend=True)

    assert node.text == once == "[/Paper/Methods/] Methods text"


def test_min_size_floor_drops_tiny_markdown_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The experimental min-size floor drops tiny Markdown chunks."""

    small = SimpleNamespace(text="## Introduction\n\nWe study X.")
    large = SimpleNamespace(text="x" * 1200)

    kept = _drop_small_markdown_chunks([small, large], chunk_size=512, min_chunk_fraction=0.5)

    assert kept == [large]


@pytest.mark.asyncio
async def test_markdown_experimental_knobs_default_to_existing_chunks(
    sample_md: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unset 6c knobs preserve the 6b Markdown chunk text for a small fixture."""

    nodes = await read_and_chunk_file_async(sample_md)
    texts = [_node_text(node) for node in nodes]

    assert texts == [
        "# European Capitals",
        "## France\n\nThe capital of France is Paris. It is known for the Eiffel Tower.",
        "## Germany\n\nThe capital of Germany is Berlin. It is known for the Brandenburg Gate.",
        "## Italy\n\nThe capital of Italy is Rome. It is known for the Colosseum.",
        "## Spain\n\nThe capital of Spain is Madrid. It is known for the Royal Palace.",
        "## United Kingdom\n\nThe capital of the United Kingdom is London. It is known for Big Ben.",  # noqa: E501
    ]
