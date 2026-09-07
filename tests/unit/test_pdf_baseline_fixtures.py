"""Stage 1 baseline assertions for the PDF path (tasks 1.1 and 1.2).

These tests RECORD the current pdf-inspector baseline — classification
fields, emitted markdown, and the degraded behaviour when OCR may be
required — on the committed calibration/evaluation fixture sets under
``tests/fixtures/pdf_baseline/``. They are the reference point the stage 2
routing seam diffs against; they deliberately pin observed behaviour, not
idealised requirements:

- ``pages_needing_ocr`` is logged by the adapter but NOT stored in
  metadata (the gap task 2.10 closes).
- The mixed fixture's blank second page is not flagged by the classifier
  and its absence from the markdown is silent.
- Two-column text flattens into one paragraph with interleaved reading
  order, yet still classifies ``text_based`` at confidence 1.00 (task
  2.5: layout complexity alone must not select OCR).

No test writes files or touches the network; ``pdf-inspector`` is a base
dependency (ADR-050) and runs fully locally.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

pdf_inspector = pytest.importorskip(
    "pdf_inspector", reason="pdf-inspector is a base dependency (ADR-050)"
)

PDF_BASELINE_DIR = Path(__file__).parent.parent / "fixtures" / "pdf_baseline"
PDF_MAGIC = b"%PDF-"


def _load_manifest() -> dict:
    return json.loads((PDF_BASELINE_DIR / "manifest.json").read_text(encoding="utf-8"))


def _set_files(manifest: dict, set_name: str) -> set[str]:
    return set(manifest["sets"][set_name]["files"])


# ---------------------------------------------------------------------------
# Task 1.1 — calibration/evaluation split is recorded, on disk, and disjoint
# ---------------------------------------------------------------------------


def test_manifest_matches_disk_and_sets_are_disjoint() -> None:
    """Every manifest file exists on disk and no unlisted PDF leaks in.

    This is the executable record of task 1.1: the committed manifest is
    the source of truth for which fixture belongs to which set, and the
    two sets never share a file.
    """
    manifest = _load_manifest()
    calibration = _set_files(manifest, "calibration")
    evaluation = _set_files(manifest, "evaluation")

    assert calibration and evaluation
    assert calibration.isdisjoint(evaluation), "calibration and evaluation must be disjoint"

    for set_name in ("calibration", "evaluation"):
        listed = _set_files(manifest, set_name)
        on_disk = {
            str(p.relative_to(PDF_BASELINE_DIR))
            for p in (PDF_BASELINE_DIR / set_name).glob("*.pdf")
        }
        assert on_disk == listed, f"{set_name}: manifest and disk disagree"

        for rel in listed:
            data = (PDF_BASELINE_DIR / rel).read_bytes()
            assert data.startswith(PDF_MAGIC), rel


def test_fixture_sets_stay_compact() -> None:
    """Fixtures stay small enough to commit: every PDF is under 4 KiB."""
    for pdf in PDF_BASELINE_DIR.rglob("*.pdf"):
        assert pdf.stat().st_size < 4096, f"{pdf.name} exceeds the compactness budget"


def test_readme_documents_sets_and_licence() -> None:
    """The README records the calibration/evaluation split and licence safety."""
    readme = (PDF_BASELINE_DIR / "README.md").read_text(encoding="utf-8")
    assert "calibration" in readme and "evaluation" in readme
    assert "disjoint" in readme
    assert "self-authored" in readme


# ---------------------------------------------------------------------------
# Task 1.2 — pdf-inspector output baseline, pinned against the manifest
# ---------------------------------------------------------------------------


def test_observed_classifier_baseline_matches_manifest() -> None:
    """process_pdf output on every fixture matches the recorded baseline.

    The manifest records pdf_type, confidence, page_count, and
    pages_needing_ocr as observed on 2026-09-06 with the locked
    pdf-inspector version. A diff here is a visible baseline change.
    """
    manifest = _load_manifest()
    recorded = manifest["observed_baseline"]["files"]

    for rel, expected in sorted(recorded.items()):
        result = pdf_inspector.process_pdf(str(PDF_BASELINE_DIR / rel))
        assert result.pdf_type == expected["pdf_type"], rel
        assert result.confidence == pytest.approx(expected["confidence"]), rel
        assert result.page_count == expected["page_count"], rel
        assert list(result.pages_needing_ocr or []) == expected["pages_needing_ocr"], rel
        # The library returns markdown=None for pages with no text layer;
        # the adapter normalises that to the empty string.
        markdown = result.markdown
        assert markdown is None or isinstance(markdown, str), rel
        if expected["pages_needing_ocr"]:
            assert not markdown, rel
        assert 0.0 <= result.confidence <= 1.0, rel


def test_baseline_degraded_behaviour_pinned() -> None:
    """Pin the recorded degraded behaviours on the evaluation fixtures.

    - Two-column text: reading order interleaves and whitespace is lost,
      yet the classification stays text_based at 1.00.
    - Image-only page: reports ``scanned`` (no distinct image_based
      observation in this build).
    - Mixed document: the blank second page is NOT flagged
      (``pages_needing_ocr == []``) and the markdown silently carries only
      page one. This is the current gap the stage 2 routing seam fixes.
    """
    two_col = pdf_inspector.process_pdf(str(PDF_BASELINE_DIR / "evaluation/eval_two_column.pdf"))
    md = two_col.markdown
    assert two_col.pdf_type == "text_based"
    assert "Left column heading Right column heading" in md, (
        "columns are expected to interleave line-by-line in the baseline"
    )
    assert "corpus.must" in md, "the whitespace-losing join is part of the recorded baseline"

    image = pdf_inspector.process_pdf(str(PDF_BASELINE_DIR / "evaluation/eval_image.pdf"))
    assert image.pdf_type == "scanned", "image-only page reports scanned in this build"
    assert not image.markdown, "no text layer: markdown is None in this build"

    mixed = pdf_inspector.process_pdf(str(PDF_BASELINE_DIR / "evaluation/eval_mixed.pdf"))
    assert mixed.page_count == 2
    assert mixed.pages_needing_ocr in (None, []), (
        "baseline gap: the blank second page is not flagged as needing OCR"
    )
    assert "MIXED-PAGE-ONE" in mixed.markdown


def test_adapter_metadata_contract_on_text_pdf(fixtures_dir, caplog) -> None:
    """The adapter maps exactly the current seven metadata keys on a text PDF."""
    from omrg.integrations.pdf.pdf_inspector import PdfInspectorReader

    pdf = fixtures_dir / "pdf_baseline" / "evaluation" / "eval_clean_text.pdf"
    with caplog.at_level(logging.INFO, logger="omrg.integrations.pdf.pdf_inspector"):
        docs = PdfInspectorReader().load_data(file=pdf)

    assert len(docs) == 1
    doc = docs[0]
    assert set(doc.metadata) == {
        "pdf_reader",
        "pdf_type",
        "pdf_confidence",
        "page_count",
        "pages_needing_ocr",
        "file_path",
        "file_name",
    }
    assert doc.metadata["pdf_reader"] == "pdf_inspector"
    assert doc.metadata["pdf_type"] == "text_based"
    assert doc.metadata["pdf_confidence"] == pytest.approx(1.0)
    assert doc.metadata["page_count"] == 1
    assert "## Evaluation Clean Text Fixture" in doc.get_content()
    assert "OMRG-EV-0042" in doc.get_content()
    assert "may need OCR" not in caplog.text, (
        "text_based documents must not log the degraded warning"
    )


def test_adapter_degraded_ocr_path_pinned(fixtures_dir, caplog) -> None:
    """Scanned fixture: document still emitted, empty markdown, logged warning.

    Records the degraded path end to end after task 2.10: the adapter
    returns a Document even when the markdown is empty, keeps the
    classification in metadata, logs the "may need OCR" info line, and
    stores ``pages_needing_ocr`` as the SCALAR COUNT (never the
    library's page list — vector-store metadata values are scalars).
    """
    from omrg.integrations.pdf.pdf_inspector import PdfInspectorReader

    pdf = fixtures_dir / "pdf_baseline" / "calibration" / "cal_scanned.pdf"
    with caplog.at_level(logging.INFO, logger="omrg.integrations.pdf.pdf_inspector"):
        docs = PdfInspectorReader().load_data(file=pdf)

    assert len(docs) == 1
    doc = docs[0]
    assert doc.get_content() == "", "the baseline emits the (empty) markdown as-is"
    assert doc.metadata["pdf_type"] == "scanned"
    assert doc.metadata["pdf_confidence"] == pytest.approx(0.9)
    assert doc.metadata["page_count"] == 1

    assert "may need OCR" in caplog.text
    assert "cal_scanned.pdf" in caplog.text

    assert doc.metadata["pages_needing_ocr"] == 1, (
        "task 2.10: the adapter stores the scalar count, not the page list"
    )
    assert not isinstance(doc.metadata["pages_needing_ocr"], list)

    library_result = pdf_inspector.process_pdf(str(pdf))
    assert list(library_result.pages_needing_ocr or []) == [1], (
        "the library still reports the page list; only the adapter reduces it"
    )
