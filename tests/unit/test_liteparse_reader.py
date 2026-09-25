"""Tests for the LiteParse reader adapter.

The settings test uses a stubbed parser and runs in the fast suite. The
real-parser tests are marked ``slow`` because they require the native
PDFium binary.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

CORPUS_PDF = Path(__file__).resolve().parents[2] / (
    "experiments/11-liteparse-pdf-quality-2026-06-20/corpus/vaswani2017_attention.pdf"
)


def test_default_constructor_reads_effective_settings(monkeypatch, tmp_path, effective_settings):
    """Normal LiteParse use still reads both injected parser settings."""
    from omrg.core.settings import set_default_effective_settings
    from omrg.integrations.pdf.liteparse import LiteParseReader

    observed: list[tuple[bool, int | None, bool]] = []

    class _StubLiteParse:
        def __init__(self, *, ocr_enabled: bool, num_workers: int | None, quiet: bool) -> None:
            observed.append((ocr_enabled, num_workers, quiet))

        def parse(self, file):
            item = SimpleNamespace(text="configured parse", x=0, y=0, width=1, height=1)
            page = SimpleNamespace(page_num=1, text_items=[item])
            return SimpleNamespace(pages=[page])

    monkeypatch.setitem(sys.modules, "liteparse", SimpleNamespace(LiteParse=_StubLiteParse))
    set_default_effective_settings(
        effective_settings(liteparse_ocr_enabled=True, liteparse_num_workers=4)
    )

    documents = LiteParseReader().load_data(tmp_path / "configured.pdf")

    assert observed == [(True, 4, True)]
    assert documents[0].get_content() == "configured parse"


@pytest.mark.slow
class TestLiteParseReader:
    """Tests requiring [pdf-liteparse] extra."""

    def test_emits_documents_with_bbox_metadata(self):
        """Successful parse emits Documents with pdf_reader=liteparse and bbox fields."""
        if not CORPUS_PDF.exists():
            pytest.skip("Corpus PDF not available")

        from omrg.integrations.pdf.liteparse import LiteParseReader

        reader = LiteParseReader()
        documents = reader.load_data(file=CORPUS_PDF)

        assert len(documents) > 0
        for doc in documents:
            meta = doc.metadata
            assert meta.get("pdf_reader") == "liteparse"
            assert "page" in meta
            assert meta.get("column") in ("left", "right", "single", "multi_column")
            assert "section_bbox" in meta
            assert meta.get("bbox_schema_version") == 1

    def test_two_column_pdf_produces_column_metadata(self):
        """A two-column academic PDF should be recognised and labelled multi_column."""
        if not CORPUS_PDF.exists():
            pytest.skip("Corpus PDF not available")

        from omrg.integrations.pdf.liteparse import LiteParseReader

        reader = LiteParseReader()
        documents = reader.load_data(file=CORPUS_PDF)

        columns = {doc.metadata.get("column") for doc in documents}
        assert "multi_column" in columns, f"Expected a multi_column page but got: {columns}"

    def test_section_bbox_is_json_string(self):
        """section_bbox must be a JSON-encoded string (ChromaDB scalar requirement)."""
        if not CORPUS_PDF.exists():
            pytest.skip("Corpus PDF not available")

        from omrg.integrations.pdf.liteparse import LiteParseReader

        reader = LiteParseReader()
        documents = reader.load_data(file=CORPUS_PDF)

        for doc in documents:
            bbox_str = doc.metadata.get("section_bbox")
            assert isinstance(bbox_str, str), "section_bbox must be a string"
            bbox = json.loads(bbox_str)
            assert len(bbox) == 4, "section_bbox must have 4 coordinates"


def _item(text: str, x: float, y: float, width: float, height: float = 1.0):
    """Return one LiteParse-shaped text item."""
    return SimpleNamespace(text=text, x=x, y=y, width=width, height=height)


def _two_column_items() -> list[SimpleNamespace]:
    """Return a two-column page: a 6% gutter at the centre, 12 lines a side.

    Emitted in interleaved order, the way LiteParse returns them, so a correct
    join has to reorder.
    """
    items: list[SimpleNamespace] = []
    for row in range(12):
        y = 10.0 + row * 10
        items.append(_item(f"left {row}", x=0.0, y=y, width=44.0))
        items.append(_item(f"right {row}", x=56.0, y=y, width=44.0))
    return items


def _read(monkeypatch, tmp_path, pages):
    """Load documents from a stubbed LiteParse returning *pages*."""
    from omrg.integrations.pdf.liteparse import LiteParseReader

    class _StubLiteParse:
        def __init__(self, **_kwargs) -> None:
            pass

        def parse(self, file):
            return SimpleNamespace(pages=pages)

    monkeypatch.setitem(sys.modules, "liteparse", SimpleNamespace(LiteParse=_StubLiteParse))
    return LiteParseReader(ocr_enabled=False, num_workers=1).load_data(tmp_path / "stub.pdf")


def test_two_column_page_is_joined_column_by_column(monkeypatch, tmp_path):
    """Every left-column line precedes every right-column line."""
    page = SimpleNamespace(page_num=1, text_items=_two_column_items())

    lines = _read(monkeypatch, tmp_path, [page])[0].get_content().splitlines()

    assert lines == [f"left {row}" for row in range(12)] + [f"right {row}" for row in range(12)]


def test_two_column_page_is_labelled_multi_column(monkeypatch, tmp_path):
    """A reordered page says so in its metadata."""
    page = SimpleNamespace(page_num=1, text_items=_two_column_items())

    assert _read(monkeypatch, tmp_path, [page])[0].metadata["column"] == "multi_column"


def test_full_width_heading_does_not_hide_the_gutter(monkeypatch, tmp_path):
    """A running head spanning both columns is dropped before the gutter test."""
    items = [_item("RUNNING HEAD", x=0.0, y=0.0, width=100.0), *_two_column_items()]
    page = SimpleNamespace(page_num=1, text_items=items)

    documents = _read(monkeypatch, tmp_path, [page])

    assert documents[0].metadata["column"] == "multi_column"
    assert "RUNNING HEAD" in documents[0].get_content()


def test_single_column_page_keeps_library_order(monkeypatch, tmp_path):
    """A page with no gutter is emitted exactly as LiteParse returned it."""
    items = [_item(f"line {row}", x=0.0, y=10.0 * row, width=100.0) for row in range(12)]
    page = SimpleNamespace(page_num=1, text_items=items)

    documents = _read(monkeypatch, tmp_path, [page])

    assert documents[0].get_content().splitlines() == [f"line {row}" for row in range(12)]
    assert documents[0].metadata["column"] == "single"


def test_table_page_keeps_library_order(monkeypatch, tmp_path):
    """Row-structured cells have no qualifying gutter, so the order is untouched."""
    items = []
    for row in range(8):
        y = 10.0 + row * 10
        for col, x in enumerate((0.0, 26.0, 52.0, 78.0)):
            items.append(_item(f"r{row}c{col}", x=x, y=y, width=22.0))
    page = SimpleNamespace(page_num=1, text_items=items)

    documents = _read(monkeypatch, tmp_path, [page])

    assert documents[0].get_content().splitlines() == [item.text for item in items]
    assert documents[0].metadata["column"] != "multi_column"


def test_sidebar_does_not_qualify_as_a_second_column(monkeypatch, tmp_path):
    """A narrow sidebar beside a body column fails the balance condition."""
    items = [_item(f"body {row}", x=0.0, y=10.0 + row * 10, width=68.0) for row in range(12)]
    items += [_item(f"note {row}", x=74.0, y=10.0 + row * 40, width=26.0) for row in range(3)]
    page = SimpleNamespace(page_num=1, text_items=items)

    assert _read(monkeypatch, tmp_path, [page])[0].metadata["column"] != "multi_column"


def test_reordering_preserves_content(monkeypatch, tmp_path):
    """Reordering never adds, drops or alters an item."""
    items = _two_column_items()
    page = SimpleNamespace(page_num=1, text_items=items)

    emitted = _read(monkeypatch, tmp_path, [page])[0].get_content().splitlines()

    assert sorted(emitted) == sorted(item.text for item in items)


def _one_page(monkeypatch, tmp_path, items) -> str:
    """Return the text of a one-page document made of *items*."""
    page = SimpleNamespace(page_num=1, text_items=items)
    return _read(monkeypatch, tmp_path, [page])[0].get_content()


def test_words_drawn_separately_join_into_one_line(monkeypatch, tmp_path):
    """A title drawn word by word comes out on one line, not one word per line."""
    items = [
        _item("Epistemic", x=43.6, y=170.0, width=95.5, height=20.0),
        _item("injustice", x=147.1, y=170.0, width=82.1, height=20.0),
        _item("in", x=237.3, y=170.0, width=17.9, height=20.0),
        _item("practice:", x=43.6, y=195.8, width=84.1, height=20.0),
        _item("The", x=135.7, y=195.8, width=37.8, height=20.0),
    ]

    assert _one_page(monkeypatch, tmp_path, items) == "Epistemic injustice in\npractice: The"


def test_superscript_joins_its_word(monkeypatch, tmp_path):
    """A raised affiliation marker overlapping the line stays on it."""
    items = [
        _item("Berg", x=0.0, y=10.0, width=20.0, height=10.0),
        _item("1,2", x=20.5, y=8.0, width=6.0, height=6.0),
    ]

    assert _one_page(monkeypatch, tmp_path, items) == "Berg1,2"


def test_column_gap_on_the_same_line_breaks_the_line(monkeypatch, tmp_path):
    """A sidebar and the body beside it are never glued into one sentence."""
    items = [
        _item("The authors have", x=36.1, y=95.4, width=123.2, height=9.5),
        _item("solani in lettuce", x=198.0, y=95.2, width=362.4, height=11.5),
    ]

    assert _one_page(monkeypatch, tmp_path, items) == "The authors have\nsolani in lettuce"


def test_right_to_left_step_starts_a_new_line(monkeypatch, tmp_path):
    """An item back to the left at the same height is a new line, not a continuation."""
    items = [
        _item("second", x=50.0, y=10.0, width=20.0, height=10.0),
        _item("first", x=0.0, y=10.0, width=20.0, height=10.0),
    ]

    assert _one_page(monkeypatch, tmp_path, items) == "second\nfirst"


def test_kerning_split_joins_without_a_space(monkeypatch, tmp_path):
    """Two pieces of one word, drawn with no gap, rejoin as one word."""
    items = [
        _item("fibro", x=0.0, y=10.0, width=25.0, height=10.0),
        _item("myalgia", x=25.2, y=10.0, width=35.0, height=10.0),
    ]

    assert _one_page(monkeypatch, tmp_path, items) == "fibromyalgia"
