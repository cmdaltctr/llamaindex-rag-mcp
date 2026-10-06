"""Maths-page detection from font evidence (task 5.1, design D5).

The fixtures are synthetic PDFs built with pypdf. The ``eq01`` pair
reproduces the exact font resources of ``eq01`` (Kingma & Welling,
arXiv 1312.6114v11) pages 1 and 11, read from the Experiment 34 copy on
2026-09-30: the paper itself is not committed. When that copy is
present, one extra test also runs the detector on the real PDF.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
    NumberObject,
)

from omrg.integrations.pdf import maths_pages
from omrg.integrations.pdf.maths_pages import (
    MATHS_DETECTOR_VERSION,
    MATHS_FONT_PATTERNS,
    is_maths_font,
    maths_font_pages,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
#: The gitignored Experiment 34 copy, or any copy named by OMRG_EQ01_PDF.
EQ01_CANDIDATES = [
    Path(os.environ.get("OMRG_EQ01_PDF", "/nonexistent")),
    REPO_ROOT / "experiments" / "34-worker-sample-review-2026-09-19" / "corpus" / "eq01.pdf",
]

#: ``eq01`` p11 fonts, exactly as the real PDF names them.
EQ01_P11_FONTS = [
    "DYILGD+CMEX10",
    "OBGRLQ+CMMI7",
    "ANCPWH+CMMI10",
    "KFCAMB+CMSY10",
    "EDWSKD+NimbusRomNo9L-Medi",
    "MGDDHF+NimbusRomNo9L-Regu",
    "UVUOJU+CMBX10",
    "RSAPAN+CMR7",
    "RONREM+CMMIB10",
    "UAUUQM+CMMIB7",
    "PTTSAO+CMR10",
]
#: ``eq01`` p1 fonts: Nimbus and Times only.
EQ01_P1_FONTS = [
    "EDWSKD+NimbusRomNo9L-Medi",
    "MGDDHF+NimbusRomNo9L-Regu",
    "BRGJKD+NimbusMonL-Regu",
    "PVOFDH+NimbusRomNo9L-ReguItal",
    "Times-Roman",
]


def _font(writer: PdfWriter, base_font: str, *, to_unicode: bool = False):
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/" + base_font),
        }
    )
    if to_unicode:
        cmap = DecodedStreamObject()
        cmap.set_data(b"/CIDInit /ProcSet findresource begin end")
        font[NameObject("/ToUnicode")] = writer._add_object(cmap)
    return writer._add_object(font)


def _font_dict(writer: PdfWriter, fonts: list[str], *, to_unicode: bool = False):
    return DictionaryObject(
        {
            NameObject(f"/F{index}"): _font(writer, name, to_unicode=to_unicode)
            for index, name in enumerate(fonts)
        }
    )


def build_pdf(path: Path, pages: list[list[str]], *, to_unicode: bool = False) -> Path:
    """Write one page per font list, fonts on the page's own resources."""
    writer = PdfWriter()
    for fonts in pages:
        page = writer.add_blank_page(width=200, height=200)
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): _font_dict(writer, fonts, to_unicode=to_unicode)}
        )
    writer.write(path)
    return path


