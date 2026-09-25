"""Regression tests for reader-produced Markdown normalisation."""

from __future__ import annotations

from pathlib import Path

import pytest

from omrg.core.ingestion.normalise import normalise_reader_text


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("signifi- <u>cantly different at p≤ 0.05</u>", "signifi- cantly different at p≤ 0.05"),
        ("<span class='x'>A</span> <font color='red'>B</font> <center>C</center>", "A B C"),
        ("<b>Fig 4.</b> <strong>Result</strong>", "**Fig 4.** **Result**"),
        ("<i>one</i> <em>two</em>", "*one* *two*"),
        ("first<br />second", "first\nsecond"),
        ("H<sub>2</sub>O", "H<sub>2</sub>O"),
        ('<sub title="&amp;">x</sub>', '<sub title="&amp;">x</sub>'),
        ("A &amp; B &lt; C", "A & B < C"),
        (
            "[https://doi.org/10.1371/x](https://doi.org/10.1371/x)",
            "[https://doi.org/10.1371/x](https://doi.org/10.1371/x)",
        ),
        ("https://doi.org/10.1371/x", "https://doi.org/10.1371/x"),
        ("<div>unfinished", "<div>unfinished"),
        ('<div><img src="x">caption', '<div><img src="x">caption'),
    ],
)
def test_formatting_and_preserved_text(source: str, expected: str) -> None:
    assert normalise_reader_text(source) == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("before<div><img src='a.jpg'/>Badge</div>after", "beforeBadgeafter"),
        ("before<div><img src='c.jpg' alt='Image'/></div>after", "beforeafter"),
        ("<div style='text-align: center;'>Figure 2 caption</div>", "Figure 2 caption"),
        ("before<img src='a.jpg' width='8%'/>after", "beforeafter"),
        ("<div>outer <div><img src='a.jpg'/>badge</div> text</div>", "outer badge text"),
    ],
)
def test_image_blocks_and_captions(source: str, expected: str) -> None:
    assert normalise_reader_text(source) == expected


def test_table_keeps_structure_and_spans() -> None:
    source = (
        "<table border=1 style='margin: auto;'><tr>"
        "<td colspan=\"2\" style='text-align: center;'>"
        "<b>Rigid</b> propeller &amp; wing</td></tr></table>"
    )
    expected = '<table><tr><td colspan="2">Rigid propeller &amp; wing</td></tr></table>'
    assert normalise_reader_text(source) == expected


def test_code_fences_and_inline_code_are_unchanged() -> None:
    source = "```html\n<div><img src='a.jpg' />&amp;</div>\n```\n`<u>$5 &amp;</u>`"
    assert normalise_reader_text(source) == source


def test_math_is_protected_from_entities_and_tags() -> None:
    source = (
        r"$$ \begin{align*} f(x) &= a < b \ &not= c &times d \end{align*} $$"
        "\n" + r"$a < b &not= c$" + "\n" + r"\begin{align*}x &= a < b\end{align*}"
    )
    assert normalise_reader_text(source) == source
    assert "¬" not in normalise_reader_text(source)


def test_dollar_inside_code_does_not_open_math() -> None:
    source = "`$price` <u>heading</u> &amp;"
    assert normalise_reader_text(source) == "`$price` heading &"


def test_normalisation_is_deterministic() -> None:
    source = "<div><img src='x'/>Badge</div><u>heading</u>"
    assert normalise_reader_text(source) == normalise_reader_text(source)


@pytest.mark.parametrize(
    "name",
    ["pdf_inspector", "worker_blocks", "worker_chart", "worker_table", "liteparse", "worker_maths"],
)
def test_fixtures_are_small_and_stable(fixtures_dir: Path, name: str) -> None:
    path = fixtures_dir / "reader_output" / f"{name}.md"
    assert path.stat().st_size < 2048
    source = path.read_text()
    result = normalise_reader_text(source)
    assert normalise_reader_text(source) == result
    if name in {"liteparse", "worker_maths"}:
        assert result == source


def test_fixtures_keep_every_visible_character(fixtures_dir: Path) -> None:
    """Every visible character survives, text inside image blocks included."""
    import html
    import re

    tag = re.compile(r"</?[A-Za-z][\w-]*\b[^>]*>")

    def visible(text: str) -> str:
        return "".join(html.unescape(tag.sub("", text)).split())

    for name in (
        "pdf_inspector",
        "worker_blocks",
        "worker_chart",
        "worker_table",
        "liteparse",
        "worker_maths",
    ):
        source = (fixtures_dir / "reader_output" / f"{name}.md").read_text()
        assert visible(normalise_reader_text(source)) == visible(source), name


def test_normaliser_version_pins_fixture_outputs(fixtures_dir: Path) -> None:
    """A change in any fixture output requires a normaliser version bump."""
    import hashlib

    from omrg.core.ingestion.normalise import NORMALISER_VERSION

    expected_digests = {
        1: "f2c9121ad463667efb74ec4a6c11051b92aa698102ed76570595f01f0393af29",
        2: "686cce19f136f9b9b1715203faf3eb0e5ebfc64600de84665bfa81f3022481a6",
    }
    directory = fixtures_dir / "reader_output"
    payload = "".join(
        f"{path.name}\0{normalise_reader_text(path.read_text())}\0"
        for path in sorted(directory.glob("*.md"))
        if path.name != "README.md"
    )
    assert hashlib.sha256(payload.encode()).hexdigest() == expected_digests[NORMALISER_VERSION]


def test_normalisation_setting_uses_nested_env_only(monkeypatch: pytest.MonkeyPatch) -> None:
    from omrg.compose_settings import settings_to_effective
    from omrg.config import Settings
    from omrg.core.ingestion.settings import IngestionSettings
    from omrg.core.settings import IngestionBlock

    assert IngestionSettings().normalise_reader_output is True
    assert IngestionBlock().normalise_reader_output is True
    monkeypatch.setenv("INGESTION__NORMALISE_READER_OUTPUT", "false")
    disabled = Settings(_env_file=None)
    assert disabled.ingestion.normalise_reader_output is False
    assert settings_to_effective(disabled).ingestion.normalise_reader_output is False
    monkeypatch.delenv("INGESTION__NORMALISE_READER_OUTPUT")
    monkeypatch.setenv("NORMALISE_READER_OUTPUT", "false")
    assert Settings(_env_file=None).ingestion.normalise_reader_output is True
