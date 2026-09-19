"""Merging page results into one document (task 4.5, change page-level-ocr-routing).

The ``page`` unit may read one PDF with three engines. The merge decides what
the emitted document says about that: text in page order, four scalar counts
that sum to the page count, and an ``ocr_backend`` that never names a backend
which produced only part of the document.
"""

from __future__ import annotations

import pytest

from omrg.integrations.pdf.page_routing import PageResult, merge_pages


def _result(page: int, text: str, source: str) -> PageResult:
    return PageResult(page=page, text=text, source=source)


def test_pages_join_in_page_order_with_a_blank_line():
    """Page order is the file's order, never the order the tiers finished in."""
    merged = merge_pages(
        [_result(2, "second", "local"), _result(1, "first", "native")], page_count=2
    )

    assert merged.text == "first\n\nsecond"


def test_counts_sum_to_page_count():
    """Every page is accounted for exactly once."""
    merged = merge_pages(
        [
            _result(1, "a", "native"),
            _result(2, "b", "local"),
            _result(3, "c", "worker"),
            _result(4, "", "unresolved"),
        ],
        page_count=4,
    )

    counts = merged.counts
    assert counts["ocr_pages_native"] == 1
    assert counts["ocr_pages_local"] == 1
    assert counts["ocr_pages_worker"] == 1
    assert counts["ocr_pages_unresolved"] == 1
    assert sum(counts.values()) == 4


@pytest.mark.parametrize("page_count", [1, 5, 40])
def test_counts_sum_to_page_count_for_any_document(page_count: int):
    """The sum holds whatever the mixture, so no page is lost or double-counted."""
    sources = ("native", "local", "worker", "unresolved")
    pages = [_result(n + 1, "x", sources[n % 4]) for n in range(page_count)]

    merged = merge_pages(pages, page_count=page_count)

    assert sum(merged.counts.values()) == page_count


def test_one_backend_is_named_when_only_one_produced_text():
    """A wholly native document still reports pdf_inspector, as the document unit does."""
    merged = merge_pages([_result(1, "a", "native"), _result(2, "b", "native")], page_count=2)

    assert merged.ocr_backend == "pdf_inspector"
    assert merged.ocr_used is False


def test_worker_only_document_reports_the_worker():
    """A wholly worker-read document reports paddleocr_vl, as the document unit does."""
    merged = merge_pages([_result(1, "a", "worker"), _result(2, "b", "worker")], page_count=2)

    assert merged.ocr_backend == "paddleocr_vl"
    assert merged.ocr_used is True


def test_local_only_ocr_names_the_local_tier():
    """OCR by pdf-inspector's own engine is not the worker and must not claim to be."""
    merged = merge_pages([_result(1, "a", "local"), _result(2, "b", "local")], page_count=2)

    assert merged.ocr_backend == "pdf_inspector_ocr"
    assert merged.ocr_used is True


def test_two_backends_report_mixed():
    """One string cannot name two engines, and naming the higher tier would be false."""
    merged = merge_pages([_result(1, "a", "native"), _result(2, "b", "worker")], page_count=2)

    assert merged.ocr_backend == "mixed"


def test_unresolved_pages_do_not_decide_the_backend():
    """A page no tier could read names no backend."""
    merged = merge_pages([_result(1, "a", "native"), _result(2, "", "unresolved")], page_count=2)

    assert merged.ocr_backend == "pdf_inspector"


def test_unresolved_page_contributes_its_native_text_without_a_marker():
    """No placeholder string: it would enter retrieval text and be retrieved."""
    merged = merge_pages(
        [_result(1, "kept", "unresolved"), _result(2, "b", "native")], page_count=2
    )

    assert merged.text == "kept\n\nb"


def test_empty_pages_do_not_leave_blank_gaps():
    """A page with no text contributes nothing, not an empty paragraph."""
    merged = merge_pages(
        [_result(1, "a", "native"), _result(2, "", "unresolved"), _result(3, "c", "native")],
        page_count=3,
    )

    assert merged.text == "a\n\nc"
