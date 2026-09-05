"""Deterministic Stage 1 hardening tests for chunking behaviour."""

from __future__ import annotations

import pytest
from llama_index.core.schema import TextNode

from omrg.core.chunking.code import chunk_code_file_async
from omrg.core.settings import ChunkingBlock, EffectiveSettings, MetadataBlock


@pytest.mark.asyncio
async def test_code_splitter_reports_ast_success(tmp_path) -> None:
    path = tmp_path / "app.py"
    path.write_text("def alpha():\n    return 1\n", encoding="utf-8")

    result = await chunk_code_file_async(
        path,
        "python",
        512,
        50,
        "code/python",
    )

    assert result.chunk_strategy_requested == "code"
    assert result.chunk_strategy_effective == "code"
    assert result.fallback_reason is None
    assert result


@pytest.mark.asyncio
async def test_code_splitter_fallback_is_observable(tmp_path, monkeypatch) -> None:
    path = tmp_path / "app.py"
    path.write_text("x = 1\n", encoding="utf-8")

    import llama_index.core.node_parser as node_parser

    class BrokenCodeSplitter:
        def __init__(self, **kwargs) -> None:
            raise RuntimeError("synthetic AST failure")

    monkeypatch.setattr(node_parser, "CodeSplitter", BrokenCodeSplitter)

    result = await chunk_code_file_async(
        path,
        "python",
        512,
        50,
        "code/python",
    )

    assert result.chunk_strategy_requested == "code"
    assert result.chunk_strategy_effective == "sentence"
    assert "synthetic AST failure" in (result.fallback_reason or "")
    assert result


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("suffix", "language", "content", "first", "second", "max_chars"),
    [
        (
            ".py",
            "python",
            "def alpha():\n    return 1\n\ndef beta():\n    return 2\n",
            "def alpha",
            "def beta",
            32,
        ),
        (
            ".js",
            "javascript",
            "function alpha() { return 1; }\nfunction beta() { return 2; }\n",
            "function alpha",
            "function beta",
            36,
        ),
    ],
)
async def test_code_splitter_preserves_distinct_top_level_boundaries(
    tmp_path,
    suffix: str,
    language: str,
    content: str,
    first: str,
    second: str,
    max_chars: int,
) -> None:
    """A structural fixture must fail if the path silently sentence-falls back."""
    path = tmp_path / f"fixture{suffix}"
    path.write_text(content, encoding="utf-8")

    result = await chunk_code_file_async(
        path,
        language,
        1024,  # fallback would keep the tiny file effectively whole
        0,
        f"code/{language}",
        code_chunk_lines=40,
        code_chunk_lines_overlap=1,
        code_max_chars=max_chars,
    )

    assert result.chunk_strategy_effective == "code"
    texts = [node.text for node in result]
    assert len(texts) >= 2
    assert any(first in text and second not in text for text in texts)
    assert any(second in text and first not in text for text in texts)


@pytest.mark.asyncio
async def test_sentence_helper_honours_markdown_heading_prepend(monkeypatch) -> None:
    from omrg.core.chunking import sentence

    node = TextNode(text="Body text", metadata={"header_path": "Section"})
    monkeypatch.setattr(sentence, "_split_documents_sync", lambda *args: [node])
    settings = EffectiveSettings(chunking=ChunkingBlock(markdown_heading_prepend=True))

    result = await sentence.chunk_sentence_file_async(
        [],
        "doc.md",
        True,
        settings=settings,
    )

    assert result[0].text.startswith("[Section] ")


@pytest.mark.asyncio
async def test_sentence_helper_honours_markdown_min_fraction(monkeypatch) -> None:
    from omrg.core.chunking import sentence

    small = TextNode(text="tiny")
    large = TextNode(text="x" * 80)
    monkeypatch.setattr(sentence, "_split_documents_sync", lambda *args: [small, large])
    settings = EffectiveSettings(
        chunking=ChunkingBlock(
            markdown_chunk_size=100,
            markdown_min_chunk_fraction=0.1,
        )
    )

    result = await sentence.chunk_sentence_file_async(
        [],
        "doc.md",
        True,
        settings=settings,
    )

    assert result == [large]


@pytest.mark.asyncio
async def test_markdown_helper_matches_main_ingestion_postprocessing(tmp_path, monkeypatch) -> None:
    """Both entry points must apply the same Markdown post-processing knobs."""
    from llama_index.core import Document

    from omrg.core.chunking import sentence
    from omrg.core.ingestion.chunker import read_and_chunk_file_async

    def _fresh_nodes(*_args):
        return [
            TextNode(text="tiny", metadata={"header_path": "Section"}),
            TextNode(text="x" * 80, metadata={"header_path": "Section"}),
        ]

    monkeypatch.setattr(sentence, "_split_documents_sync", _fresh_nodes)

    path = tmp_path / "doc.md"
    path.write_text("# Section\n\nBody", encoding="utf-8")
    settings = EffectiveSettings(
        chunking=ChunkingBlock(
            markdown_chunk_size=100,
            markdown_heading_prepend=True,
            markdown_min_chunk_fraction=0.1,
        ),
        metadata=MetadataBlock(extraction_mode="disabled"),
    )

    helper = await sentence.chunk_sentence_file_async(
        [Document(text="ignored")],
        str(path),
        True,
        settings=settings,
    )
    main = await read_and_chunk_file_async(path, settings=settings)

    assert [node.text for node in helper] == [node.text for node in main]
