"""pdf-inspector adapter — Rust PDF classification and markdown extraction.

pdf-inspector (Firecrawl, MIT) classifies a PDF as text-based, scanned,
image-based, or mixed in milliseconds, then extracts position-aware text
and converts it to structured markdown — multi-column reading order,
headings, lists, and tables — without OCR or ML models. Strong on the
two-column academic layouts the Qasper corpus (Experiment 14) is built
from.

Base dependency and the configured default reader (ADR-050); the
import stays lazy inside ``load_data`` per the ADR-024 pattern shared
by the integrations.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: pdf-inspector's default detection samples at most this many evenly
#: spread pages (``ScanStrategy::Sample(8)``); the Python binding exposes
#: no scan-strategy option. A ``text_based`` result on a longer PDF can
#: therefore miss image-only pages outside the sample (TDR-026).
PDF_INSPECTOR_SAMPLED_PAGES = 8


class PdfInspectorReader:
    """Adapter wrapping pdf-inspector for whole-document markdown extraction.

    Produces a single ``Document`` per file carrying the extracted
    markdown plus classification diagnostics (``pdf_type``,
    ``confidence``, ``page_count``) so downstream consumers can route on
    them (e.g. scanned PDFs to an OCR path).
    """

    def load_data(self, file: Path, *args: Any, **kwargs: Any) -> list:
        """Parse a PDF into markdown via pdf-inspector.

        Args:
            file: Path to the PDF file.

        Returns:
            List with one LlamaIndex ``Document`` whose text is the
            extracted markdown. When pdf-inspector classifies the file
            ``text_based`` yet extracts nothing from a non-empty page
            count, the document text is the fallback chain's joined
            pages instead — liteparse first, pypdf last (ADR-066); empty
            markdown still yields a document with empty text so callers
            observe the classification.

        Raises:
            ImportError: If ``pdf_inspector`` is not installed.
            Exception: Whatever the final pypdf tier raises — a file that
                opens in pdf-inspector but crashes pypdf is genuinely
                broken input for the per-file error boundary.
        """
        try:
            import pdf_inspector
        except ImportError as exc:
            raise ImportError("pdf_inspector is not installed. Install with: uv sync") from exc

        from llama_index.core import Document

        result = pdf_inspector.process_pdf(str(file))
        markdown = result.markdown or ""
        # Store-compatible scalar count (task 2.10): vector-store
        # metadata values are scalars in both backends and nothing
        # sanitises them on the way in, so the classifier's page LIST
        # is reduced here to the count the routing gate consumes.
        pages_needing_ocr_count = len(_complete_ocr_pages(pdf_inspector, file, result))

        metadata: dict[str, Any] = {
            "pdf_reader": "pdf_inspector",
            "pdf_type": result.pdf_type,
            "pdf_confidence": result.confidence,
            "page_count": result.page_count,
            "pages_needing_ocr": pages_needing_ocr_count,
            "file_path": str(file),
            "file_name": file.name,
        }

        if result.pdf_type != "text_based":
            logger.info(
                "pdf-inspector classified %s as %s (confidence %.2f, "
                "%d page(s) may need OCR); markdown may be partial",
                file.name,
                result.pdf_type,
                result.confidence,
                pages_needing_ocr_count,
            )

        # Sloman guard (design D6, change pdf-reader-extraction-fallback):
        # a ``text_based`` classification with an empty extraction on a
        # non-empty document is a contradiction — the classifier saw a
        # text layer the extractor failed to read (WinAnsi TrueType
        # without /ToUnicode; IA GlyphLessFont; TDR-024). Retry through
        # the tiered fallback chain — liteparse first (extraction-only,
        # fastest rescue), pypdf last (always available) — before
        # emitting zero characters (ADR-066; unqualified design numbers
        # below are D1–D5 of change tiered-reader-fallback-chain).
        if result.pdf_type == "text_based" and markdown == "" and result.page_count > 0:
            from .registry import get as get_reader

            recovered = ""
            fallback_backend: str | None = None
            # Tier 1 — liteparse, constructed extraction-only (design
            # D2: an operator enabling liteparse OCR must not turn the
            # fallback chain into an OCR path); any failure hands over
            # to pypdf (D3).
            try:
                candidate = "\n\n".join(
                    doc.text
                    for doc in get_reader("liteparse")(
                        ocr_enabled=False, num_workers=None
                    ).load_data(file)
                    if doc.text and doc.text.strip()
                )
                if candidate:
                    recovered = candidate
                    fallback_backend = "liteparse"
            except Exception:  # noqa: BLE001 - a tier failure must never block the next tier
                logger.debug("liteparse fallback tier failed for %s; handing over", file.name)
            # Tier 2 — pypdf: always available; its exceptions propagate
            # to the per-file error boundary (D3) — a file that opens in
            # pdf-inspector but crashes pypdf is genuinely broken input.
            if fallback_backend is None:
                candidate = "\n\n".join(
                    doc.text
                    for doc in get_reader("pypdf")().load_data(file)
                    if doc.text and doc.text.strip()
                )
                if candidate:
                    recovered = candidate
                    fallback_backend = "pypdf"

            if recovered:
                logger.warning(
                    "pdf-inspector extracted no text from %s despite a "
                    "text_based classification (%d page(s) flagged); "
                    "recovered %d characters via %s",
                    file.name,
                    pages_needing_ocr_count,
                    len(recovered),
                    fallback_backend,
                )
                markdown = recovered
                # Evidence correction, not replacement (D4, change
                # pdf-reader-extraction-fallback): the pages were
                # flagged only by the failed extraction, so the scalar
                # the OCR gate reads drops to zero while the original
                # count survives under a diagnostic key.
                metadata["pages_needing_ocr"] = 0
                metadata["pages_needing_ocr_before_fallback"] = pages_needing_ocr_count
                metadata["extraction_fallback_backend"] = fallback_backend
            else:
                logger.warning(
                    "pdf-inspector extracted no text from %s despite a "
                    "text_based classification, and both fallback tiers "
                    "recovered nothing — emitting the flagged "
                    "evidence unchanged for OCR routing",
                    file.name,
                )

        return [Document(text=markdown, metadata=metadata)]


def _complete_ocr_pages(pdf_inspector: Any, file: Path, result: Any) -> list:
    """Return OCR-needing pages, completing a sampled ``text_based`` result.

    Only a ``text_based`` result on a PDF longer than the detection sample
    can be incomplete: a flagged sample page already makes pdf-inspector
    scan every page, and ``scanned``/``image_based`` PDFs route regardless
    (change full-page-ocr-evidence). Classification, confidence and the
    extracted Markdown stay the library's.

    Args:
        pdf_inspector: The imported ``pdf_inspector`` module.
        file: Path to the PDF file.
        result: The ``process_pdf`` result.

    Returns:
        The page list the routing evidence is counted from; the sampled
        list when no full scan is needed or the full scan fails.
    """
    sampled = list(result.pages_needing_ocr or [])
    if result.pdf_type != "text_based" or result.page_count <= PDF_INSPECTOR_SAMPLED_PAGES:
        return sampled
    try:
        complete = list(pdf_inspector.extract_pages_markdown(str(file)).pages_needing_ocr or [])
    except Exception as exc:  # noqa: BLE001 - evidence completion must never fail the read
        logger.warning(
            "pdf-inspector full page scan failed for %s (%s); keeping the sampled OCR "
            "evidence (%d page(s))",
            file.name,
            type(exc).__name__,
            len(sampled),
        )
        return sampled
    if len(complete) > len(sampled):
        logger.info(
            "pdf-inspector full page scan of %s found %d page(s) needing OCR; the "
            "%d-page detection sample found %d",
            file.name,
            len(complete),
            PDF_INSPECTOR_SAMPLED_PAGES,
            len(sampled),
        )
    return complete
