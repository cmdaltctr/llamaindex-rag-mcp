"""Task 3.4 (part 1): extract both rescue tiers with OCR off and the shipped normaliser.

Reuses Experiment 38 ``extract_rescue_text.page_texts`` (imported, not copied).
Writes gitignored ``output/.rescue_text/<doc_id>/<tier>.json`` and the committed
row file ``output/rescue_text.json`` (hashes and versions only, no page text).

    uv run --no-sync python extract_rescue.py --resume
"""

from __future__ import annotations

import argparse
from importlib.metadata import version
from pathlib import Path

from exp42_io import (
    EXP38,
    EXP_DIR,
    OUTPUT,
    atomic_json,
    load_module,
    plan,
    read_json,
    sha256,
    text_sha256,
)

from omrg.core.ingestion.normalise import NORMALISER_VERSION
from omrg.integrations.pdf.liteparse import LiteParseReader
from omrg.integrations.pdf.pypdf import PyPDFReader

TARGET = OUTPUT / "rescue_text.json"
TIERS = ("liteparse", "pypdf")


def identity() -> dict:
    """Bind resume to the readers, adapters, normaliser and this runner."""
    import omrg.core.ingestion.normalise as normaliser
    import omrg.integrations.pdf.liteparse as liteparse_adapter
    import omrg.integrations.pdf.pypdf as pypdf_adapter

    return {
        "reader_versions": {name: version(name) for name in TIERS},
        "adapter_sha256": {
            name: sha256(Path(module.__file__))
            for name, module in (
                ("liteparse", liteparse_adapter),
                ("pypdf", pypdf_adapter),
                ("normaliser", normaliser),
            )
        },
        "normaliser_version": NORMALISER_VERSION,
        "page_mapper": "experiments/38-rescue-quality-signal-2026-09-30/extract_rescue_text.py",
        "page_mapper_sha256": sha256(EXP38 / "extract_rescue_text.py"),
        "runner_sha256": sha256(Path(__file__)),
    }


def main() -> None:
    """Extract every document in sources.json order."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    plan()
    mapper = load_module(EXP38 / "extract_rescue_text.py", "exp38_extract_rescue_text")
    ident = identity()
    if TARGET.exists():
        if not args.resume:
            raise SystemExit("rescue_text.json exists: pass --resume")
        payload = read_json(TARGET)
        if payload["identity"] != ident:
            raise SystemExit("extraction identity changed: resume refused")
    else:
        payload = {"identity": ident, "completed_documents": [], "rows": []}
    readers = {"liteparse": LiteParseReader(ocr_enabled=False), "pypdf": PyPDFReader()}
    for doc in read_json(EXP_DIR / "sources.json")["documents"]:
        doc_id = doc["doc_id"]
        if doc_id in payload["completed_documents"]:
            continue
        rows = []
        for tier, reader in readers.items():
            try:
                texts = mapper.page_texts(
                    reader.load_data(EXP_DIR / doc["local_path"]), tier, doc["page_count"]
                )
                error = None
            except Exception as exc:  # noqa: BLE001 - a reader failure is a recorded outcome
                texts, error = [""] * doc["page_count"], f"{type(exc).__name__}"
            atomic_json(OUTPUT / ".rescue_text" / doc_id / f"{tier}.json", texts)
            rows += [
                {
                    "doc_id": doc_id,
                    "page": page,
                    "tier": tier,
                    "text_sha256": text_sha256(text),
                    "reader_version": ident["reader_versions"][tier],
                    "normaliser_version": NORMALISER_VERSION,
                    "reader_error": error,
                }
                for page, text in enumerate(texts, start=1)
            ]
        payload["rows"] += rows
        payload["completed_documents"].append(doc_id)
        atomic_json(TARGET, payload)
        print(f"[extract] {doc_id}: {doc['page_count']} pages per tier", flush=True)


if __name__ == "__main__":
    main()
