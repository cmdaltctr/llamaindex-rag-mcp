"""Experiment 31 freeze manifest (task 2.6).

Records SHA-256 digests of every frozen input — corpus documents (via the
verified corpus manifest), queries/qrels, cells.json, matching.py, and
protocol.md — into ``output/frozen.manifest.json``.

Downstream steps verify the freeze before running:

    uv run python freeze.py --check

A digest mismatch is a hard stop: the frozen inputs changed after the
freeze and every measured number would describe a different experiment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent
FROZEN = EXP_DIR / "output" / "frozen.manifest.json"

#: Frozen artefacts inside the experiment directory (label -> relative path).
FROZEN_FILES = {
    "cells": "cells.json",
    "matching_rule": "matching.py",
    "protocol": "protocol.md",
    "qrels": "queries/qrels.json",
    "corpus_manifest": "corpus_manifest.json",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _build() -> dict:
    corpus = json.loads((EXP_DIR / "corpus_manifest.json").read_text(encoding="utf-8"))
    files = {
        label: {"path": rel, "sha256": _sha256(EXP_DIR / rel)}
        for label, rel in FROZEN_FILES.items()
    }
    return {
        "experiment": "31-reader-rescue-retrieval-impact-2026-09-15",
        "frozen_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "files": files,
        "documents": {d["doc_id"]: d["sha256"] for d in corpus["documents"]},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify instead of write")
    args = parser.parse_args()

    if not args.check:
        FROZEN.parent.mkdir(exist_ok=True)
        manifest = _build()
        FROZEN.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"frozen: {len(manifest['files'])} files, {len(manifest['documents'])} documents")
        return 0

    if not FROZEN.is_file():
        print("FROZEN MANIFEST MISSING — run freeze.py first", file=sys.stderr)
        return 1
    recorded = json.loads(FROZEN.read_text(encoding="utf-8"))
    current = _build()
    mismatches: list[str] = []
    # Reject label-set drift in both directions: a FROZEN_FILES entry added
    # after the freeze would otherwise pass without a recorded digest, and a
    # removed entry is caught again below with a clearer message.
    added = sorted(set(current["files"]) - set(recorded["files"]))
    removed = sorted(set(recorded["files"]) - set(current["files"]))
    if added:
        mismatches.append(f"file labels added since freeze: {added}")
    if removed:
        mismatches.append(f"file labels removed since freeze: {removed}")
    for label, entry in recorded["files"].items():
        now = current["files"].get(label)
        if now is None or now["sha256"] != entry["sha256"]:
            mismatches.append(f"file {label} ({entry['path']})")
    for doc_id, digest in recorded["documents"].items():
        if current["documents"].get(doc_id) != digest:
            mismatches.append(f"document {doc_id}")
    if mismatches:
        print("FROZE VIOLATION — changed since freeze:", file=sys.stderr)
        for item in mismatches:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print(
        f"freeze verified: {len(recorded['files'])} files,"
        f" {len(recorded['documents'])} documents unchanged"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
