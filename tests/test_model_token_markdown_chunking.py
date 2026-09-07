"""Stage 3 model-token-aware Markdown chunking tests.

The structural regressions run on a deterministic in-memory tokenizer so they
never depend on a populated Hugging Face cache. One end-to-end check uses the
real Qwen tokenizer and skips when that artefact is not cached.
"""

from __future__ import annotations

from itertools import pairwise
from pathlib import Path

import pytest
from llama_index.core import Document

from omrg.core.chunking.sentence import chunk_sentence_file_async
from omrg.core.settings import ChunkingBlock, EffectiveSettings, EmbeddingBlock, MetadataBlock

_MODEL = "Qwen/Qwen3-Embedding-4B"
_STUB_MODEL = "test/word-level"
_STUB_REVISION = "test-revision"


def _stub_tokenizer():
    """Return a word-level tokenizer whose units are whitespace-ish words."""
    from tokenizers import Tokenizer, models, pre_tokenizers

    marker = "[UNK]"
    tokenizer = Tokenizer(models.WordLevel({marker: 0}, unk_token=marker))
    tokenizer.pre_tokenizer = pre_tokenizers.Whitespace()
    return tokenizer


def _stub_settings(
    monkeypatch: pytest.MonkeyPatch,
    *,
    chunk_size: int = 48,
    chunk_overlap: int = 0,
    heading_prepend: bool = False,
    min_chunk_fraction: float = 0.0,
):
    """Install the in-memory tokenizer and build settings that resolve to it."""
    from omrg.core.chunking import model_token

    tokenizer = _stub_tokenizer()
    monkeypatch.setattr(model_token, "load_tokenizer", lambda *_args: tokenizer)
    settings = EffectiveSettings(
        chunking=ChunkingBlock(
            markdown_chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            markdown_heading_prepend=heading_prepend,
            markdown_min_chunk_fraction=min_chunk_fraction,
        ),
        embedding=EmbeddingBlock(
            tokenizer_model=_STUB_MODEL,
            tokenizer_revision=_STUB_REVISION,
        ),
        metadata=MetadataBlock(extraction_mode="disabled"),
    )
    return settings, tokenizer


def _find_local_qwen_tokenizer() -> tuple[Path, str] | None:
    """Return a cached Qwen tokenizer and its snapshot revision."""
    cache = Path.home() / ".cache" / "huggingface" / "hub"
    candidates = sorted(cache.glob("models--Qwen--Qwen3-Embedding-4B/snapshots/*/tokenizer.json"))
    if not candidates:
        return None
    path = candidates[0]
    return path, path.parent.name


def _qwen_settings(
    *,
    chunk_size: int = 64,
    chunk_overlap: int = 0,
    heading_prepend: bool = False,
) -> tuple[EffectiveSettings, object]:
    """Build settings and the cached Qwen tokenizer for one test."""
    cached = _find_local_qwen_tokenizer()
    if cached is None:
        pytest.skip("no cached Qwen tokenizer.json; tokenizer tests do not download models")
    _, revision = cached
    from tokenizers import Tokenizer

    tokenizer = Tokenizer.from_file(str(cached[0]))
    settings = EffectiveSettings(
        chunking=ChunkingBlock(
            markdown_chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            markdown_heading_prepend=heading_prepend,
        ),
        embedding=EmbeddingBlock(tokenizer_model=_MODEL, tokenizer_revision=revision),
        metadata=MetadataBlock(extraction_mode="disabled"),
    )
    return settings, tokenizer


def _token_count(tokenizer: object, text: str) -> int:
    """Count tokens through a Hugging Face tokenizer."""
    return len(tokenizer.encode(text).ids)


def _token_overlap(tokenizer: object, left: str, right: str) -> int:
    """Return the largest suffix/prefix overlap in tokenizer units."""
    left_ids = tokenizer.encode(left).ids
    right_ids = tokenizer.encode(right).ids
    return max(
        (
            size
            for size in range(1, min(len(left_ids), len(right_ids)) + 1)
            if left_ids[-size:] == right_ids[:size]
        ),
        default=0,
    )


