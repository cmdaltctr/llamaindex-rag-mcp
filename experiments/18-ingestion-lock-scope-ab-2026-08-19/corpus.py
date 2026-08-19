"""Deterministic generated corpus for the ingestion lock-scope experiment.

Generates plain-text files from a seeded word pool so every pipeline variant
ingests byte-identical content. No semantic dataset is used (protocol §5).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path

GENERATOR_VERSION = "1.0"
DEFAULT_SEED = 20260819

# Stable word pool (protocol-controlled vocabulary; unrelated to any corpus).
_WORDS = (
    "pipeline vector store replacement attempt durability verify cleanup "
    "generation lock semaphore ingestion bounded node chunk metadata "
    "retrieval embedding provider fallback contract invariant regression "
    "observation measurement throughput latency memory ceiling baseline "
    "candidate evidence gate calibration audit fixture deterministic seed"
).split()


def _paragraph(rng: random.Random) -> str:
    """Build one paragraph of roughly 60-90 words."""
    count = rng.randint(60, 90)
    words = [rng.choice(_WORDS) for _ in range(count)]
    return " ".join(words).capitalize() + "."


def _file_text(rng: random.Random, target_chars: int) -> str:
    """Build deterministic file body near ``target_chars`` characters."""
    parts: list[str] = []
    total = 0
    while total < target_chars:
        para = _paragraph(rng)
        parts.append(para)
        total += len(para) + 1
    return "\n\n".join(parts)


def _make_rng(seed: int, index: int) -> random.Random:
    """Return the per-file generator (deterministic corpus, not crypto)."""
    return random.Random(seed * 1_000_003 + index)  # noqa: S311


def generate_corpus(
    out_dir: Path,
    *,
    file_count: int,
    seed: int = DEFAULT_SEED,
    target_chars: int = 6000,
) -> dict:
    """Write ``file_count`` deterministic text files and a manifest.

    Returns the manifest dict (also written to ``out_dir/manifest.json``).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    hashes: list[str] = []
    records = []
    for index in range(file_count):
        rng = _make_rng(seed, index)
        text = _file_text(rng, target_chars)
        name = f"source_{index:04d}.txt"
        path = out_dir / name
        path.write_text(text, encoding="utf-8")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        hashes.append(digest)
        records.append({"file": name, "sha256": digest, "bytes": len(text.encode())})
    corpus_identity = hashlib.sha256("\n".join(hashes).encode("utf-8")).hexdigest()
    manifest = {
        "generator_version": GENERATOR_VERSION,
        "seed": seed,
        "file_count": file_count,
        "target_chars_per_file": target_chars,
        "total_bytes": sum(r["bytes"] for r in records),
        "corpus_identity": corpus_identity,
        "files": records,
    }
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    """CLI entry point for standalone corpus generation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--files", required=True, type=int)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--target-chars", type=int, default=6000)
    args = parser.parse_args()
    manifest = generate_corpus(
        args.out,
        file_count=args.files,
        seed=args.seed,
        target_chars=args.target_chars,
    )
    print(
        f"corpus: {manifest['file_count']} files, "
        f"{manifest['total_bytes']} bytes, identity {manifest['corpus_identity'][:12]}",
        flush=True,
    )


if __name__ == "__main__":
    main()
