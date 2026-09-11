"""Markdown chunking through the ingestion pipeline.

OpenSpec: improve-rag-input-quality-5. These regressions cover two pipeline
concerns for the Markdown chunking path: the tokenizer identity, its revision,
and the resolved splitter stay inside the failure-safe replacement path, so a
degraded run is never mistaken for an up-to-date one; and a source the splitter
cannot fit fails on its own without stopping the rest of the batch.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from omrg.core.ingestion import ingest_path_async
from omrg.core.settings import EffectiveSettings, EmbeddingBlock, MetadataBlock
from omrg.core.vectordb import get_default_store, set_default_store
from omrg.core.vectordb.lancedb import LanceVectorStore

_COLLECTION = "markdown_chunking_pipeline"


@pytest.fixture(params=["chroma", "lancedb"])
def identity_store(request: pytest.FixtureRequest, tmp_path: Path):
    """Install one real store implementation behind the process default."""
    if request.param == "chroma":
        return get_default_store()
    store = LanceVectorStore(uri=str(tmp_path / "lancedb"))
    set_default_store(store)
    return store


def _stored_identities(store, source: Path) -> list[str]:
    """Return the stored index identity of every row for one source."""
    from omrg.core.ingestion.source_state import SOURCE_INDEX_IDENTITY_KEY

    return [
        metadata[SOURCE_INDEX_IDENTITY_KEY]
        for _, _, metadata in store.iter_documents(_COLLECTION)
        if metadata.get("file_path") == str(source)
    ]


def _settings(*, tokenizer_model: str, tokenizer_revision: str) -> EffectiveSettings:
    """Build settings that differ only in the configured tokenizer identity."""
    return EffectiveSettings(
        metadata=MetadataBlock(extraction_mode="disabled"),
        embedding=EmbeddingBlock(
            tokenizer_model=tokenizer_model,
            tokenizer_revision=tokenizer_revision,
        ),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("first_settings", "second_settings"),
    [
        (
            _settings(tokenizer_model="test/model-a", tokenizer_revision="rev-1"),
            _settings(tokenizer_model="test/model-b", tokenizer_revision="rev-1"),
        ),
        (
            _settings(tokenizer_model="test/model-a", tokenizer_revision="rev-1"),
            _settings(tokenizer_model="test/model-a", tokenizer_revision="rev-2"),
        ),
    ],
    ids=["tokenizer-model-change", "tokenizer-revision-change"],
)
async def test_tokenizer_identity_change_forces_replacement(
    tmp_path: Path,
    identity_store,
    first_settings: EffectiveSettings,
    second_settings: EffectiveSettings,
) -> None:
    """A changed tokenizer model or revision replaces the stored chunks."""
    source = tmp_path / "tokenizer-identity.md"
    source.write_text("# Identity\n\n" + "token-aware content " * 60, encoding="utf-8")

    first = await ingest_path_async(
        str(source),
        collection_name=_COLLECTION,
        effective_settings=first_settings,
    )
    first_identities = _stored_identities(identity_store, source)
    second = await ingest_path_async(
        str(source),
        collection_name=_COLLECTION,
        effective_settings=second_settings,
    )
    second_identities = _stored_identities(identity_store, source)

    assert first["status"] == "ok"
    assert second["status"] == "ok"
    assert second["files_indexed"] == 1
    assert second["files_skipped_unchanged"] == 0
    assert second["chunks_removed"] == first["chunks_created"]
    assert first_identities and second_identities
    assert first_identities[0] != second_identities[0]


@pytest.mark.asyncio
async def test_degraded_markdown_chunking_recovers_when_tokenizer_resolves(
    tmp_path: Path,
    identity_store,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A legacy-indexed Markdown source is replaced after tokenizer resolution."""
    from tokenizers import Tokenizer, models, pre_tokenizers

    from omrg.core.chunking.model_token import MarkdownChunkingResolution
    from omrg.core.ingestion import pipeline

    source = tmp_path / "chunking-recovery.md"
    source.write_text("# Recovery\n\n" + "token-aware content " * 80, encoding="utf-8")
    identity = {"model": "test/model", "revision": "test-revision"}
    legacy = MarkdownChunkingResolution(None, identity, "legacy_fallback")
    marker = "[UNK]"
    tokenizer = Tokenizer(models.WordLevel({marker: 0}, unk_token=marker))
    tokenizer.pre_tokenizer = pre_tokenizers.Whitespace()
    resolved = MarkdownChunkingResolution(tokenizer, identity, "model_token_aware")
    monkeypatch.setattr(pipeline, "resolve_markdown_chunking", lambda _settings: legacy)

    first = await ingest_path_async(str(source), collection_name=_COLLECTION)
    first_identities = _stored_identities(identity_store, source)

    monkeypatch.setattr(pipeline, "resolve_markdown_chunking", lambda _settings: resolved)
    second = await ingest_path_async(str(source), collection_name=_COLLECTION)
    second_identities = _stored_identities(identity_store, source)

    assert first["status"] == "ok"
    assert second["status"] == "ok"
    assert second["files_indexed"] == 1
    assert second["files_skipped_unchanged"] == 0
    assert first_identities and second_identities
    assert first_identities[0] != second_identities[0]


@pytest.mark.asyncio
async def test_unfittable_markdown_fails_that_source_alone(
    tmp_path: Path,
    identity_store,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A chunk that will not fit the cap fails per file; the batch continues.

    The oversized escape it replaces used to emit the chunk anyway, so the
    source silently violated the token contract instead of being reported.
    """
    from tokenizers import Tokenizer, models, pre_tokenizers

    from omrg.core.chunking.model_token import MarkdownChunkingResolution
    from omrg.core.ingestion import pipeline
    from omrg.core.settings import ChunkingBlock

    marker = "[UNK]"
    tokenizer = Tokenizer(models.WordLevel({marker: 0}, unk_token=marker))
    tokenizer.pre_tokenizer = pre_tokenizers.Whitespace()
    resolution = MarkdownChunkingResolution(
        tokenizer,
        {"model": "test/model", "revision": "test-revision"},
        "model_token_aware",
    )
    monkeypatch.setattr(pipeline, "resolve_markdown_chunking", lambda _settings: resolution)

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "good.md").write_text("# Good\n\n" + "usable content " * 40, encoding="utf-8")
    # A heading path longer than the whole token budget leaves no room for text.
    (corpus / "unfittable.md").write_text(
        "# Alpha bravo charlie delta echo foxtrot golf hotel india juliet\n\n" + "evidence " * 60,
        encoding="utf-8",
    )
    settings = EffectiveSettings(
        metadata=MetadataBlock(extraction_mode="disabled"),
        chunking=ChunkingBlock(
            markdown_chunk_size=12,
            chunk_overlap=0,
            markdown_heading_prepend=True,
        ),
    )

    result = await ingest_path_async(
        str(corpus),
        collection_name=_COLLECTION,
        effective_settings=settings,
    )

    assert result["status"] == "ok"
    assert result["files_indexed"] == 1
    details = {detail["file"]: detail for detail in result["file_details"]}
    assert details["good.md"]["status"] == "indexed"
    assert details["unfittable.md"]["status"] == "failed"
    assert "CHUNKING__MARKDOWN_CHUNK_SIZE" in details["unfittable.md"]["error"]
