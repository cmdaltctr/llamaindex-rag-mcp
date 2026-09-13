"""Build the approved collection for experiment 29 (change task 2.2).

Reads an operator-approved path list and writes the immutable private
digest-to-ID mapping. Discovery in ``classify.py`` processes exactly this
list — nothing is scanned.

Usage:

    uv run python experiments/29-pdf-routing-repeat-2026-09-13/prepare_collection.py \
        --development /abs/path/one.pdf /abs/path/two.pdf \
        --held-out /abs/path/three.pdf /abs/path/four.pdf

Outputs (all gitignored):

- ``output/.collection.private.json`` — doc_id, path, sha256, split
- ``output/.local_manifest.json`` — doc_id to path, for labelling

The mapping is written once. Re-running with different paths refuses
unless ``--force`` is given, and ``--force`` is recorded so a rebuilt
collection cannot masquerade as the approved one.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent
OUT_DIR = EXP_DIR / "output"
PRIVATE_COLLECTION = OUT_DIR / ".collection.private.json"
LOCAL_MANIFEST = OUT_DIR / ".local_manifest.json"


def _entry(doc_id: str, path: Path, split: str) -> dict:
    if path.suffix.lower() != ".pdf":
        raise SystemExit(f"not a PDF: {path}")
    if not path.is_file():
        raise SystemExit(f"approved path does not exist: {path}")
    return {
        "doc_id": doc_id,
        "path": str(path.resolve()),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "split": split,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--development", nargs="*", default=[], metavar="PDF")
    parser.add_argument("--held-out", nargs="*", default=[], metavar="PDF")
    parser.add_argument(
        "--force",
        action="store_true",
        help="rebuild the mapping; recorded in the file as a re-approval event",
    )
    args = parser.parse_args()

    if not args.development and not args.held_out:
        raise SystemExit("no approved paths supplied")

    documents: list[dict] = []
    for index, raw in enumerate(args.development, start=1):
        documents.append(_entry(f"dev_{index:03d}", Path(raw), "development"))
    for index, raw in enumerate(args.held_out, start=1):
        documents.append(_entry(f"hold_{index:03d}", Path(raw), "held_out"))

    digests = [d["sha256"] for d in documents]
    if len(set(digests)) != len(digests):
        raise SystemExit("duplicate content digests in the approved list")

    payload = {
        "created_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "rebuilt": False,
        "documents": documents,
    }

    if PRIVATE_COLLECTION.exists():
        existing = json.loads(PRIVATE_COLLECTION.read_text(encoding="utf-8"))
        if not args.force:
            same = existing.get("documents") == documents
            message = (
                "collection already exists and is identical"
                if same
                else "collection exists and differs; re-approve and pass --force"
            )
            raise SystemExit(f"{PRIVATE_COLLECTION.name}: {message}")
        payload["rebuilt"] = True
        print("[prepare] WARNING: rebuilding an existing collection mapping", file=sys.stderr)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    PRIVATE_COLLECTION.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    LOCAL_MANIFEST.write_text(
        json.dumps({d["doc_id"]: d["path"] for d in documents}, indent=2),
        encoding="utf-8",
    )
    print(
        f"[prepare] {len(documents)} documents "
        f"({len(args.development)} development, {len(args.held_out)} held-out); "
        f"mapping written to {PRIVATE_COLLECTION.name} (gitignored)",
        flush=True,
    )


if __name__ == "__main__":
    main()
