"""Build Experiment 7 ground truth and pre-registration (protocol section 9).

Phase A (this script) runs BEFORE any metadata-path treatment:

1. Reads each fixture through the production ``SimpleDirectoryReader``
   (same reader the ingestion chunker uses for non-PDF documents).
2. Splits each document with the declared metadata splitting policy — the
   production ``SentenceSplitter(chunk_size=512, chunk_overlap=100)``
   construction from ``core/metadata/llamaindex.py`` — and nothing else.
3. Writes ``fixtures/expected_chunks.json`` with per-chunk sha256, token
   count, char count, and first marker.
4. Writes ``fixtures/manifest.json`` pre-registering: document identities,
   splitting policy + tokenizer identity, fake-LLM output templates, the
   documented aggregation rule (first non-empty per-chunk value wins), and
   the expected aggregated metadata per document derived from chunk 0's
   marker through the production aggregation helpers.

Preflight assertions (protocol section 12) enforced here: every document
produces more than the maximum tested cap of chunks; the synthetic
document shows a material token-vs-character divergence (max/min chars per
token across chunks >= 1.5); every chunk's first marker is unique so call
attribution is unambiguous.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fake_llm import MARKER_RE, fake_output  # noqa: E402
from llama_index.core import (  # noqa: E402
    Document,
    SimpleDirectoryReader,
)
from llama_index.core.node_parser import SentenceSplitter  # noqa: E402
from llama_index.core.utils import get_tokenizer  # noqa: E402

from rag_mcp.core.metadata._common import (  # noqa: E402
    _strip_llm_prefix,
    _truncate_keywords,
    _truncate_summary,
)
from rag_mcp.core.metadata.llamaindex import (  # noqa: E402
    _derive_category,
    _parse_keywords_from_meta,
)

FIXTURES_DIR = SCRIPT_DIR / "fixtures"
EXPECTED_PATH = FIXTURES_DIR / "expected_chunks.json"
MANIFEST_PATH = FIXTURES_DIR / "manifest.json"
CHUNK_SIZE = 512
CHUNK_OVERLAP = 100
MAX_TESTED_CAP = 10
DIVERGENCE_FLOOR = 1.5

DOC_FILES = {
    "synthetic": "synthetic_token_char_divergence.txt",
    "realistic_md": "realistic_long_document.md",
}


def read_document_text(path: Path) -> str:
    """Read one fixture exactly as the ingestion chunker does."""
    reader = SimpleDirectoryReader(input_files=[str(path)], filename_as_id=True)
    documents = reader.load_data()
    return "\n".join(document.get_content() for document in documents)


def split_document(text: str, file_name: str) -> list[Any]:
    """Split with the declared production metadata policy (nothing else)."""
    splitter = SentenceSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    document = Document(text=text, metadata={"file_name": file_name})
    return splitter.get_nodes_from_documents([document])


def tokenizer_identity() -> dict[str, Any]:
    """Record the identity of the locked default tokenizer."""
    tokenizer = get_tokenizer()
    return {
        "class": type(tokenizer).__name__,
        "name": str(getattr(tokenizer, "name", "")),
        "module": type(tokenizer).__module__,
    }


def expected_aggregation(chunk0_marker: str) -> dict[str, Any]:
    """Apply the documented aggregation rule to chunk 0's fake outputs.

    Rule (``core/metadata/llamaindex.py::_aggregate_llamaindex_metadata``,
    llama-index 0.14.23): the first non-empty per-chunk value wins for
    keywords, summary, and document title; the fake extractors succeed on
    every chunk, so chunk 0 supplies all three; category derives from the
    first keyword.
    """
    keyword_output = fake_output("keyword", f"MARK{chunk0_marker}X context")
    keywords = _truncate_keywords(_parse_keywords_from_meta(keyword_output))
    title_output = fake_output("title_combine", f"Title node MARK{chunk0_marker}X, tail")
    title = _strip_llm_prefix(title_output)
    summary_output = fake_output("summary", f"MARK{chunk0_marker}X context")
    summary = _truncate_summary(_strip_llm_prefix(summary_output))
    return {
        "aggregation_rule": "first non-empty per-chunk value wins (chunk 0)",
        "chunk0_marker": chunk0_marker,
        "category": _derive_category(keywords, title),
        "keywords": keywords,
        "keywords_flat": ", ".join(keywords),
        "summary": summary,
        "document_title": title,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    tokenizer = get_tokenizer()
    per_doc: dict[str, Any] = {}
    for doc_id, file_name in DOC_FILES.items():
        path = FIXTURES_DIR / file_name
        text = read_document_text(path)
        nodes = split_document(text, path.name)

        chunks = []
        for node in nodes:
            content = node.get_content()
            match = MARKER_RE.search(content)
            tokens = len(tokenizer(content))
            chunks.append(
                {
                    "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                    "tokens": tokens,
                    "chars": len(content),
                    "chars_per_token": round(len(content) / tokens, 3) if tokens else None,
                    "first_marker": match.group(1) if match else None,
                }
            )

        markers = [chunk["first_marker"] for chunk in chunks]
        if len(chunks) <= MAX_TESTED_CAP:
            raise SystemExit(
                f"{doc_id}: {len(chunks)} chunks <= max tested cap {MAX_TESTED_CAP} "
                "(protocol section 12 preflight)"
            )
        if len(set(markers)) != len(markers) or any(m is None for m in markers):
            raise SystemExit(f"{doc_id}: first markers are not unique/complete: {markers[:12]}")

        ratios = [chunk["chars_per_token"] for chunk in chunks if chunk["chars_per_token"]]
        divergence = round(max(ratios) / min(ratios), 3)
        per_doc[doc_id] = {
            "file": f"fixtures/{file_name}",
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "source_chars": len(text),
            "chunk_count": len(chunks),
            "chunks": chunks,
            "max_chars_per_token": max(ratios),
            "min_chars_per_token": min(ratios),
            "token_char_divergence_ratio": divergence,
            "expected_aggregation": expected_aggregation(markers[0]),
        }

    synthetic = per_doc["synthetic"]
    if synthetic["token_char_divergence_ratio"] < DIVERGENCE_FLOOR:
        raise SystemExit(
            f"synthetic divergence {synthetic['token_char_divergence_ratio']} < {DIVERGENCE_FLOOR}"
        )

    EXPECTED_PATH.write_text(
        json.dumps(
            {
                "splitting_policy": {
                    "splitter": "SentenceSplitter",
                    "chunk_size": CHUNK_SIZE,
                    "chunk_overlap": CHUNK_OVERLAP,
                    "construction": "core/metadata/llamaindex.py::_extract_llamaindex_async",
                },
                "documents": per_doc,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    pre_registration = {
        "written_before_treatments": True,
        "protocol_note": (
            "Ground truth (expected chunk hashes/tokens/chars) was produced by the declared "
            "SentenceSplitter alone; the expected aggregation below was derived from chunk 0's "
            "marker through the documented first-non-empty rule BEFORE any metadata-path run "
            "(protocol section 9)."
        ),
        "splitting_policy": {"chunk_size": CHUNK_SIZE, "chunk_overlap": CHUNK_OVERLAP},
        "tokenizer": tokenizer_identity(),
        "fake_llm": {
            "class": "CountingMockLLM (fake_llm.py, subclasses llama_index MockLLM)",
            "output_templates": {
                "keyword": "KW{marker}A, KW{marker}B",
                "summary": "Summary for marker {marker} of the corpus section.",
                "title_node": "Title node {marker}",
                "title_combine": "Combined title {marker}",
            },
            "aggregation_rule": "first non-empty per-chunk value wins (chunk 0)",
        },
        "documents": {
            doc_id: {
                "file": entry["file"],
                "sha256": entry["sha256"],
                "chunk_count": entry["chunk_count"],
                "token_char_divergence_ratio": entry["token_char_divergence_ratio"],
                "expected_aggregation": entry["expected_aggregation"],
            }
            for doc_id, entry in per_doc.items()
        },
    }
    MANIFEST_PATH.write_text(json.dumps(pre_registration, indent=2) + "\n", encoding="utf-8")
    print(
        f"ground truth: {synthetic['chunk_count']} synthetic chunks "
        f"(divergence {synthetic['token_char_divergence_ratio']}), "
        f"{per_doc['realistic_md']['chunk_count']} realistic chunks",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
