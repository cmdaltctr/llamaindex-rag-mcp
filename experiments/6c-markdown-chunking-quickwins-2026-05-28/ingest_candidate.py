"""Build one Experiment 6c candidate ChromaDB variant.

The baseline is copied from 6b and is not rebuilt here.  This script only
builds candidate variants under ``chroma_candidate_runs/<run-id>/``.
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


def _bool_env(value: bool) -> str:
    return "true" if value else "false"


async def _ingest_candidate(out_dir: Path) -> None:
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

    print(f"Ingesting candidate: {CORPUS} → {out_dir}")
    print(f"  MARKDOWN_CHUNK_SIZE={os.environ.get('MARKDOWN_CHUNK_SIZE')}")
    print(f"  MARKDOWN_HEADING_PREPEND={os.environ.get('MARKDOWN_HEADING_PREPEND')}")
    print(f"  MARKDOWN_MIN_CHUNK_FRACTION={os.environ.get('MARKDOWN_MIN_CHUNK_FRACTION')}")
    result = await _ing.ingest_path_async(str(CORPUS))
    print(f"  status={result.get('status')} chunks={result.get('chunks_created')}")
    if result.get("status") != "ok":
        raise SystemExit(result)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chunk-size", type=int, default=512)
    parser.add_argument("--heading-prepend", action="store_true")
    parser.add_argument("--min-size-floor", type=float, default=0.0)
    parser.add_argument(
        "--metadata-copy",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Kept for run-matrix traceability; metadata copy is currently always-on.",
    )
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    if not CORPUS.exists():
        raise SystemExit(f"Corpus not found: {CORPUS}")

    os.environ["MARKDOWN_CHUNK_SIZE"] = str(args.chunk_size)
    os.environ["MARKDOWN_HEADING_PREPEND"] = _bool_env(args.heading_prepend)
    os.environ["MARKDOWN_MIN_CHUNK_FRACTION"] = str(args.min_size_floor)
    os.environ["MARKDOWN_METADATA_COPY"] = _bool_env(args.metadata_copy)

    asyncio.run(_ingest_candidate(args.out_dir))


if __name__ == "__main__":
    main()
