"""Experiment 25 token accounting: chunk the corpus both ways, count tokens.

Protocol pre-build step (task 1.6 cost gate basis): with NO embedding calls,
run the production chunker over the preserved FreshStack corpus under the
baseline splitter and under the model-token Markdown chunker, then count
embedding-payload tokens with the pinned Qwen tokenizer.

Usage (mode selects the env before omrg imports):

    uv run python token_accounting.py --mode baseline
    uv run python token_accounting.py --mode candidate

Writes output/token_accounting_<mode>.json atomically.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = EXP_DIR.parent.parent
CORPUS = EXP_DIR / "corpus"
TOKENIZER_MODEL = "Qwen/Qwen3-Embedding-4B"
TOKENIZER_REVISION = "5cf2132abc99cad020ac570b19d031efec650f2b"

parser = argparse.ArgumentParser()
parser.add_argument("--mode", choices=["baseline", "candidate"], required=True)
parser.add_argument("--limit", type=int, default=0, help="smoke: first N files only")
args = parser.parse_args()

from dotenv import load_dotenv  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")
os.environ.update(
    {
        "VECTOR_STORE": "lancedb",
        "EMBED_PROVIDER": "cloud",
        "CLOUD_BACKEND": "openrouter",
        "OPENROUTER_EMBED_MODEL": "qwen/qwen3-embedding-4b",
        "METADATA__EXTRACTION_MODE": "disabled",
        "PDF_READER": "pypdf",
    }
)
if args.mode == "candidate":
    os.environ.update(
        {
            "EMBEDDING__TOKENIZER_MODEL": TOKENIZER_MODEL,
            "EMBEDDING__TOKENIZER_REVISION": TOKENIZER_REVISION,
        }
    )

sys.path.insert(0, str(PROJECT_ROOT / "src"))


def main() -> None:
    """Chunk every corpus file under the selected mode and count tokens."""
    from omrg.compose import ensure_runtime_setup
    from omrg.core.ingestion.chunker import read_and_chunk_file_async
    from omrg.integrations.tokenizer import load_tokenizer

    ensure_runtime_setup()
    tokenizer = load_tokenizer(TOKENIZER_MODEL, TOKENIZER_REVISION)

    files = sorted(p for p in CORPUS.rglob("*") if p.is_file())
    if args.limit:
        files = files[: args.limit]

    started = time.perf_counter()
    total_chunks = 0
    total_tokens = 0
    max_chunk_tokens = 0
    header_path_chunks = 0
    errors = 0
    error_samples: list[dict] = []

    async def run() -> None:
        nonlocal total_chunks, total_tokens, max_chunk_tokens, header_path_chunks, errors
        for i, path in enumerate(files, 1):
            try:
                nodes = await read_and_chunk_file_async(path)
            except Exception as exc:
                errors += 1
                if len(error_samples) < 5:
                    error_samples.append(
                        {
                            "file": str(path.relative_to(CORPUS)),
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )
                continue
            for node in nodes:
                text = node.text or node.get_content()
                count = len(tokenizer.encode(text).ids)
                total_chunks += 1
                total_tokens += count
                max_chunk_tokens = max(max_chunk_tokens, count)
                if (node.metadata or {}).get("header_path"):
                    header_path_chunks += 1
            if i % 500 == 0:
                print(
                    f"[{args.mode}] {i}/{len(files)} files, "
                    f"{total_chunks} chunks, {total_tokens} tokens",
                    flush=True,
                )

    asyncio.run(run())

    report = {
        "mode": args.mode,
        "tokenizer": {"model": TOKENIZER_MODEL, "revision": TOKENIZER_REVISION},
        "files": len(files),
        "chunks": total_chunks,
        "embedded_tokens": total_tokens,
        "max_chunk_tokens": max_chunk_tokens,
        "chunks_with_header_path": header_path_chunks,
        "chunk_errors": errors,
        "error_samples": error_samples,
        "elapsed_s": round(time.perf_counter() - started, 1),
    }
    out = EXP_DIR / f"output/token_accounting_{args.mode}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(report, indent=2), encoding="utf-8")
    tmp.replace(out)
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
