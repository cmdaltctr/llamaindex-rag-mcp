"""Helper: ingest the Exp 6 corpus into baseline and candidate ChromaDBs.

The eval runner expects two pre-populated ChromaDB directories. This script
produces both:

  - ./chroma_md_baseline   — SentenceSplitter only (Markdown branch disabled)
  - ./chroma_md_new        — MarkdownNodeParser → SentenceSplitter (current code)

Run from the repo root:

    EMBED_MODEL=qwen3-embedding:0.6b \\
      uv run python experiments/6-markdown-chunking-quality-2026-05-27/ingest_both.py
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
from pathlib import Path
from unittest.mock import patch

# Ensure project source is importable.
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from dotenv import load_dotenv

load_dotenv()

EXPERIMENT_DIR = Path(__file__).parent
CORPUS = EXPERIMENT_DIR / "corpus"
BASELINE_DIR = EXPERIMENT_DIR / "chroma_md_baseline"
CANDIDATE_DIR = EXPERIMENT_DIR / "chroma_md_new"


async def _ingest(corpus: Path, target: Path, *, force_baseline: bool) -> None:
    """Ingest ``corpus`` into a fresh ChromaDB at ``target``.

    When ``force_baseline`` is True, the Markdown branch is disabled by
    patching ``Path.suffix`` on the ingestion module — every file is
    routed through the bare ``SentenceSplitter`` regardless of extension.
    """
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)

    os.environ["CHROMA_PERSIST_DIR"] = str(target.resolve())
    os.environ["COLLECTION_NAME"] = "documents"
    os.environ["METADATA_EXTRACTION_MODE"] = "disabled"
    os.environ["CHUNK_OVERLAP"] = "100"

    # Re-import to pick up the env vars.
    for mod_name in list(sys.modules):
        if mod_name.startswith("rag_mcp"):
            sys.modules.pop(mod_name, None)

    from rag_mcp import ingestion as _ing

    if force_baseline:
        # Patch the ingestion module's read-and-chunk function so that
        # the Markdown branch never fires. We do this surgically by
        # replacing the suffix check inline.
        original = _ing._read_and_chunk_file_async

        async def _baseline_read_and_chunk(file_path, **kwargs):
            return await original(Path(str(file_path)).with_suffix(".txt"), **kwargs) \
                if False else await _force_sentence_splitter(file_path, **kwargs)

        async def _force_sentence_splitter(file_path, *, chunk_size=None, chunk_overlap=None):
            """Re-implementation that always uses SentenceSplitter."""
            from llama_index.core import SimpleDirectoryReader
            from llama_index.core.node_parser import SentenceSplitter

            from rag_mcp.config import CHUNK_OVERLAP, CHUNK_SIZE

            cs = chunk_size if chunk_size is not None else CHUNK_SIZE
            co = chunk_overlap if chunk_overlap is not None else CHUNK_OVERLAP

            def _read():
                return SimpleDirectoryReader(
                    input_files=[str(file_path)], filename_as_id=True
                ).load_data()

            documents = await asyncio.to_thread(_read)
            splitter = SentenceSplitter(chunk_size=cs, chunk_overlap=co)
            return await asyncio.to_thread(
                splitter.get_nodes_from_documents, documents
            )

        _ing._read_and_chunk_file_async = _baseline_read_and_chunk

    print(f"  Ingesting {corpus} → {target} (baseline={force_baseline})")
    result = await _ing.ingest_path_async(str(corpus))
    print(f"  status={result.get('status')} chunks={result.get('chunks_created')}")


async def main() -> None:
    if not CORPUS.exists():
        print(f"ERROR: corpus not found at {CORPUS}")
        sys.exit(1)

    print("[1/2] Baseline ingest (SentenceSplitter only)")
    await _ingest(CORPUS, BASELINE_DIR, force_baseline=True)

    print("\n[2/2] Candidate ingest (MarkdownNodeParser → SentenceSplitter)")
    await _ingest(CORPUS, CANDIDATE_DIR, force_baseline=False)

    print(f"\nBoth ChromaDBs ready:")
    print(f"  baseline:  {BASELINE_DIR}")
    print(f"  candidate: {CANDIDATE_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
