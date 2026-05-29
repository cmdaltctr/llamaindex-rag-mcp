"""Build one ChromaDB index per CHUNK_OVERLAP value for Experiment 7a.

Forces SentenceSplitter-only chunking (no Markdown branch) so the only
variable in the sweep is ``CHUNK_OVERLAP``.  Mirrors the pattern used by
``experiments/6c.../ingest_baseline.py``.

One index per overlap value lives under
``chroma_overlap_{value}/``.  All indexes are built from this
experiment's local ``corpus/`` directory; no symlinks.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

EXPERIMENT_DIR = Path(__file__).parent
CORPUS = EXPERIMENT_DIR / "corpus"



async def _force_sentence_splitter(file_path: Path, *, chunk_size=None, chunk_overlap=None):
    """Read and chunk a file with SentenceSplitter only.

    This monkey-patches the ingestion module's ``_read_and_chunk_file_async``
    so the Markdown branch is bypassed for every file.  ``chunk_size`` and
    ``chunk_overlap`` honour the environment-driven defaults from
    ``rag_mcp.config`` unless explicitly overridden.
    """
    from llama_index.core import SimpleDirectoryReader
    from llama_index.core.node_parser import SentenceSplitter

    from rag_mcp.config import CHUNK_OVERLAP, CHUNK_SIZE

    cs = chunk_size if chunk_size is not None else CHUNK_SIZE
    co = chunk_overlap if chunk_overlap is not None else CHUNK_OVERLAP

    def _read():
        return SimpleDirectoryReader(input_files=[str(file_path)], filename_as_id=True).load_data()

    documents = await asyncio.to_thread(_read)
    splitter = SentenceSplitter(chunk_size=cs, chunk_overlap=co)
    return await asyncio.to_thread(splitter.get_nodes_from_documents, documents)


async def _ingest_one_overlap(out_dir: Path, *, overlap: int) -> dict:
    """Build a fresh ChromaDB at ``out_dir`` using ``CHUNK_OVERLAP=overlap``."""
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    os.environ["CHROMA_PERSIST_DIR"] = str(out_dir.resolve())
    os.environ["COLLECTION_NAME"] = "documents"
    os.environ["METADATA_EXTRACTION_MODE"] = "disabled"
    os.environ["CHUNK_OVERLAP"] = str(overlap)

    # Force a clean reload so the new CHUNK_OVERLAP is picked up by config.py
    # at import time rather than being shadowed by a previously-cached value.
    for mod_name in list(sys.modules):
        if mod_name.startswith("rag_mcp"):
            sys.modules.pop(mod_name, None)

    from rag_mcp import ingestion as _ing

    _ing._read_and_chunk_file_async = _force_sentence_splitter
    print(f"[overlap={overlap}] ingesting {CORPUS} -> {out_dir}")
    result = await _ing.ingest_path_async(str(CORPUS))
    print(f"[overlap={overlap}]   status={result.get('status')} chunks={result.get('chunks_created')}")
    if result.get("status") != "ok":
        raise SystemExit(result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build one ChromaDB index per CHUNK_OVERLAP value.",
    )
    parser.add_argument(
        "--overlaps",
        type=str,
        default="32,64,100,128",
        help="Comma-separated overlap values (default: 32,64,100,128)",
    )
    parser.add_argument(
        "--out-root",
        type=Path,
        default=EXPERIMENT_DIR,
        help="Parent directory for the per-overlap chroma_overlap_<value> dirs.",
    )
    args = parser.parse_args()

    if not CORPUS.exists():
        raise SystemExit(f"Corpus not found: {CORPUS}")

    overlaps = [int(x) for x in args.overlaps.split(",") if x.strip()]
    print(f"Experiment 7a — building indexes for overlaps={overlaps}")

    for overlap in overlaps:
        out_dir = args.out_root / f"chroma_overlap_{overlap}"
        asyncio.run(_ingest_one_overlap(out_dir, overlap=overlap))


if __name__ == "__main__":
    main()
