"""Regression tests for the experiment 25 accounting defects.

Covers the two contract points the standalone counter got wrong
(2026-09-08 external review):

1. Production file selection excludes the corpus manifest — only
   supported document extensions are gathered, so a ``.jsonl``
   bookkeeping file is never chunked or counted.
2. The embedding payload is body text plus RETAINED metadata under
   MetadataMode.EMBED with the production excluded-key set — lineage
   keys must not leak into the payload, retained keys must.
"""

from __future__ import annotations

from pathlib import Path

from llama_index.core.schema import MetadataMode, TextNode

from omrg.core.ingestion.pipeline import gather_supported_files
from omrg.core.ingestion.source_state import (
    _RETAINED_EMBED_METADATA_KEYS,
    SOURCE_ID_KEY,
)


def test_gather_supported_files_excludes_manifest_jsonl(tmp_path: Path) -> None:
    """The corpus manifest jsonl is never selected for ingestion."""
    (tmp_path / "doc.md").write_text("# Doc\n\nbody", encoding="utf-8")
    (tmp_path / "langchain_manifest.jsonl").write_text('{"path": "x"}\n', encoding="utf-8")
    (tmp_path / "note.txt").write_text("plain text", encoding="utf-8")

    selected = gather_supported_files(tmp_path)
    names = (
        {p.name for p in selected}
        if not isinstance(selected, tuple)
        else {p.name for p in selected[0]}
    )

    assert names == {"doc.md", "note.txt"}, "manifest jsonl must never be gathered"


def test_embed_payload_keeps_retained_and_excludes_lineage_keys() -> None:
    """Payload composition matches the production embed contract."""
    metadata = {
        "file_path": "/corpus/langchain/00001_deadbeef.md",
        "file_name": "00001_deadbeef.md",
        "content_type": "text/markdown",
        "header_path": "/Report/Findings/",
        SOURCE_ID_KEY: "src_abc",
        "omrg_source_version": "v1",
        "omrg_source_attempt": "att_1",
        "omrg_chunk_id": "chk_1",
    }
    node = TextNode(text="chunk body text", metadata=metadata)
    retained = set(_RETAINED_EMBED_METADATA_KEYS)
    node.excluded_embed_metadata_keys = sorted(set(metadata) - retained)

    payload = node.get_content(metadata_mode=MetadataMode.EMBED)

    assert "chunk body text" in payload
    assert "00001_deadbeef.md" in payload, "retained file_name must be embedded"
    assert "/Report/Findings/" in payload, "retained header_path must be embedded"
    assert "text/markdown" in payload, "retained content_type must be embedded"
    assert "src_abc" not in payload, "lineage source id must not be embedded"
    assert "chk_1" not in payload, "lineage chunk id must not be embedded"
