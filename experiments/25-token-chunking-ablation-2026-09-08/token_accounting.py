"""DEPRECATED 2026-09-08 — kept as the record of a defective method.

This standalone re-chunking counter was superseded by verify_accounting.py
after an external review proved its defects: it chunked the corpus
manifest jsonl production never selects (+~40k chunks), counted body text
instead of the composed MetadataMode.EMBED payload, and its shared
additive contamination did NOT cancel in the ratio (it loosened the
nominal 1.15 cap to ~1.37 on genuine body tokens). Future pre-build
counts must reuse production preparation (gather_supported_files,
per-pack detection) with an in-memory store and a network-blocked
request recorder, per the review's guidance.
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
    """Chunk every corpus file under the selected mode and count tokens.

    Replicates the production ingestion dispatch exactly: Magika
    content-type detection (binary files skipped), the resolved
    strategy_fallback, and one operation-scoped markdown chunking
    resolution — the same call shape ``ingest_path_async`` uses.
    """
    from omrg.compose import ensure_runtime_setup
    from omrg.core.chunking.model_token import resolve_markdown_chunking
    from omrg.core.codebase.codebase_map import detect_file_types
    from omrg.core.ingestion.chunker import (
        read_and_chunk_file_async,
        resolve_effective_settings,
    )
    from omrg.integrations.tokenizer import load_tokenizer

    ensure_runtime_setup()
    tokenizer = load_tokenizer(TOKENIZER_MODEL, TOKENIZER_REVISION)
    resolved = resolve_effective_settings(None)
    markdown_chunking = resolve_markdown_chunking(resolved)

    content_type_map: dict[str, str] = {}
    try:
        inventory = detect_file_types(str(CORPUS))
        for entry in inventory.entries:
            content_type_map[entry.path] = f"{entry.group}/{entry.label}"
    except Exception as exc:  # same degradation contract as the pipeline
        print(f"[accounting] Magika detection failed ({exc}); extension routing", flush=True)

    files = sorted(p for p in CORPUS.rglob("*") if p.is_file())
    if args.limit:
        files = files[: args.limit]

    started = time.perf_counter()
    total_chunks = 0
    total_tokens = 0
    max_chunk_tokens = 0
    header_path_chunks = 0
    errors = 0
    binary_skipped = 0
    error_samples: list[dict] = []

    async def run() -> None:
        nonlocal total_chunks, total_tokens, max_chunk_tokens
        nonlocal header_path_chunks, errors, binary_skipped
        for i, path in enumerate(files, 1):
            rel = str(path.relative_to(CORPUS))
            content_type = content_type_map.get(rel)
            if content_type and content_type.startswith("binary"):
                binary_skipped += 1
                continue
            try:
                nodes = await read_and_chunk_file_async(
                    path,
                    content_type=content_type,
                    fallback_strategy=resolved.chunking.strategy_fallback,
                    markdown_chunking=markdown_chunking,
                )
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
                count = len(tokenizer.encode(text, add_special_tokens=False).ids)
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
        "binary_skipped": binary_skipped,
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
