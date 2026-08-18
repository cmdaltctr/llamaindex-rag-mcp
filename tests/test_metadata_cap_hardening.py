"""Deterministic Stage 1 test for the LlamaIndex metadata chunk budget."""

from __future__ import annotations

import pytest

from rag_mcp.core.settings import ChunkingBlock, EffectiveSettings, MetadataBlock


@pytest.mark.asyncio
async def test_llamaindex_extractors_receive_exact_max_chunk_budget(monkeypatch) -> None:
    """Only split nodes inside the configured budget reach expensive extractors."""
    from llama_index.core import extractors as extractor_module
    from llama_index.core import ingestion as ingestion_module

    from rag_mcp.core.metadata.llamaindex import _extract_llamaindex_async
    from rag_mcp.core.providers.llm import registry as llm_registry

    monkeypatch.setenv("LLAMANDEX_EXTRACTOR_MAX_CHUNKS", "3")
    monkeypatch.setattr(llm_registry, "get", lambda _name: lambda *_a, **_kw: object())

    # The fake pipeline ignores extractor objects; patch constructors so no
    # external LLM/model validation occurs in this unit test.
    monkeypatch.setattr(extractor_module, "TitleExtractor", lambda **kwargs: object())
    monkeypatch.setattr(extractor_module, "KeywordExtractor", lambda **kwargs: object())
    monkeypatch.setattr(extractor_module, "SummaryExtractor", lambda **kwargs: object())

    seen_counts: list[int] = []

    class FakePipeline:
        def __init__(self, *, transformations) -> None:
            self.transformations = transformations

        async def arun(self, *, nodes):
            seen_counts.append(len(nodes))
            nodes[0].metadata.update(
                {
                    "excerpt_keywords": "ai, retrieval",
                    "section_summary": "Synthetic summary",
                    "document_title": "AI Retrieval",
                }
            )
            return nodes

    monkeypatch.setattr(ingestion_module, "IngestionPipeline", FakePipeline)

    settings = EffectiveSettings(
        chunking=ChunkingBlock(chunk_size=32, chunk_overlap=0),
        metadata=MetadataBlock(extraction_mode="llamaindex"),
        metadata_llm_provider="local",
        local_backend="ollama",
    )
    text = " ".join(
        f"Sentence number {i} contains enough words to create several chunks." for i in range(80)
    )

    result = await _extract_llamaindex_async(text, "synthetic.txt", settings)

    assert seen_counts == [3]
    assert result["category"] == "ai"
    assert result["summary"] == "Synthetic summary"
