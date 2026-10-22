"""Extract both rescue tiers, with OCR disabled, from the frozen source corpus."""

from __future__ import annotations

import argparse
from importlib.metadata import version
from pathlib import Path
from typing import Any

from experiment_io import (
    OUTPUT,
    approved_plan,
    atomic_json,
    read_json,
    resume_payload,
    sha256,
    text_sha256,
    verify_freeze,
)

from omrg.core.ingestion.normalise import NORMALISER_VERSION, normalise_reader_text
from omrg.integrations.pdf.liteparse import LiteParseReader
from omrg.integrations.pdf.pypdf import PyPDFReader


def page_texts(documents: list[Any], tier: str, count: int) -> list[str]:
    """Map adapter documents to physical pages, retaining empty LiteParse pages."""
    if tier not in {"liteparse", "pypdf"}:
        raise ValueError("unknown rescue tier")
    if tier == "pypdf" and len(documents) != count:
        raise ValueError("pypdf page count differs from frozen source")
    texts = [""] * count
    seen = set()
    for index, document in enumerate(documents, start=1):
        page = document.metadata["page"] if tier == "liteparse" else index
        if not isinstance(page, int) or not 1 <= page <= count or page in seen:
            raise ValueError("adapter returned an invalid or duplicate physical page")
        seen.add(page)
        texts[page - 1] = normalise_reader_text(document.text)
    return texts


def extraction_identity(source: Path) -> dict:
    """Bind resume to the frozen files, references, readers and normaliser."""
    import omrg.core.ingestion.normalise as normaliser
    import omrg.integrations.pdf.liteparse as liteparse_adapter
    import omrg.integrations.pdf.pypdf as pypdf_adapter

    files = [
        source / "output" / "frozen.manifest.json",
        source / "sources.json",
        source / "labels.json",
        source / "output" / "page_evidence.json",
        source / "build_labels.py",
    ]
    references = sorted(
        path
        for folder in (".transcripts", ".transcripts_split")
        for path in (source / "output" / folder).glob("*/*.json")
    )
    return {
        "source_files": {str(p.relative_to(source)): sha256(p) for p in files},
        "references": {str(p.relative_to(source)): sha256(p) for p in references},
        "reader_versions": {name: version(name) for name in ("liteparse", "pypdf")},
        "adapter_sha256": {
            name: sha256(Path(module.__file__))
            for name, module in (
                ("liteparse", liteparse_adapter),
                ("pypdf", pypdf_adapter),
                ("normaliser", normaliser),
            )
        },
        "normaliser_version": NORMALISER_VERSION,
        "runner_sha256": sha256(Path(__file__)),
    }


def validate_checkpoint(payload: dict) -> None:
    """Verify saved text bytes before trusting a completed document."""
    for doc_id in payload["completed_documents"]:
        rows = [r for r in payload["rows"] if r["doc_id"] == doc_id]
        for tier in ("liteparse", "pypdf"):
            texts = read_json(OUTPUT / ".rescue_text" / doc_id / f"{tier}.json")
            tier_rows = [r for r in rows if r["tier"] == tier]
            if len(tier_rows) != len(texts) or any(
                r["text_sha256"] != text_sha256(texts[r["page"] - 1]) for r in tier_rows
            ):
                raise ValueError(f"saved text checkpoint changed: {doc_id} {tier}")


def run(source: Path, resume: bool) -> None:
    """Extract and checkpoint each complete document under experiment output."""
    plan = approved_plan()
    verify_freeze(source)
    documents = [
        d for d in read_json(source / "sources.json")["documents"] if d["stratum"] != "synthetic"
    ]
    if (
        len(documents) != plan["source_data"]["documents"]
        or sum(d["page_count"] for d in documents) != plan["source_data"]["pages"]
    ):
        raise ValueError("frozen corpus size differs from the registered plan")
    identity = extraction_identity(source)
    target = OUTPUT / "rescue_text.json"
    payload = resume_payload(target, identity, resume)
    validate_checkpoint(payload)
    readers = {"liteparse": LiteParseReader(ocr_enabled=False), "pypdf": PyPDFReader()}
    for document in documents:
        doc_id = document["doc_id"]
        if doc_id in payload["completed_documents"]:
            print(f"[resume] {doc_id}", flush=True)
            continue
        rows = []
        for tier, reader in readers.items():
            texts = page_texts(
                reader.load_data(source / document["local_path"]), tier, document["page_count"]
            )
            atomic_json(OUTPUT / ".rescue_text" / doc_id / f"{tier}.json", texts)
            rows.extend(
                {
                    "doc_id": doc_id,
                    "page": page,
                    "tier": tier,
                    "text_sha256": text_sha256(text),
                    "reader_version": identity["reader_versions"][tier],
                    "normaliser_version": NORMALISER_VERSION,
                }
                for page, text in enumerate(texts, start=1)
            )
        payload["rows"].extend(rows)
        payload["completed_documents"].append(doc_id)
        atomic_json(target, payload)
        print(f"[extract] {doc_id}: {document['page_count']} pages in each tier", flush=True)
    if len(payload["rows"]) != 2 * plan["source_data"]["pages"]:
        raise ValueError("extraction row count differs from the registered plan")
    print(f"[extract] complete: {len(payload['rows'])} rows", flush=True)


def main() -> None:
    """Read runtime source arguments without changing production settings."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-exp", required=True, type=Path)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    run(args.source_exp.resolve(), args.resume)


if __name__ == "__main__":
    main()
