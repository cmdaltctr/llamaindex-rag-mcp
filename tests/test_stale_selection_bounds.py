"""Red-first coverage for source-scoped stale-row selection.

Stage 1 of the OpenSpec change
``fix-retrieval-freshness-and-context-assembly-2`` (task 1.4).

``_stale_source_ids`` (``core/ingestion/replacement.py``) iterates every
row in the collection, in Python, for each replaced source — inside the
global write lock. This test pins the post-fix behaviour (stage 6): the
row reads performed to select stale rows must be proportional to the
replaced source's own row count, not the collection total. It was
written red against the unfiltered ``iter_documents`` seam; design D6
routes selection through the store-neutral filtered read
(``iter_filtered_documents``, task 2.7), so the spy watches that seam
and additionally proves the unfiltered scan is no longer used at all.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from omrg.core.ingestion import ingest_path_async

# Enough sentences per file that each source spans several chunks, so the
# collection total is a clear multiple of one source's rows.
_SENTENCES_PER_FILE = 200
_SOURCE_COUNT = 6


def _file_text(file_index: int, *, revised: bool = False) -> str:
    """Return unique per-file content so every source has its own rows."""
    marker = "revised" if revised else "initial"
    return " ".join(
        f"File {file_index} {marker} sentence {sentence:03d} "
        f"carries unique token f{file_index}{'r' if revised else 'i'}s{sentence:03d}."
        for sentence in range(_SENTENCES_PER_FILE)
    )


@pytest.fixture
def many_source_collection(tmp_path: Path) -> list[Path]:
    """Ingest several multi-chunk sources and return their paths."""
    files: list[Path] = []
    for index in range(_SOURCE_COUNT):
        doc = tmp_path / f"source_{index:02d}.txt"
        doc.write_text(_file_text(index))
        files.append(doc)
    return files


async def test_stale_selection_reads_rows_proportional_to_the_replaced_source(
    many_source_collection: list[Path],
    monkeypatch,
) -> None:
    """Replacing one source must not read the whole collection.

    GIVEN a collection holding several multi-chunk sources
    WHEN one source is replaced with new content
    THEN the number of rows read through ``iter_filtered_documents`` to
    select stale rows is proportional to that source's row count
    AND the unfiltered ``iter_documents`` scan is not used at all.
    """
    from omrg.core.vectordb import get_default_store

    store = get_default_store()
    per_source_rows: list[int] = []
    for doc in many_source_collection:
        result = await ingest_path_async(str(doc))
        assert result["status"] == "ok", result.get("warnings")
        per_source_rows.append(result["chunks_created"])

    target_rows = per_source_rows[0]
    total_rows = store.count("documents")
    assert total_rows >= 4 * target_rows, (
        f"precondition failed: collection total {total_rows} is not a clear "
        f"multiple of the replaced source's {target_rows} rows."
    )

    # Rewrite the target source so its content hash, source version and
    # attempt all change and the replacement path runs end to end.
    target_file = many_source_collection[0]
    target_file.write_text(_file_text(0, revised=True))

    reads = {"rows": 0, "unfiltered_rows": 0}
    original_filtered = store.iter_filtered_documents
    original_iter_documents = store.iter_documents

    def _counting_iter_documents(collection_name, page_size=None):
        for row in original_iter_documents(collection_name, page_size):
            reads["unfiltered_rows"] += 1
            yield row

    def _counting_filtered(collection_name, where, page_size=None):
        for row in original_filtered(collection_name, where, page_size):
            reads["rows"] += 1
            yield row

    monkeypatch.setattr(store, "iter_documents", _counting_iter_documents)
    monkeypatch.setattr(store, "iter_filtered_documents", _counting_filtered)

    result = await ingest_path_async(str(target_file))

    assert result["status"] == "ok", result.get("warnings")
    assert result["chunks_removed"] == target_rows, (
        f"precondition failed: expected the previous attempt's {target_rows} "
        f"rows to be removed, got {result['chunks_removed']}."
    )
    assert reads["rows"] > 0, "precondition failed: no rows were read at all"
    assert reads["unfiltered_rows"] == 0, (
        "stale selection must not use the unfiltered iter_documents scan; "
        f"it read {reads['unfiltered_rows']} row(s) of the collection."
    )

    # Bound: the filtered read may see the source's old-attempt rows plus
    # its new-attempt rows, with headroom, but never a scan of the whole
    # collection.
    assert reads["rows"] <= 3 * target_rows, (
        f"stale selection read {reads['rows']} rows to replace one source of "
        f"{target_rows} rows in a {total_rows}-row collection; selection must "
        "be scoped to the source, not scan the collection."
    )
