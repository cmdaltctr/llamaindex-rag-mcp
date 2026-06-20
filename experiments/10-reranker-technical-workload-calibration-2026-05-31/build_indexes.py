"""Build Chroma indexes for Experiment 10 by reusing 9a data.

This script copies the ChromaDB indexes and ground-truth data from Experiment 9a
rather than re-ingesting the corpus from scratch. The corpus, manifest, and
indexes are identical — only the reranker pool sizing differs between cells.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
EXP_9A_DIR = PROJECT_ROOT / "experiments" / "9a-hybrid-retrieval-freshstack-langchain-2026-05-30"


def _copy_if_needed(src: Path, dst: Path, label: str) -> dict[str, Any]:
    """Copy a file if dst does not exist or differs from src."""
    if dst.exists() and src.read_bytes() == dst.read_bytes():
        return {"status": "reused", "path": str(dst)}
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return {"status": "copied", "from": str(src), "to": str(dst)}


def _copy_tree_if_needed(src: Path, dst: Path, label: str) -> dict[str, Any]:
    """Copy a directory tree if dst does not exist."""
    if dst.exists():
        return {"status": "reused", "path": str(dst)}
    shutil.copytree(src, dst)
    return {"status": "copied", "from": str(src), "to": str(dst)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment-dir", type=Path, default=SCRIPT_DIR)
    parser.add_argument("--exp9a-dir", type=Path, default=EXP_9A_DIR)
    parser.add_argument("--force", action="store_true", help="Force re-copy even if files exist")
    args = parser.parse_args()

    exp_dir = args.experiment_dir.resolve()
    exp9a = args.exp9a_dir.resolve()
    output_dir = exp_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Validate 9a data exists
    gt_9a = exp9a / "output" / "ground-truth.json"
    manifest_9a = exp9a / "corpus" / "langchain_manifest.jsonl"
    qrels_9a = exp9a / "freshstack-qrels.json"
    dense_9a = exp9a / "output" / "chroma_dense"
    hybrid_9a = exp9a / "output" / "chroma_hybrid_bm25"

    for required in (gt_9a, manifest_9a, qrels_9a):
        if not required.exists():
            raise SystemExit(f"Missing 9a data: {required}")

    results: dict[str, Any] = {"exp9a_dir": str(exp9a), "artefacts": {}}

    # Copy ground truth and qrels
    gt_dst = output_dir / "ground-truth.json"
    if args.force and gt_dst.exists():
        gt_dst.unlink()
    results["artefacts"]["ground_truth"] = _copy_if_needed(gt_9a, gt_dst, "ground truth")

    qrels_dst = exp_dir / "freshstack-qrels.json"
    if args.force and qrels_dst.exists():
        qrels_dst.unlink()
    results["artefacts"]["qrels"] = _copy_if_needed(qrels_9a, qrels_dst, "qrels")

    # Copy manifest (needed if we ever need to rebuild)
    manifest_dst = exp_dir / "corpus" / "langchain_manifest.jsonl"
    if args.force and manifest_dst.exists():
        manifest_dst.unlink()
    results["artefacts"]["manifest"] = _copy_if_needed(manifest_9a, manifest_dst, "manifest")

    # Copy Chroma indexes
    dense_dst = output_dir / "chroma_dense"
    hybrid_dst = output_dir / "chroma_hybrid_bm25"

    if args.force:
        shutil.rmtree(dense_dst, ignore_errors=True)
        shutil.rmtree(hybrid_dst, ignore_errors=True)

    if dense_9a.exists():
        results["artefacts"]["chroma_dense"] = _copy_tree_if_needed(dense_9a, dense_dst, "dense")
    else:
        results["artefacts"]["chroma_dense"] = {"status": "skipped", "reason": "9a dense index not found"}

    if hybrid_9a.exists():
        results["artefacts"]["chroma_hybrid_bm25"] = _copy_tree_if_needed(hybrid_9a, hybrid_dst, "hybrid")
    else:
        results["artefacts"]["chroma_hybrid_bm25"] = {"status": "skipped", "reason": "9a hybrid index not found"}

    # Validate ground truth corpus size
    with gt_dst.open(encoding="utf-8") as f:
        gt = json.load(f)
    total_docs = gt.get("corpus", {}).get("total_parent_docs", 0)
    if total_docs < 10_000:
        raise SystemExit(f"Corpus validity failed: {total_docs} < 10,000 parent documents")

    results["corpus"] = gt.get("corpus", {})
    (output_dir / "index_build.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