def build_form_pdf(path: Path, fonts: list[str], *, depth: int) -> Path:
    """Write one page whose fonts sit *depth* Form XObjects deep."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    resources = DictionaryObject({NameObject("/Font"): _font_dict(writer, fonts)})
    for level in range(depth):
        form = DecodedStreamObject()
        form.set_data(b"")
        form.update(
            {
                NameObject("/Type"): NameObject("/XObject"),
                NameObject("/Subtype"): NameObject("/Form"),
                NameObject("/BBox"): ArrayObject([NumberObject(0)] * 4),
                NameObject("/Resources"): resources,
            }
        )
        resources = DictionaryObject(
            {
                NameObject("/XObject"): DictionaryObject(
                    {NameObject(f"/X{level}"): writer._add_object(form)}
                )
            }
        )
    page[NameObject("/Resources")] = resources
    writer.write(path)
    return path


# ── The detection scenarios (spec maths-page-routing) ──────────────────────


def test_eq01_fonts_flag_p11_and_not_p1(tmp_path: Path) -> None:
    """``eq01`` p11 (CMEX10, CMMI7/10, CMMIB7/10, CMSY10) flagged; p1 not."""
    pdf = build_pdf(tmp_path / "eq01-fonts.pdf", [EQ01_P1_FONTS, EQ01_P11_FONTS])
    assert maths_font_pages(pdf) == frozenset({2})


def test_cmmi_with_a_unicode_map_is_flagged(tmp_path: Path) -> None:
    """Spec: "A maths font with a Unicode map is flagged"."""
    pdf = build_pdf(tmp_path / "tounicode.pdf", [["ABCDEF+CMMI10"]], to_unicode=True)
    assert maths_font_pages(pdf) == frozenset({1})


def test_latex_maths_page_without_unicode_map_is_flagged(tmp_path: Path) -> None:
    """Spec: "A LaTeX maths page without a Unicode map is flagged"."""
    pdf = build_pdf(tmp_path / "latex.pdf", [["CMMI10", "CMEX10"]])
    assert maths_font_pages(pdf) == frozenset({1})


def test_word_cambria_math_page_is_flagged(tmp_path: Path) -> None:
    """Spec: "A Word equation page is flagged" (Cambria Math, spaced name)."""
    pdf = build_pdf(tmp_path / "word.pdf", [["Calibri"], ["BCDEEE+Cambria Math"]])
    assert maths_font_pages(pdf) == frozenset({2})


@pytest.mark.parametrize("fonts", [["CMR10", "CMBX10", "CMTI10"], ["Times-Roman"]])
def test_prose_only_pages_are_not_flagged(tmp_path: Path, fonts: list[str]) -> None:
    """Spec: "Prose-only pages are not flagged" (CMR or Times text fonts)."""
    pdf = build_pdf(tmp_path / "prose.pdf", [fonts])
    assert maths_font_pages(pdf) == frozenset()


def test_malformed_resources_flag_nothing(tmp_path: Path) -> None:
    """Spec: "Unreadable font resources flag nothing" and the file continues."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): NumberObject(7)})
    pdf = tmp_path / "malformed.pdf"
    writer.write(pdf)
    assert maths_font_pages(pdf) == frozenset()
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"%PDF-1.4 truncated")
    assert maths_font_pages(broken) == frozenset()


def test_fonts_in_nested_forms_count_up_to_the_depth_cap(tmp_path: Path) -> None:
    """Fonts used through nested form objects count; the walk stops past depth 4."""
    within = build_form_pdf(tmp_path / "within.pdf", ["CMSY10"], depth=maths_pages.MAX_FORM_DEPTH)
    beyond = build_form_pdf(
        tmp_path / "beyond.pdf", ["CMSY10"], depth=maths_pages.MAX_FORM_DEPTH + 1
    )
    assert maths_font_pages(within) == frozenset({1})
    assert maths_font_pages(beyond) == frozenset()


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("/ABCDEF+CMMI10", True),
        ("CMBSY7", True),
        ("CMEX10", True),
        ("LMMathItalic10-Regular", True),
        ("LatinModernMath-Regular", True),
        ("MSBM10", True),
        ("EUFM10", True),
        ("STIXTwoMath-Regular", True),
        ("TeXGyreTermesMath-Regular", True),
        ("Libertinus Math", True),
        ("CMR10", False),
        ("CMMI", False),
        ("NewTXMI", False),
        ("Cambria", False),
        ("ABCDE+CMMI10", False),
    ],
)
def test_font_name_matching(name: str, expected: bool) -> None:
    """Subset prefix stripped, spaces and hyphens normalised, closed list."""
    assert is_maths_font(name) is expected


def test_pattern_list_is_pinned_to_the_detector_version() -> None:
    """Changing the maths-font list without a version bump fails here."""
    assert MATHS_DETECTOR_VERSION == 1
    assert MATHS_FONT_PATTERNS == (
        r"^(CMMI|CMMIB|CMSY|CMBSY|CMEX)\d+$",
        r"^LMMath(Italic|Symbols|Extension)\d+",
        r"^LatinModernMath",
        r"^(MSAM|MSBM|EUFM|EUSM|EUEX)\d+$",
        r"^(CambriaMath|STIXMath|STIXTwoMath|XITSMath|TeXGyre\w+Math|LibertinusMath|AsanaMath|FiraMath)",
    )


def test_real_eq01_when_present() -> None:
    """On the real ``eq01`` (if present locally), p11 is flagged and p1 is not."""
    pdf = next((path for path in EQ01_CANDIDATES if path.is_file()), None)
    if pdf is None:
        pytest.skip("eq01.pdf is gitignored and not present")
    flagged = maths_font_pages(pdf)
    assert 11 in flagged
    assert 1 not in flagged
