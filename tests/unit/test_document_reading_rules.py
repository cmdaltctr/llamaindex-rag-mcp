"""Write rules of the document-reading keys (document-reading-settings, tasks 1.1 to 1.4).

The rules run only when the Settings page writes ``omrs.jsonc``. Startup
reading stays as it was: an unknown ``pdf_reader`` still warns and falls back
to ``auto``. Every test points ``OMRS_CONFIG_DIR`` at a temporary folder.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

from omrs.config import Settings
from omrs.config.rules import (
    DOCUMENT_READING_KEYS,
    ENGINE_NAME_PATTERN,
    MAX_ENGINE_NAME_CHARS,
    PDF_READER_NAMES,
    document_reading_problem,
)
from omrs.config.settings_file_write import SettingsFileRefused, write_settings
from omrs.config.user_config import parse_jsonc

ENGINE_RULE = (
    "The engine name must start with a letter or digit, hold only letters, digits, dots, "
    "hyphens and underscores, and be at most 64 characters."
)
FRACTION_RULE = "The value must be a number from 0.0 to 1.0."
BOOL_RULE = "The value must be true or false."
BLANK_RULE = "The value must not be blank. Send null to use the default."
READER_RULE = "The value must be one of: auto, liteparse, pdf_inspector, pypdfium2, pypdf."
UNIT_RULE = "The value must be one of: document, page."
FRACTIONS = ("ocr_fallback_min_confidence", "ocr_fallback_page_fraction", "ocr_maths_page_fraction")
BOOLEANS = ("ocr_fallback_enabled", "ocr_maths_routing_enabled")
ENGINES = ("ocr_engine_primary", "ocr_engine_fallback")


# ── 1.1 Reader names ─────────────────────────────────────────────────────


def test_reader_names_match_the_pdf_registry() -> None:
    from omrs.integrations.pdf import registry

    assert PDF_READER_NAMES[0] == "auto"
    assert set(PDF_READER_NAMES) - {"auto"} == set(registry.available())


def test_the_settings_validator_reads_the_shared_reader_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in PDF_READER_NAMES:
        monkeypatch.setenv("PDF_READER", name)
        assert Settings().pdf_reader == name


# ── 1.2 The write rule ───────────────────────────────────────────────────


def test_the_key_order_is_the_contract_order() -> None:
    assert DOCUMENT_READING_KEYS == (
        "pdf_reader",
        "ocr_fallback_enabled",
        "ocr_fallback_min_confidence",
        "ocr_fallback_page_fraction",
        "ocr_routing_unit",
        "ocr_engine_primary",
        "ocr_engine_fallback",
        "ocr_maths_routing_enabled",
        "ocr_maths_page_fraction",
    )


def test_engine_pattern_matches_the_route_resolver() -> None:
    from omrs.integrations.ocr_worker import routes

    assert ENGINE_NAME_PATTERN == routes._ENGINE_NAME_RE.pattern
    assert MAX_ENGINE_NAME_CHARS == 64


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("pdf_reader", "liteparse"),
        ("pdf_reader", "auto"),
        ("ocr_routing_unit", "page"),
        ("ocr_engine_primary", "dots-mocr"),
        ("ocr_engine_fallback", "my_engine.v2"),
        ("ocr_engine_fallback", "e" * 64),
        ("ocr_fallback_enabled", False),
        ("ocr_maths_routing_enabled", True),
        ("ocr_fallback_page_fraction", 0.2),
        ("ocr_fallback_min_confidence", 0),
        ("ocr_maths_page_fraction", 1),
        ("ocr_maths_page_fraction", 1.0),
        ("ocr_engine_primary", None),
        ("pdf_reader", None),
    ],
)
def test_valid_values_pass(key: str, value: Any) -> None:
    assert document_reading_problem(key, value) is None


@pytest.mark.parametrize(
    ("key", "value", "rule"),
    [
        ("pdf_reader", "pdfminer", READER_RULE),
        ("pdf_reader", 3, READER_RULE),
        ("pdf_reader", "", BLANK_RULE),
        ("ocr_routing_unit", "chapter", UNIT_RULE),
        ("ocr_routing_unit", True, UNIT_RULE),
        ("ocr_routing_unit", "  ", BLANK_RULE),
        ("ocr_engine_primary", "../x", ENGINE_RULE),
        ("ocr_engine_primary", ".hidden", ENGINE_RULE),
        ("ocr_engine_primary", "a/b", ENGINE_RULE),
        ("ocr_engine_primary", "abc\n", ENGINE_RULE),
        ("ocr_engine_primary", "e" * 65, ENGINE_RULE),
        ("ocr_engine_primary", 7, ENGINE_RULE),
        ("ocr_engine_fallback", "", BLANK_RULE),
        ("ocr_engine_fallback", "   ", BLANK_RULE),
        ("ocr_fallback_enabled", "true", BOOL_RULE),
        ("ocr_fallback_enabled", 1, BOOL_RULE),
        ("ocr_maths_routing_enabled", "", BOOL_RULE),
        ("ocr_fallback_page_fraction", 1.5, FRACTION_RULE),
        ("ocr_fallback_page_fraction", -0.1, FRACTION_RULE),
        ("ocr_fallback_min_confidence", True, FRACTION_RULE),
        ("ocr_maths_page_fraction", "0.2", FRACTION_RULE),
        ("ocr_maths_page_fraction", float("nan"), FRACTION_RULE),
    ],
)
def test_each_rule_has_its_exact_message(key: str, value: Any, rule: str) -> None:
    assert document_reading_problem(key, value) == rule


def test_a_rule_never_holds_the_value() -> None:
    for key in DOCUMENT_READING_KEYS:
        message = document_reading_problem(key, "zz-secret-zz/..") or ""
        assert "zz-secret-zz" not in message


def test_a_key_outside_the_nine_passes_unchecked() -> None:
    assert document_reading_problem("ollama_base_url", "") is None


# ── 1.3 The writer ───────────────────────────────────────────────────────


@pytest.fixture
def folder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    root = tmp_path / "cfg" / "omrs"
    root.mkdir(parents=True, mode=0o700)
    monkeypatch.setenv("OMRS_CONFIG_DIR", str(root))
    (root / "omrs.jsonc").write_text(
        '// mine\n{\n  "ocr_engine_fallback": "my-engine", // keep this\n  "web_port": 9100\n}\n',
        encoding="utf-8",
    )
    return root


def text(folder: Path) -> str:
    return (folder / "omrs.jsonc").read_text(encoding="utf-8")


def test_a_valid_reader_is_written_and_every_other_byte_stays(folder: Path) -> None:
    before = text(folder)
    write_settings({"pdf_reader": "liteparse"}, revision=None, directory=folder)
    after = text(folder)
    assert parse_jsonc(after)["pdf_reader"] == "liteparse"
    assert "// keep this" in after and after.startswith("// mine\n")
    assert '"ocr_engine_fallback": "my-engine", // keep this' in after
    assert len(after) > len(before)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"pdf_reader": "pdfminer"}, f"pdf_reader: {READER_RULE}"),
        ({"ocr_engine_fallback": "../other"}, f"ocr_engine_fallback: {ENGINE_RULE}"),
        ({"ocr_engine_fallback": ""}, f"ocr_engine_fallback: {BLANK_RULE}"),
        ({"ocr_fallback_enabled": "true"}, f"ocr_fallback_enabled: {BOOL_RULE}"),
        (
            {"ocr_routing_unit": "page", "ocr_maths_page_fraction": 1.5},
            f"ocr_maths_page_fraction: {FRACTION_RULE}",
        ),
    ],
)
def test_a_refused_value_writes_nothing(
    folder: Path, changes: dict[str, Any], message: str
) -> None:
    before = text(folder)
    with pytest.raises(SettingsFileRefused) as caught:
        write_settings(changes, revision=None, directory=folder)
    assert str(caught.value) == message
    assert text(folder) == before


def test_null_removes_the_key_and_keeps_the_comments(folder: Path) -> None:
    write_settings({"ocr_engine_fallback": None}, revision=None, directory=folder)
    after = text(folder)
    assert "ocr_engine_fallback" not in parse_jsonc(after)
    assert after.startswith("// mine\n") and parse_jsonc(after)["web_port"] == 9100


def test_numbers_and_booleans_are_written_as_json(folder: Path) -> None:
    write_settings(
        {
            "ocr_fallback_page_fraction": 0.2,
            "ocr_maths_routing_enabled": False,
            "ocr_routing_unit": "page",
        },
        revision=None,
        directory=folder,
    )
    data = parse_jsonc(text(folder))
    assert data["ocr_fallback_page_fraction"] == 0.2
    assert data["ocr_maths_routing_enabled"] is False
    assert data["ocr_routing_unit"] == "page"


# ── 1.4 Startup behaviour does not change ───────────────────────────────


def test_an_unknown_reader_in_the_file_still_falls_back_to_auto_at_startup(
    folder: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.delenv("PDF_READER", raising=False)
    (folder / "omrs.jsonc").write_text('{ "pdf_reader": "pdfminer" }', encoding="utf-8")
    empty = folder / "none.env"
    empty.write_text("", encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="omrs.config"):
        settings = Settings(_env_file=empty)
    assert settings.pdf_reader == "auto"
    assert any("Unknown PDF_READER" in record.getMessage() for record in caplog.records)
