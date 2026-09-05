"""Red-first coverage for overlap removal between adjacent chunks.

Stage 1 of the OpenSpec change
``fix-retrieval-freshness-and-context-assembly-2`` (task 1.2).

``search()`` currently has no context-assembly stage: with the default
``chunking.chunk_overlap=100``, a query that returns two adjacent chunks
returns the splitter-produced overlap text twice. This test pins the
post-fix behaviour (stage 5) and is EXPECTED TO FAIL until the assembly
stage lands.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from omrg.core.ingestion import ingest_path_async
from omrg.core.retrieval import search

# Sentences are long and individually unique so the only legitimate
# source of a repeated sentence across chunks is the splitter's overlap.
_SENTENCE_TEMPLATE = (
    "Sentence number {index:03d} discusses topic {index:03d} carrying "
    "unique token tok{index:03d} for tracing."
)
_SENTENCE_COUNT = 40
_MIN_SENTENCE_CHARS = 20


def _normalised_sentences(text: str) -> list[str]:
    """Return whitespace-normalised sentences of usable length from one chunk."""
    return [
        sentence
        for sentence in (
            " ".join(part.split()) for part in re.split(r"(?<=[.!?])\s+", text.strip())
        )
        if len(sentence) >= _MIN_SENTENCE_CHARS
    ]


@pytest.fixture
def overlap_document(tmp_path: Path) -> Path:
    """Write one plain-text document whose chunks overlap heavily."""
    doc = tmp_path / "overlap_doc.txt"
    doc.write_text(" ".join(_SENTENCE_TEMPLATE.format(index=i) for i in range(_SENTENCE_COUNT)))
    return doc


async def test_adjacent_overlap_chunks_do_not_repeat_sentences(
    overlap_document: Path,
    effective_settings,
) -> None:
    """One search must not return the overlap text of adjacent chunks twice.

    GIVEN a document ingested with ``chunking.chunk_overlap=100``
    AND a query whose result set contains adjacent chunks of one source
    WHEN search returns
    THEN no sentence of the source appears twice across the returned texts.
    """
    settings = effective_settings(
        chunk_size=128,
        chunk_overlap=100,
        extraction_mode="disabled",
    )
    ingest = await ingest_path_async(
        str(overlap_document),
        effective_settings=settings,
    )
    assert ingest["status"] == "ok", ingest.get("warnings")
    assert ingest["chunks_created"] >= 2, "precondition: the document must produce multiple chunks"

    results = search("sentence topic", top_k=10, rerank=False, effective_settings=settings)

    # Precondition: the result set really does contain adjacent chunks
    # from the same source version, so the assertion below cannot pass
    # vacuously. Assembly (stage 5) merges adjacent chunks into one row,
    # so adjacency is now observable either as two rows with consecutive
    # indices or as one merged row carrying several constituent
    # ``chunk_ids`` (its ``source_chunk_index`` reports the lowest only).
    flat = sorted(
        row["source_chunk_index"] for row in results if row.get("source_chunk_index") is not None
    )
    adjacent_rows = any(second - first == 1 for first, second in zip(flat, flat[1:], strict=False))
    merged_counts = [len(row.get("chunk_ids", [])) for row in results]
    assert adjacent_rows or any(count > 1 for count in merged_counts), (
        f"precondition failed: no adjacent chunk pair in {flat}; "
        f"merged constituent counts {merged_counts}"
    )

    occurrences: dict[str, int] = {}
    for row in results:
        for sentence in _normalised_sentences(row["text"]):
            occurrences[sentence] = occurrences.get(sentence, 0) + 1

    duplicated = {sentence: count for sentence, count in occurrences.items() if count > 1}
    assert not duplicated, (
        f"{len(duplicated)} of {len(occurrences)} sentences appear more than "
        "once across the returned chunks; the overlap text must be merged "
        "into one row, not returned twice. First duplicates: "
        f"{sorted(duplicated)[:3]}"
    )