def _grow_to_exact_tokens(tokenizer: object, prelude: str, unit: str, target: int) -> str:
    """Return body text whose ``prelude + body`` is exactly *target* tokens."""
    body = unit
    while _token_count(tokenizer, prelude + body) < target:
        body = f"{body} {unit}"
    assert _token_count(tokenizer, prelude + body) == target
    return body


@pytest.mark.asyncio
async def test_model_token_path_keeps_fitting_table_and_caps_oversized_section(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fitting Markdown structures stay intact and long sections respect the cap."""
    settings, tokenizer = _stub_settings(monkeypatch, chunk_size=48)
    text = """# Report

## Table

| name | value |
| --- | --- |
| alpha | one |
| beta | two |

## Long section

""" + " ".join("identifier-heavy evidence" for _ in range(90))

    nodes = await chunk_sentence_file_async(
        [Document(text=text)], "doc.md", True, settings=settings
    )
    assert len(nodes) > 2
    table = next(node for node in nodes if "| alpha |" in node.text)
    assert "| beta |" in table.text
    assert _token_count(tokenizer, table.text) <= 48
    assert all(_token_count(tokenizer, node.text) <= 48 for node in nodes)


@pytest.mark.asyncio
async def test_model_token_path_derives_nested_header_paths_without_parent_nodes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every model-aware chunk receives ancestry from source Markdown offsets."""
    settings, _ = _stub_settings(monkeypatch, chunk_size=24)
    document = Document(
        text="# Root\n\n## Methods\n\n"
        + "method detail " * 35
        + "\n\n### Results\n\nresult detail " * 35
    )

    nodes = await chunk_sentence_file_async([document], "doc.md", True, settings=settings)

    assert nodes
    assert all(getattr(node, "source_node", None) is None for node in nodes)
    methods = [node for node in nodes if "method detail" in node.text]
    results = [node for node in nodes if "result detail" in node.text]
    assert methods and results
    assert all(node.metadata["header_path"] == "/Root/Methods/" for node in methods)
    assert all(node.metadata["header_path"] == "/Root/Methods/Results/" for node in results)


@pytest.mark.asyncio
async def test_heading_prepend_stays_within_finalised_token_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The final chunk text, including its heading prefix, stays within the cap."""
    settings, tokenizer = _stub_settings(monkeypatch, chunk_size=40, heading_prepend=True)
    body = _grow_to_exact_tokens(tokenizer, "## Section\n\n", "content", 40)
    text = "# Root\n\n## Section\n\n" + body

    nodes = await chunk_sentence_file_async(
        [Document(text=text)], "doc.md", True, settings=settings
    )

    body_nodes = [node for node in nodes if "content" in node.text]
    assert body_nodes
    assert all(node.text.startswith("[/Root/Section/] ") for node in body_nodes)
    assert all(_token_count(tokenizer, node.text) <= 40 for node in nodes)


@pytest.mark.asyncio
async def test_overlap_is_measured_in_tokenizer_units(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Adjacent model-aware chunks share the configured tokenizer overlap."""
    settings, tokenizer = _stub_settings(monkeypatch, chunk_size=48, chunk_overlap=6)
    text = "# Root\n\n" + " ".join("repeated evidence token" for _ in range(120))

    nodes = await chunk_sentence_file_async(
        [Document(text=text)], "doc.md", True, settings=settings
    )

    assert len(nodes) > 1
    assert all(_token_count(tokenizer, node.text) <= 48 for node in nodes)
    body = [node for node in nodes if "repeated evidence token" in node.text]
    assert len(body) > 1
    assert all(
        _token_overlap(tokenizer, left.text, right.text) >= 6 for left, right in pairwise(body)
    )


@pytest.mark.asyncio
async def test_heading_prepend_keeps_the_configured_overlap_within_the_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A reserved heading prefix never silently reduces the configured overlap."""
    settings, tokenizer = _stub_settings(
        monkeypatch,
        chunk_size=48,
        chunk_overlap=6,
        heading_prepend=True,
    )
    text = "# Root\n\n## Section\n\n" + " ".join("repeated evidence token" for _ in range(120))

    nodes = await chunk_sentence_file_async(
        [Document(text=text)], "doc.md", True, settings=settings
    )

    prefix = "[/Root/Section/] "
    body = [node for node in nodes if node.text.startswith(prefix) and "repeated" in node.text]
    assert len(body) > 1
    assert all(_token_count(tokenizer, node.text) <= 48 for node in body)
    assert all(
        _token_overlap(
            tokenizer,
            left.text.removeprefix(prefix),
            right.text.removeprefix(prefix),
        )
        >= 6
        for left, right in pairwise(body)
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("chunk_overlap", "headings"),
    [
        (4, "# Alpha bravo charlie\n\n## Delta echo foxtrot golf hotel india\n\n"),
        # A three-token prefix leaves a capacity of nine, which cannot hold a
        # requested overlap of nine.
        (9, "# Root\n\n"),
    ],
    ids=["prefix-exceeds-cap", "prefix-crowds-out-overlap"],
)
async def test_oversized_heading_prefix_fails_naming_the_settings(
    monkeypatch: pytest.MonkeyPatch,
    chunk_overlap: int,
    headings: str,
) -> None:
    """A heading prefix that crowds out the content budget raises, never overflows.

    The second case is the one that used to pass silently: the splitter clamped
    the requested overlap to the reduced capacity instead of reporting that the
    combination is unworkable.
    """
    settings, _ = _stub_settings(
        monkeypatch,
        chunk_size=12,
        chunk_overlap=chunk_overlap,
        heading_prepend=True,
    )
    text = headings + " ".join("evidence" for _ in range(60))

    with pytest.raises(ValueError) as error:
        await chunk_sentence_file_async([Document(text=text)], "doc.md", True, settings=settings)

    message = str(error.value)
    assert "CHUNKING__MARKDOWN_CHUNK_SIZE" in message
    assert "CHUNKING__CHUNK_OVERLAP" in message
    assert "CHUNKING__MARKDOWN_HEADING_PREPEND" in message


@pytest.mark.asyncio
@pytest.mark.parametrize("fence", ["```", "~~~"], ids=["backtick", "tilde"])
async def test_fenced_code_comments_do_not_become_headings(
    monkeypatch: pytest.MonkeyPatch,
    fence: str,
) -> None:
    """A ``#`` line inside a fenced code block never joins the heading chain."""
    settings, _ = _stub_settings(monkeypatch, chunk_size=32)
    language = "python" if fence == "```" else ""
    text = f"# Root\n\n{fence}{language}\n# Fake\nvalue = 1\n{fence}\n\nprose detail " * 20

    nodes = await chunk_sentence_file_async(
        [Document(text=text)], "doc.md", True, settings=settings
    )

    prose = [node for node in nodes if "prose detail" in node.text]
    assert prose
    assert all(node.metadata["header_path"] == "/Root/" for node in prose)


@pytest.mark.asyncio
async def test_skipped_heading_levels_produce_sibling_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two level-three headings under one level-one heading stay siblings."""
    settings, _ = _stub_settings(monkeypatch, chunk_size=32)
    text = (
        "# Root\n\n"
        "### First\n\n" + "first detail " * 20 + "\n\n"
        "### Second\n\n" + "second detail " * 20
    )

    nodes = await chunk_sentence_file_async(
        [Document(text=text)], "doc.md", True, settings=settings
    )

    first = [node for node in nodes if "first detail" in node.text]
    second = [node for node in nodes if "second detail" in node.text]
    assert first and second
    assert all(node.metadata["header_path"] == "/Root/First/" for node in first)
    assert all(node.metadata["header_path"] == "/Root/Second/" for node in second)


@pytest.mark.asyncio
async def test_small_chunk_filter_uses_exact_model_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The model-aware path filters small chunks by tokenizer units, not characters."""
    settings, tokenizer = _stub_settings(
        monkeypatch,
        chunk_size=24,
        min_chunk_fraction=0.5,
    )
    text = "# Root\n\n## Tiny\n\ntiny\n\n## Long\n\n" + " ".join(
        "substantial evidence" for _ in range(40)
    )

    nodes = await chunk_sentence_file_async(
        [Document(text=text)], "doc.md", True, settings=settings
    )

    assert nodes
    assert all(_token_count(tokenizer, node.text) >= 12 for node in nodes)
    assert not any(node.text.strip() == "tiny" for node in nodes)


class _UnsplittableSplitter:
    """A splitter that always returns its input, standing in for indivisible text."""

    @classmethod
    def from_huggingface_tokenizer(cls, tokenizer: object, capacity: int, *, overlap: int):
        """Ignore the capacity, exactly as an unsplittable structure would."""
        return cls()

    def chunk_indices(self, text: str) -> list[tuple[int, str]]:
        """Return the whole text as one oversized chunk."""
        return [(0, text)]


@pytest.mark.parametrize("heading_prepend", [False, True], ids=["plain", "prepend"])
def test_unreducible_chunk_raises_instead_of_exceeding_the_cap(
    monkeypatch: pytest.MonkeyPatch,
    heading_prepend: bool,
) -> None:
    """A chunk that will not fit is reported per file, never emitted oversized."""
    import semantic_text_splitter

    from omrg.core.chunking.model_token import (
        MODEL_AWARE_PATH,
        MarkdownChunkingResolution,
        split_markdown_documents,
    )

    tokenizer = _stub_tokenizer()
    monkeypatch.setattr(semantic_text_splitter, "MarkdownSplitter", _UnsplittableSplitter)
    resolution = MarkdownChunkingResolution(
        tokenizer,
        {"model": _STUB_MODEL, "revision": _STUB_REVISION},
        MODEL_AWARE_PATH,
    )
    document = Document(text="# Root\n\n" + " ".join("evidence" for _ in range(30)))

    with pytest.raises(ValueError) as error:
        split_markdown_documents(
            [document],
            chunk_size=8,
            chunk_overlap=0,
            resolution=resolution,
            heading_prepend=heading_prepend,
        )

    assert "CHUNKING__MARKDOWN_CHUNK_SIZE" in str(error.value)


@pytest.mark.asyncio
async def test_cached_qwen_tokenizer_caps_finalised_chunks() -> None:
    """End-to-end check against the real embedding tokenizer when it is cached."""
    settings, tokenizer = _qwen_settings(chunk_size=48, heading_prepend=True)
    text = "# Report\n\n## Findings\n\n" + " ".join("identifier-heavy evidence" for _ in range(90))

    nodes = await chunk_sentence_file_async(
        [Document(text=text)], "doc.md", True, settings=settings
    )

    assert nodes
    assert all(node.text.startswith("[/Report/Findings/] ") for node in nodes)
    assert all(_token_count(tokenizer, node.text) <= 48 for node in nodes)


def test_unresolvable_configured_tokenizer_uses_legacy_with_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An unavailable configured tokenizer must not claim exact chunking."""
    from omrg.core.chunking import model_token
    from omrg.integrations.tokenizer import TokenizerUnavailableError

    settings = EffectiveSettings(
        embedding=EmbeddingBlock(tokenizer_model=_MODEL, tokenizer_revision="missing"),
        metadata=MetadataBlock(extraction_mode="disabled"),
    )
    monkeypatch.setattr(
        model_token,
        "load_tokenizer",
        lambda *_args: (_ for _ in ()).throw(TokenizerUnavailableError("missing cache")),
    )

    with caplog.at_level("WARNING"):
        resolution = model_token.resolve_markdown_chunking(settings)

    assert resolution.resolved_splitter == "legacy_fallback"
    assert resolution.tokenizer is None
    assert "legacy" in caplog.text.lower()
    assert _MODEL in caplog.text
