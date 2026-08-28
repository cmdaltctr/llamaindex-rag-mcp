"""Deterministic generated corpus for the ingestion boundedness experiment.

Experiment 6 template (protocol §9): generate plain-text files from a
committed seed and generator version so every cell ingests byte-identical
content.  The generator and per-size manifest JSONs are committed; the
generated corpus directories themselves are transient (protocol §20).

This module is self-contained by design: the experiment directory must not
import from ``experiments/18-*`` (read-only precedent) and must carry its
own generator identity separate from experiment 18's.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path
from typing import Any

GENERATOR_VERSION = "1.0-exp6"
DEFAULT_SEED = 20260806

# Stable word pool (protocol-controlled vocabulary for exp 6).
_WORDS = (
    "boundedness atomicity replacement durability searchable generation "
    "attempt stamp verification stale cleanup semaphore lock scope memory "
    "ceiling node batch parse chunk embed write failure injection recovery "
    "skip unchanged modified corpus identity manifest throughput evidence "
    "gate confirming precedent current code retained narrow mutation"
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
) -> dict[str, Any]:
    """Write ``file_count`` deterministic text files and a manifest.

    Returns the manifest dict (also written to ``out_dir/manifest.json``).
    ``corpus_identity`` is the SHA-256 over the per-file SHA-256 list, so any
    byte change in any file changes the identity.
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
    manifest: dict[str, Any] = {
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
