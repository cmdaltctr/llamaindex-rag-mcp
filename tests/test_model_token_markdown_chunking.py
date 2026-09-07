"""Stage 3 model-token-aware Markdown chunking tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from llama_index.core import Document

from omrg.core.chunking.sentence import chunk_sentence_file_async
from omrg.core.settings import ChunkingBlock, EffectiveSettings, EmbeddingBlock, MetadataBlock

_MODEL = "Qwen/Qwen3-Embedding-4B"


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


@pytest.mark.asyncio
async def test_model_token_path_keeps_fitting_table_and_caps_oversized_section() -> None:
    """Fitting Markdown structures stay intact and long sections respect the cap."""
    settings, tokenizer = _qwen_settings(chunk_size=48)
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
async def test_model_token_path_derives_nested_header_paths_without_parent_nodes() -> None:
    """Every model-aware chunk receives ancestry from source Markdown offsets."""
    settings, _ = _qwen_settings(chunk_size=24)
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
async def test_heading_prepend_stays_within_finalised_token_cap() -> None:
    """The final chunk text, including its heading prefix, stays within the cap."""
    settings, tokenizer = _qwen_settings(chunk_size=40, heading_prepend=True)
    body = "content"
    while _token_count(tokenizer, "## Section\n\n" + body) < 40:
        candidate = body + " content"
        if _token_count(tokenizer, "## Section\n\n" + candidate) > 40:
            break
        body = candidate
    assert _token_count(tokenizer, "## Section\n\n" + body) == 40
    text = "# Root\n\n## Section\n\n" + body

    nodes = await chunk_sentence_file_async(
        [Document(text=text)], "doc.md", True, settings=settings
    )

    assert nodes
    assert all(node.text.startswith("[/Root/Section/] ") for node in nodes)
    assert all(_token_count(tokenizer, node.text) <= 40 for node in nodes)


@pytest.mark.asyncio
async def test_overlap_is_measured_in_tokenizer_units() -> None:
    """Adjacent model-aware chunks share the configured tokenizer overlap."""
    settings, tokenizer = _qwen_settings(chunk_size=48, chunk_overlap=6)
    text = "# Root\n\n" + " ".join("repeated evidence token" for _ in range(120))

    nodes = await chunk_sentence_file_async(
        [Document(text=text)], "doc.md", True, settings=settings
    )

    assert len(nodes) > 1
    assert all(_token_count(tokenizer, node.text) <= 48 for node in nodes)
    assert all(
        _token_overlap(tokenizer, left.text, right.text) >= 6
        for left, right in zip(nodes, nodes[1:], strict=True)
    )


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
