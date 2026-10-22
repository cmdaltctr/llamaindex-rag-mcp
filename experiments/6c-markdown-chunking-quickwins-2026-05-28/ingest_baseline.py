"""Build Experiment 6c baseline ChromaDB from the 6c-local corpus.

This forces SentenceSplitter-only chunking so baseline metadata paths point at
``experiments/6c.../corpus`` rather than copied 6b paths.
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
    """Read and chunk a file with SentenceSplitter only."""
    from llama_index.core import SimpleDirectoryReader
    from llama_index.core.node_parser import SentenceSplitter

    from omrg.config import CHUNK_OVERLAP, CHUNK_SIZE

    cs = chunk_size if chunk_size is not None else CHUNK_SIZE
    co = chunk_overlap if chunk_overlap is not None else CHUNK_OVERLAP

    def _read():
        return SimpleDirectoryReader(input_files=[str(file_path)], filename_as_id=True).load_data()

    documents = await asyncio.to_thread(_read)
    splitter = SentenceSplitter(chunk_size=cs, chunk_overlap=co)
    return await asyncio.to_thread(splitter.get_nodes_from_documents, documents)


async def _ingest_baseline(out_dir: Path) -> None:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    os.environ["CHROMA_PERSIST_DIR"] = str(out_dir.resolve())
    os.environ["COLLECTION_NAME"] = "documents"
    os.environ["METADATA_EXTRACTION_MODE"] = "disabled"
    os.environ["CHUNK_OVERLAP"] = "100"

    for mod_name in list(sys.modules):
        if mod_name.startswith("omrg"):
            sys.modules.pop(mod_name, None)

    from omrg import ingestion as _ing

    _ing._read_and_chunk_file_async = _force_sentence_splitter
    print(f"Ingesting baseline: {CORPUS} → {out_dir}")
    result = await _ing.ingest_path_async(str(CORPUS))
    print(f"  status={result.get('status')} chunks={result.get('chunks_created')}")
    if result.get("status") != "ok":
        raise SystemExit(result)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=EXPERIMENT_DIR / "chroma_baseline")
    args = parser.parse_args()

    if not CORPUS.exists():
        raise SystemExit(f"Corpus not found: {CORPUS}")
    asyncio.run(_ingest_baseline(args.out_dir))


if __name__ == "__main__":
    main()
