"""Build deterministic misnamed copies of the Experiment 31 corpus.

Copies only: sources are never moved or renamed. Writes a manifest
with sha256 for every produced file, then exits.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

EXP = Path(__file__).resolve().parent
REPO = EXP.parent.parent
E31 = REPO / "experiments/31-reader-rescue-retrieval-impact-2026-09-15/corpus"
WORK = EXP / "output/work"

PDF_SOURCES = sorted(E31.glob("heldout/*.pdf")) + sorted(E31.glob("distractors/*.pdf"))
TEXT_SOURCES = [
    REPO / "src/omrg/compose.py",
    REPO / "src/omrg/core/ingestion/pipeline.py",
    REPO / "src/omrg/integrations/magika.py",
    REPO / "src/omrg/core/codebase/codebase_map.py",
    REPO / "README.md",
    REPO / "AGENTS.md",
    REPO / "docs/guides/architecture.md",
    REPO / "docs/guides/ingestion.md",
    REPO / "experiments/20-citation-faithfulness-2026-09-02/corpus/source-01-aurora.txt",
    REPO / "experiments/20-citation-faithfulness-2026-09-02/corpus/source-02-birch.txt",
    REPO
    / (
        "experiments/19-lancedb-lifecycle-qualification-2026-08-21/"
        "fixtures/corpus_replacement/bravo_harbour.txt"
    ),
]

# Rotated lying extensions for the PDF set: index modulo three.
LYING_PDF_EXTS = [".py", ".md", ".txt"]

EXPECTED_MAGIKA = {
    source.name: (
        "code/python"
        if source.suffix == ".py"
        else "document/markdown"
        if source.suffix == ".md"
        else "document/text"
    )
    for source in TEXT_SOURCES
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def populate(target: Path, source: Path, new_name: str, expected: str) -> dict:
    target.mkdir(parents=True, exist_ok=True)
    copy = target / new_name
    shutil.copyfile(source, copy)
    return {
        "source": str(source.relative_to(REPO)),
        "copy": str(copy.relative_to(REPO)),
        "sha256": sha256(copy),
        "expected_magika_label": expected,
    }


def main() -> None:
    # Regenerate from scratch: leftover copies from an earlier list or
    # naming scheme would otherwise sit outside swap_manifest.json and a
    # later directory scan would count them.
    for name in ("swap_pdf_names", "swap_text_to_pdf"):
        target = WORK / name
        if target.exists():
            shutil.rmtree(target)

    records: dict[str, list[dict]] = {"swap_pdf_names": [], "swap_text_to_pdf": []}

    for index, source in enumerate(PDF_SOURCES):
        lying = LYING_PDF_EXTS[index % len(LYING_PDF_EXTS)]
        record = populate(WORK / "swap_pdf_names", source, f"doc{index:02d}{lying}", "document/pdf")
        records["swap_pdf_names"].append(record)

    for index, source in enumerate(TEXT_SOURCES):
        record = populate(
            WORK / "swap_text_to_pdf", source, f"file{index:02d}.pdf", EXPECTED_MAGIKA[source.name]
        )
        records["swap_text_to_pdf"].append(record)

    manifest = EXP / "output/swap_manifest.json"
    tmp = manifest.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(records, indent=2), encoding="utf-8")
    tmp.replace(manifest)
    print(f"pdf sources: {len(PDF_SOURCES)}, text sources: {len(TEXT_SOURCES)}", flush=True)
    print(f"manifest: {manifest}", flush=True)


if __name__ == "__main__":
    main()
