"""Build a ChromaDB index for Experiment 11 using a specific PDF parser.

Usage:
    CHROMA_PERSIST_DIR=./output/chroma_pypdf PDF_READER=pypdf \\
        uv run python build_indexes.py --parser pypdf

    CHROMA_PERSIST_DIR=./output/chroma_liteparse PDF_READER=liteparse \\
        uv run python build_indexes.py --parser liteparse

Records per-file parsing wall-clock to ``output/build_<parser>_timing.json``
for the H2 (speed) pass gate.

This script intentionally bypasses the not-yet-existing ``readers/`` factory:
the experiment must validate the *hypothesis* (LiteParse output produces
better RAG results than pypdf), not a specific adapter API. The adapter
implementation (OpenSpec tasks 6–9) ships only after this experiment PASSes.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")

# Import project internals. We use the existing chunking + embedding pipeline
# so the only variable is the parser, not downstream processing.
from llama_index.core import Document, Settings  # noqa: E402
from llama_index.core.node_parser import SentenceSplitter  # noqa: E402

from rag_mcp.core.ingestion import (  # noqa: E402
    embed_and_write_async,
    gather_supported_files,
)
from rag_mcp.core.settings import get_default_effective_settings  # noqa: E402

CORPUS_DIR = SCRIPT_DIR / "corpus"
OUTPUT_DIR = SCRIPT_DIR / "output"


def _parse_with_pypdf(file_path: Path) -> list[Document]:
    """Parse a PDF using the current production path (pypdf via llama-index)."""
    from llama_index.core import SimpleDirectoryReader

    reader = SimpleDirectoryReader(
        input_files=[str(file_path)],
        filename_as_id=True,
    )
    return reader.load_data()


def _parse_with_liteparse(file_path: Path) -> list[Document]:
    """Parse a PDF using LiteParse directly and wrap output as LlamaIndex Documents.

    Adds bbox metadata per spec requirement so downstream retrieval can
    optionally consume it. Mirrors what the eventual ``LiteParseReader``
    adapter in ``src/rag_mcp/readers/liteparse_reader.py`` will produce.
    """
    from liteparse import LiteParse

    # OCR disabled: the corpus is all digital arXiv preprints (no scanned
    # PDFs per corpus/MANIFEST.md). OCR would add ~16s/file of pure overhead
    # and unfairly penalise LiteParse on the H2 speed gate. The spec default
    # for LITEPARSE_OCR_ENABLED is False (task 6.5).
    parser = LiteParse(ocr_enabled=False, quiet=True)
    result = parser.parse(str(file_path))

    documents: list[Document] = []
    for page in result.pages:
        # Reconstruct text in reading order; LiteParse already orders items.
        page_text = "\n".join(item.text for item in page.text_items)
        if not page_text.strip():
            continue

        # Crude column detection: if any item's x-coordinate is > 50% of the
        # max x on the page, the page has multiple columns. The eventual
        # adapter will use LiteParse's grid projection for this; the
        # experiment just needs the metadata to be present.
        if page.text_items:
            max_x = max(item.x + item.width for item in page.text_items)
            has_left = any(item.x < max_x * 0.45 for item in page.text_items)
            has_right = any(item.x >= max_x * 0.45 for item in page.text_items)
            if has_left and has_right:
                # Best-effort column labelling by median x of each item.
                column = "left" if page.text_items[0].x < max_x * 0.45 else "right"
            else:
                column = "single"
        else:
            column = "single"

        bbox = [
            min((item.x for item in page.text_items), default=0.0),
            min((item.y for item in page.text_items), default=0.0),
            max((item.x + item.width for item in page.text_items), default=0.0),
            max((item.y + item.height for item in page.text_items), default=0.0),
        ]

        documents.append(
            Document(
                text=page_text,
                metadata={
                    "pdf_reader": "liteparse",
                    "page": page.page_num,
                    "column": column,
                    "section_bbox": json.dumps(bbox),
                    "bbox_schema_version": 1,
                    "file_path": str(file_path),
                    "file_name": file_path.name,
                },
            )
        )
    return documents


def _chunk_documents(documents: list[Document], *, chunk_size: int, chunk_overlap: int) -> list:
    """Run the same SentenceSplitter the production pipeline uses."""
    splitter = SentenceSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    nodes = splitter.get_nodes_from_documents(documents)
    return nodes


async def _build(parser: str) -> dict[str, Any]:
    """Build a complete ChromaDB index from corpus/ using the named parser."""
    effective_settings = get_default_effective_settings()
    files, skipped = gather_supported_files(CORPUS_DIR)
    if not files:
        raise SystemExit(
            f"No supported files in {CORPUS_DIR}. Populate corpus/ per "
            f"corpus/README.md before running."
        )
    if skipped:
        print(
            f"Skipping {len(skipped)} unsupported files: {[s['file'] for s in skipped]}", flush=True
        )

    print(f"Building index with parser={parser} for {len(files)} PDFs...", flush=True)

    parse_fn = _parse_with_pypdf if parser == "pypdf" else _parse_with_liteparse

    timing: list[dict[str, Any]] = []
    all_nodes: list = []
    build_started = time.perf_counter()

    for index, file_path in enumerate(files, start=1):
        file_started = time.perf_counter()
        try:
            documents = parse_fn(file_path)
        except Exception as exc:
            print(f"  [{index}/{len(files)}] FAILED {file_path.name}: {exc}", flush=True)
            timing.append(
                {
                    "file": file_path.name,
                    "status": "failed",
                    "error": str(exc),
                    "parse_seconds": round(time.perf_counter() - file_started, 3),
                }
            )
            continue

        parse_seconds = time.perf_counter() - file_started
        chunk_started = time.perf_counter()
        nodes = _chunk_documents(
            documents,
            chunk_size=effective_settings.chunking.chunk_size,
            chunk_overlap=effective_settings.chunking.chunk_overlap,
        )
        chunk_seconds = time.perf_counter() - chunk_started

        all_nodes.extend(nodes)
        timing.append(
            {
                "file": file_path.name,
                "status": "ok",
                "pages": len(documents),
                "chunks": len(nodes),
                "parse_seconds": round(parse_seconds, 3),
                "chunk_seconds": round(chunk_seconds, 3),
            }
        )
        print(
            f"  [{index}/{len(files)}] {file_path.name}: "
            f"{len(documents)} pages, {len(nodes)} chunks, "
            f"parse={parse_seconds:.2f}s",
            flush=True,
        )

    if not all_nodes:
        raise SystemExit(
            "No chunks produced. All files failed to parse. "
            "Check the parser install and corpus contents."
        )

    print(
        f"\nEmbedding {len(all_nodes)} chunks via {Settings.embed_model.model_name}...", flush=True
    )
    embed_started = time.perf_counter()
    chunks_written = await embed_and_write_async(
        all_nodes,
        embed_concurrency=effective_settings.ingestion.embed_concurrency,
    )
    embed_seconds = time.perf_counter() - embed_started

    total_seconds = time.perf_counter() - build_started
    summary = {
        "parser": parser,
        "files_total": len(files),
        "files_ok": sum(1 for t in timing if t["status"] == "ok"),
        "files_failed": sum(1 for t in timing if t["status"] == "failed"),
        "chunks_written": chunks_written,
        "total_seconds": round(total_seconds, 3),
        "parse_seconds_total": round(sum(t.get("parse_seconds", 0) for t in timing), 3),
        "chunk_seconds_total": round(sum(t.get("chunk_seconds", 0) for t in timing), 3),
        "embed_seconds_total": round(embed_seconds, 3),
        "per_file": timing,
    }

    timing_path = OUTPUT_DIR / f"build_{parser}_timing.json"
    timing_path.parent.mkdir(parents=True, exist_ok=True)
    timing_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSummary written to {timing_path}", flush=True)
    print(
        f"Total: {total_seconds:.1f}s "
        f"(parse {summary['parse_seconds_total']}s, "
        f"chunk {summary['chunk_seconds_total']}s, "
        f"embed {summary['embed_seconds_total']}s)",
        flush=True,
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--parser",
        required=True,
        choices=["pypdf", "liteparse"],
        help="Which PDF parser to use for building this index.",
    )
    args = parser.parse_args()

    if not CORPUS_DIR.exists() or not any(CORPUS_DIR.glob("*.pdf")):
        raise SystemExit(f"No PDFs in {CORPUS_DIR}. Populate corpus/ per corpus/README.md.")

    chroma_dir = os.environ.get("CHROMA_PERSIST_DIR")
    if not chroma_dir:
        raise SystemExit(
            "CHROMA_PERSIST_DIR must be set to an isolated directory, "
            "e.g. ./experiments/11-liteparse-pdf-quality-2026-06-20/output/chroma_pypdf"
        )

    print(f"CHROMA_PERSIST_DIR={chroma_dir}", flush=True)
    print(f"PDF_READER={os.environ.get('PDF_READER', '<unset>')}", flush=True)

    from rag_mcp import compose

    compose.ensure_runtime_setup()
    asyncio.run(_build(args.parser))


if __name__ == "__main__":
    main()
