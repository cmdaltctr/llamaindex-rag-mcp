"""Experiment 31 corpus preparation (tasks 2.1-2.4, 2.6).

Verifies every corpus file against the SHA-256 digests recorded at sourcing
time (``corpus/SOURCING.md``) and writes:

- ``output/.collection.private.json`` — doc_id, LOCAL path, sha256, split,
  role. Gitignored. The only artefact carrying private paths.
- ``corpus_manifest.json`` (experiment root, committed) — doc_id, sha256,
  split, failure type, page count. No paths, no text.

Development documents arrive as operator-approved path arguments (the
Experiment 30 pathological/control set, local Zotero storage) so no private
path is ever embedded in a committed file (task 4.5).

Usage:
    uv run python prepare_corpus.py --development p01=/abs/p1.pdf p02=/abs/p2.pdf ...
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent
CORPUS = EXP_DIR / "corpus"
OUT_DIR = EXP_DIR / "output"
PRIVATE = OUT_DIR / ".collection.private.json"
PUBLIC_MANIFEST = EXP_DIR / "corpus_manifest.json"

# Frozen at sourcing time (corpus/SOURCING.md, 2026-09-15). doc_id is
# stable and public; the digest pins the exact bytes.
HELDOUT: list[dict] = [
    {
        "doc_id": "h01",
        "file": "gri_33125011167869.pdf",
        "failure_type": "type_a_glyphlessfont",
        "pages": 282,
        "sha256": "878eea13a353b24780ddf457c406473028c9103533729cbe26f3a706d46b0cfa",
    },
    {
        "doc_id": "h02",
        "file": "frenchinheartam00finlgoog.pdf",
        "failure_type": "type_a_glyphlessfont",
        "pages": 457,
        "sha256": "3d511ba813d2fa224f9eda5e30d502712142d6a5b4e84e1c5972391c5c594fa5",
    },
    {
        "doc_id": "h03",
        "file": "introductiontoe02turngoog.pdf",
        "failure_type": "type_a_glyphlessfont",
        "pages": 668,
        "sha256": "d302ec57e29bd04aa83c631bddd3cb3873d86c58ba2aeb0259a73822e716655d",
    },
    {
        "doc_id": "h04",
        "file": "introductiontohi00jackuoft.pdf",
        "failure_type": "type_a_glyphlessfont",
        "pages": 284,
        "sha256": "ce8441a004a42a74dece008cff977965f87a22891d73813885d2c8990d6181aa",
    },
    {
        "doc_id": "h05",
        "file": "introductiontolo00howarich.pdf",
        "failure_type": "type_a_glyphlessfont",
        "pages": 554,
        "sha256": "bff70e3c22b112f7ed4b1712af8f6e1db60b6bffb7848fdafdac4edcdb5ec2b3",
    },
    {
        "doc_id": "h06",
        "file": "jacobeanletterwr00chamuoft.pdf",
        "failure_type": "type_a_glyphlessfont",
        "pages": 272,
        "sha256": "25faf0665316737f941b001859640480bff83c529f565dc78c1e6a29e33975e3",
    },
    {
        "doc_id": "h07",
        "file": "J90-1001.pdf",
        "failure_type": "type_b_winansi_no_tounicode",
        "pages": 10,
        "sha256": "1c350f0314bf10561a9c00966d26998fcd403da933f9bba9d8075ba84bd66a28",
    },
    {
        "doc_id": "h08",
        "file": "P89-1001.pdf",
        "failure_type": "type_b_winansi_no_tounicode",
        "pages": 6,
        "sha256": "657a65bd7f58389098f233707b934247f1e5dfea29deb29e230d024d301837ab",
    },
]

DISTRACTORS: list[dict] = [
    {
        "doc_id": "d01",
        "file": "1312613f-e01a-499a-b0d0-7289d5b9013d.pdf",
        "pages": 504,
        "sha256": "15937a212278a97c9b29997af61dc69ee74c70d4fed2e4e3d0d6337ba57cffa1",
    },
    {
        "doc_id": "d02",
        "file": "19c8c38c-9262-4f37-891a-18f767dbf61c.pdf",
        "pages": 476,
        "sha256": "3e26debea0ad8cd9b3b46f1e0056c18ada42158103d32e6fb0a7e9f5653aaf8c",
    },
    {
        "doc_id": "d03",
        "file": "2925acef-56cf-4459-9a2f-cbf42625006f.pdf",
        "pages": 254,
        "sha256": "a31f555d54bccbe33ec1099b0c4c0e8b1e042d1c11e4a02401aace3e9520f8c8",
    },
    {
        "doc_id": "d04",
        "file": "2de0dafa-1843-47cc-a55f-0e557fa87cf9.pdf",
        "pages": 228,
        "sha256": "f33f4ae5eb0a2a9d3c89f85f32101b832c8cb7643a0c08333d035b91f30081cf",
    },
    {
        "doc_id": "d05",
        "file": "32e99c61-2352-4a88-bb9a-bd81f113ba1e.pdf",
        "pages": 262,
        "sha256": "3f7d4fdeefa7e6ec28d160057cb196ef86b437692da2e4991c45040b909e7df2",
    },
    {
        "doc_id": "d06",
        "file": "6ed799de-77a5-44fd-80aa-5a9940b3a44c.pdf",
        "pages": 224,
        "sha256": "9d49eb1f9d2de1fadd5ef18ab2fcbf4c4cf4dda90ed3cb636e58b4a1974b0940",
    },
    {
        "doc_id": "d07",
        "file": "BusinessEthics-OP.pdf",
        "pages": 377,
        "sha256": "3a73f4b5941a07b86a468268f1eaa39476455580d8134b779b9aec0361af6401",
    },
    {
        "doc_id": "d08",
        "file": "business-law-i-essentials-draft.pdf",
        "pages": 285,
        "sha256": "a028c7c76e0255e103e06f3255b844bd3612c891db6ab78dd409ab0b829dc795",
    },
    {
        "doc_id": "d09",
        "file": "china-dreams.pdf",
        "pages": 328,
        "sha256": "21cc5ed797ca14a33eeec3ca71b1092abd78a48a11024af4c2c96cd8112d3fd7",
    },
    {
        "doc_id": "d10",
        "file": "e76e054c-617d-4004-b68d-54739205df8d.pdf",
        "pages": 372,
        "sha256": "e26c9ceedd97a31526f2073bad0cfc2e27de43c0778a29f4961cacae6386f3cb",
    },
    {
        "doc_id": "d11",
        "file": "on-the-frontiers-of-history.pdf",
        "pages": 246,
        "sha256": "1260496a4f23a3a0c08abb6049f9e068041e9609b2d58d1e76b30c961e9f5368",
    },
]

# Development/regression registrations (task 2.1) — Experiment 30 ids.
DEVELOPMENT_ROLES = {
    "p01_ia_prince": "development_pathological",
    "p02_ia_managing": "development_pathological",
    "p03_winansi_sloman": "development_pathological",
    "c01_scanned_kerr": "development_control_scanned",
    "c02_healthy_graphrag": "development_control_healthy",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--development",
        nargs="*",
        default=[],
        metavar="ID=PATH",
        help="development registrations as doc_id=/abs/path.pdf pairs",
    )
    args = parser.parse_args()

    dev_entries: list[dict] = []
    seen_ids: set[str] = set()
    for pair in args.development:
        doc_id, _, raw = pair.partition("=")
        if not raw:
            raise SystemExit(f"bad --development entry (want ID=PATH): {pair!r}")
        if doc_id not in DEVELOPMENT_ROLES:
            raise SystemExit(
                f"unknown development doc_id {doc_id!r}; known: {sorted(DEVELOPMENT_ROLES)}"
            )
        if doc_id in seen_ids:
            raise SystemExit(f"duplicate development doc_id {doc_id!r}")
        seen_ids.add(doc_id)
        path = Path(raw).expanduser().resolve()
        if path.suffix.lower() != ".pdf" or not path.is_file():
            raise SystemExit(f"development path is not an existing PDF: {path}")
        dev_entries.append(
            {
                "doc_id": doc_id,
                "path": str(path),
                "sha256": _sha256(path),
                "split": "development",
                "role": DEVELOPMENT_ROLES[doc_id],
            }
        )
    missing = set(DEVELOPMENT_ROLES) - seen_ids
    if missing:
        raise SystemExit(f"missing development registrations: {sorted(missing)}")

    documents: list[dict] = []
    for group, split, folder in (
        (HELDOUT, "heldout", CORPUS / "heldout"),
        (DISTRACTORS, "distractor", CORPUS / "distractors"),
    ):
        for spec in group:
            path = folder / spec["file"]
            if not path.is_file():
                raise SystemExit(f"missing corpus file: {path}")
            digest = _sha256(path)
            if digest != spec["sha256"]:
                raise SystemExit(
                    f"digest mismatch for {spec['doc_id']}: expected {spec['sha256']}, got {digest}"
                )
            entry = {
                "doc_id": spec["doc_id"],
                "path": str(path),
                "sha256": digest,
                "split": split,
            }
            if split == "heldout":
                entry["failure_type"] = spec["failure_type"]
            documents.append(entry)
    documents.extend(dev_entries)

    digests = [d["sha256"] for d in documents]
    if len(set(digests)) != len(digests):
        raise SystemExit("duplicate content digests across corpus groups")

    OUT_DIR.mkdir(exist_ok=True)
    PRIVATE.write_text(
        json.dumps(
            {
                "created_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "documents": documents,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    public = {
        "experiment": "31-reader-rescue-retrieval-impact-2026-09-15",
        "created_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sourcing_record": "corpus/SOURCING.md (local, gitignored)",
        "excluded_partial_extractions_during_sourcing": 1,
        "documents": [
            {
                "doc_id": d["doc_id"],
                "sha256": d["sha256"],
                "split": d["split"],
                **({"failure_type": d["failure_type"]} if "failure_type" in d else {}),
                **({"role": d["role"]} if "role" in d else {}),
            }
            for d in documents
        ],
    }
    PUBLIC_MANIFEST.write_text(json.dumps(public, indent=2), encoding="utf-8")

    counts: dict[str, int] = {}
    for d in documents:
        counts[d["split"]] = counts.get(d["split"], 0) + 1
    print(f"corpus frozen: {counts}")
    print(f"private mapping: {PRIVATE.name} (gitignored)")
    print(f"public manifest: {PUBLIC_MANIFEST.name} (committed, no paths)")
    return None


if __name__ == "__main__":
    sys.exit(main())
