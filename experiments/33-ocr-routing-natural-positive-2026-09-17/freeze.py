"""Experiment 33 freeze manifest (task 2.9).

Records SHA-256 digests of every frozen input: the protocol, the plan, the
development exclusions, the corpus sources, the labels, the operator spot
check, and every natural document, into ``output/frozen.manifest.json``.

    uv run python freeze.py            # write the freeze
    uv run python freeze.py --check    # verify it (exit 1 on drift)

A digest mismatch is a hard stop: the frozen inputs changed after the freeze,
so every measured number would describe a different experiment.
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
    "protocol": "protocol.md",
    "plan": "plan.json",
    "dev_exclusions": "dev_exclusions.json",
    "sources": "sources.json",
    "labels": "labels.json",
    "spot_check": "spot_check.json",
}


def sha256_file(path: Path) -> str:
    """Return the hex SHA-256 digest of *path*, read in 1 MiB blocks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def natural_documents() -> list[dict]:
    """Return the natural (held-out) documents recorded in ``sources.json``."""
    sources = json.loads((EXP_DIR / "sources.json").read_text(encoding="utf-8"))
    return [d for d in sources["documents"] if d["stratum"] != "synthetic"]


def build() -> dict:
    """Compute the current freeze manifest from files and document bytes."""
    files = {
        label: {"path": rel, "sha256": sha256_file(EXP_DIR / rel)}
        for label, rel in FROZEN_FILES.items()
    }
    documents = {}
    for doc in natural_documents():
        path = EXP_DIR / doc["local_path"]
        documents[doc["doc_id"]] = sha256_file(path) if path.is_file() else "MISSING"
    return {
        "experiment": EXP_DIR.name,
        "frozen_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "files": files,
        "documents": documents,
    }


def check() -> list[str]:
    """Return every drift between the recorded freeze and the current state."""
    if not FROZEN.is_file():
        return ["frozen manifest missing; run freeze.py first"]
    recorded = json.loads(FROZEN.read_text(encoding="utf-8"))
    current = build()
    mismatches: list[str] = []
    for key in ("files", "documents"):
        added = sorted(set(current[key]) - set(recorded[key]))
        removed = sorted(set(recorded[key]) - set(current[key]))
        if added:
            mismatches.append(f"{key} added since freeze: {added}")
        if removed:
            mismatches.append(f"{key} removed since freeze: {removed}")
    for label, entry in recorded["files"].items():
        now = current["files"].get(label)
        if now is not None and now["sha256"] != entry["sha256"]:
            mismatches.append(f"file {label} ({entry['path']})")
    for doc_id, digest in recorded["documents"].items():
        now = current["documents"].get(doc_id)
        if now is not None and now != digest:
            mismatches.append(f"document {doc_id}")
    return mismatches


def main() -> int:
    """Write or verify the freeze manifest."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify instead of write")
    args = parser.parse_args()

    if args.check:
        mismatches = check()
        if mismatches:
            print("FREEZE VIOLATION — changed since freeze:", file=sys.stderr)
            for item in mismatches:
                print(f"  - {item}", file=sys.stderr)
            return 1
        print("freeze verified")
        return 0

    labels = json.loads((EXP_DIR / "labels.json").read_text(encoding="utf-8"))
    if not labels.get("frozen"):
        print("labels.json is not marked frozen; finish the spot check first", file=sys.stderr)
        return 1
    manifest = build()
    missing = [doc_id for doc_id, digest in manifest["documents"].items() if digest == "MISSING"]
    if missing:
        print(f"documents missing on disk: {missing}", file=sys.stderr)
        return 1
    FROZEN.parent.mkdir(exist_ok=True)
    tmp = FROZEN.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    tmp.replace(FROZEN)
    print(f"frozen: {len(manifest['files'])} files, {len(manifest['documents'])} documents")
    return 0


if __name__ == "__main__":
    sys.exit(main())
