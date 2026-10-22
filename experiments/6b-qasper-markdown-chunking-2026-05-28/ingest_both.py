"""Ingest Experiment 6b corpus into baseline and candidate ChromaDBs."""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from dotenv import load_dotenv


load_dotenv()

EXPERIMENT_DIR = Path(__file__).parent
CORPUS = EXPERIMENT_DIR / "corpus"
BASELINE_DIR = EXPERIMENT_DIR / "chroma_baseline"
CANDIDATE_DIR = EXPERIMENT_DIR / "chroma_candidate"


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


async def _ingest(target: Path, *, force_baseline: bool) -> None:
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)

    os.environ["CHROMA_PERSIST_DIR"] = str(target.resolve())
    os.environ["COLLECTION_NAME"] = "documents"
    os.environ["METADATA_EXTRACTION_MODE"] = "disabled"
    os.environ["CHUNK_OVERLAP"] = "100"

    for mod_name in list(sys.modules):
        if mod_name.startswith("omrg"):
            sys.modules.pop(mod_name, None)

    from omrg import ingestion as _ing

    if force_baseline:
        _ing._read_and_chunk_file_async = _force_sentence_splitter

    print(f"Ingesting {CORPUS} → {target} (baseline={force_baseline})")
    result = await _ing.ingest_path_async(str(CORPUS))
    print(f"  status={result.get('status')} chunks={result.get('chunks_created')}")


async def main() -> None:
    if not CORPUS.exists():
        raise SystemExit(
            f"Corpus not found: {CORPUS}\n"
            "Run prepare_dataset.py first."
        )
    print("[1/2] Baseline ingest (SentenceSplitter only)")
    await _ingest(BASELINE_DIR, force_baseline=True)
    print("\n[2/2] Candidate ingest (MarkdownNodeParser → SentenceSplitter)")
    await _ingest(CANDIDATE_DIR, force_baseline=False)
    print("\nBoth ChromaDBs ready:")
    print(f"  baseline:  {BASELINE_DIR}")
    print(f"  candidate: {CANDIDATE_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
