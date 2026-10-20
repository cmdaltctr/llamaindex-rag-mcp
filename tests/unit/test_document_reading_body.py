"""The body of ``/v1/settings/document-reading`` (document-reading-settings, task 1.6).

The builder imports no web framework, so these tests need no ``fastapi``. A
plain namespace stands in for ``ConfigurationState``. Every test points
``OMRG_CONFIG_DIR`` at a temporary folder and never reads the real one.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from omrg import capabilities
from omrg.config import Settings, provenance
from omrg.config.rules import DOCUMENT_READING_KEYS
from omrg.config.settings_file import file_revision, read_settings_file
from omrg.transports.api import document_reading
from omrg.transports.api.document_reading import (
    build_document_reading,
    lock_reason,
    reset_reader_in_use,
    update_refusal,
)
from omrg.transports.api.restart_snapshot import capture

VARIABLES = tuple(key.upper() for key in DOCUMENT_READING_KEYS) + (
    "OCR_WORKERS_DIR",
    "OCR_WORKER_COMMAND",
)
DEFAULTS = {
    "pdf_reader": "pdf_inspector",
    "ocr_fallback_enabled": True,
    "ocr_fallback_min_confidence": 0.5,
    "ocr_fallback_page_fraction": 0.10,
    "ocr_routing_unit": "document",
    "ocr_engine_primary": "dots-mocr",
    "ocr_engine_fallback": "paddleocr-vl",
    "ocr_maths_routing_enabled": True,
    "ocr_maths_page_fraction": 0.10,
}
OPTIONS = {"pypdf": None, "pypdfium2": "The package 'pypdfium2' is not installed."}


class Harness:
    """A config folder, an empty ``.env`` and the launch state."""

    def __init__(self, folder: Path, empty_env: Path) -> None:
        self.folder = folder
        self.empty_env = empty_env
        self.state: Any = None

    def write(self, text: str) -> None:
        (self.folder / "omrg.jsonc").write_text(text, encoding="utf-8")

    def launch(self) -> None:
        file = read_settings_file(self.folder)
        self.state = SimpleNamespace(
            launch_settings=Settings(_env_file=self.empty_env),
            snapshot=capture(file),
            read_file=lambda: read_settings_file(self.folder),
        )

    def body(self) -> dict[str, Any]:
        return build_document_reading(self.state)

    def rows(self) -> dict[str, dict[str, Any]]:
        return {row["key"]: row for row in self.body()["settings"]}


@pytest.fixture
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Harness:
    for variable in VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setattr(provenance, "DOTENV_KEYS", frozenset())
    monkeypatch.setattr(capabilities, "pdf_reader_options", lambda: dict(OPTIONS))
    monkeypatch.setattr(capabilities, "resolve_pdf_reader", lambda settings: "pypdf")
    reset_reader_in_use()
    folder = tmp_path / "omrg-config"
    folder.mkdir(mode=0o700)
    monkeypatch.setenv("OMRG_CONFIG_DIR", str(folder))
    empty_env = tmp_path / "none.env"
    empty_env.write_text("", encoding="utf-8")
    yield Harness(folder, empty_env)
    reset_reader_in_use()


# ── Shape ────────────────────────────────────────────────────────────────


def test_nine_rows_in_key_order_with_defaults(harness: Harness) -> None:
    harness.launch()
    body = harness.body()
    assert set(body) == {"revision", "settings", "pdf_readers", "pdf_reader_in_use", "ocr"}
    assert [row["key"] for row in body["settings"]] == list(DOCUMENT_READING_KEYS)
    assert body["revision"] == "absent"
    for row in body["settings"]:
        assert row["default"] == DEFAULTS[row["key"]]
        assert row["value"] == DEFAULTS[row["key"]]
        assert (row["saved"], row["source"], row["locked"]) == (None, "default", False)
        assert (row["lock_reason"], row["restart_pending"]) == (None, False)


def test_readers_list_auto_first_then_the_registry_order(harness: Harness) -> None:
    harness.launch()
    body = harness.body()
    assert body["pdf_readers"] == [
        {"name": "auto", "available": True, "reason": None},
        {"name": "pypdf", "available": True, "reason": None},
        {"name": "pypdfium2", "available": False, "reason": OPTIONS["pypdfium2"]},
    ]
    assert body["pdf_reader_in_use"] == "pypdf"


def test_the_reader_in_use_is_computed_once_per_process(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        capabilities, "resolve_pdf_reader", lambda settings: calls.append("x") or "liteparse"
    )
    harness.launch()
    assert harness.body()["pdf_reader_in_use"] == "liteparse"
    assert harness.body()["pdf_reader_in_use"] == "liteparse"
    assert calls == ["x"]


def test_a_failing_reader_probe_gives_null(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(settings: Any) -> str:
        raise RuntimeError("probe failed")

    monkeypatch.setattr(capabilities, "resolve_pdf_reader", explode)
    harness.launch()
    assert harness.body()["pdf_reader_in_use"] is None


# ── Sources and locks ────────────────────────────────────────────────────


def test_a_file_value_reads_config_file_and_is_saved(harness: Harness) -> None:
    harness.write('{ "pdf_reader": "liteparse", "ocr_fallback_page_fraction": 0.2 }')
    harness.launch()
    found = harness.rows()
    assert (found["pdf_reader"]["value"], found["pdf_reader"]["saved"]) == (
        "liteparse",
        "liteparse",
    )
    assert found["pdf_reader"]["source"] == "config-file"
    assert found["ocr_fallback_page_fraction"]["value"] == 0.2
    assert harness.body()["revision"] == file_revision(harness.folder)


def test_env_and_dotenv_lock_the_row(harness: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PDF_READER", "pypdf")
    monkeypatch.setenv("OCR_ROUTING_UNIT", "page")
    monkeypatch.setattr(provenance, "DOTENV_KEYS", frozenset({"OCR_ROUTING_UNIT"}))
    harness.launch()
    found = harness.rows()
    assert (found["pdf_reader"]["source"], found["pdf_reader"]["locked"]) == ("env", True)
    assert found["pdf_reader"]["lock_reason"] == (
        "Remove PDF_READER from the environment or .env to edit it here."
    )
    unit = found["ocr_routing_unit"]
    assert (unit["value"], unit["source"], unit["locked"]) == ("page", "dotenv", True)
    assert unit["lock_reason"] == lock_reason("ocr_routing_unit")
    assert lock_reason("ocr_routing_unit") == (
        "Remove OCR_ROUTING_UNIT from the environment or .env to edit it here."
    )


def test_an_explicit_option_reads_default(harness: Harness) -> None:
    harness.launch()
    harness.state.launch_settings = Settings(_env_file=harness.empty_env, ocr_routing_unit="page")
    row = harness.rows()["ocr_routing_unit"]
    assert (row["value"], row["source"], row["locked"]) == ("page", "default", False)


# ── restart_pending and saved ────────────────────────────────────────────


def test_a_file_change_after_launch_is_pending(harness: Harness) -> None:
    harness.launch()
    harness.write('{ "pdf_reader": "liteparse" }')
    row = harness.rows()["pdf_reader"]
    assert (row["value"], row["saved"], row["restart_pending"]) == (
        "pdf_inspector",
        "liteparse",
        True,
    )
    assert not any(r["restart_pending"] for k, r in harness.rows().items() if k != "pdf_reader")


def test_a_locked_key_is_never_pending(harness: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PDF_READER", "pypdf")
    harness.launch()
    harness.write('{ "pdf_reader": "liteparse" }')
    row = harness.rows()["pdf_reader"]
    assert (row["locked"], row["restart_pending"]) == (True, False)


def test_saved_is_null_for_a_value_that_breaks_its_rule(harness: Harness) -> None:
    harness.write(
        '{ "pdf_reader": "pdfminer", "ocr_engine_primary": "../x", "ocr_maths_page_fraction": 3 }'
    )
    harness.launch()
    found = harness.rows()
    assert found["pdf_reader"]["saved"] is None
    assert found["pdf_reader"]["value"] == "auto"  # startup fallback, unchanged
    assert found["ocr_engine_primary"]["saved"] is None
    assert found["ocr_maths_page_fraction"]["saved"] is None


def test_a_hand_written_blank_fallback_comes_back_as_not_set(harness: Harness) -> None:
    # The file reader treats blank text as not set, so the engine keeps paddleocr-vl (D8).
    harness.write('{ "ocr_engine_fallback": "" }')
    harness.launch()
    assert harness.rows()["ocr_engine_fallback"]["saved"] is None


def test_a_missing_state_uses_the_launch_settings_and_nothing_is_pending(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    from omrg import compose

    harness.write('{ "pdf_reader": "liteparse" }')
    monkeypatch.setattr(compose, "get_settings", lambda: Settings(_env_file=harness.empty_env))
    body = build_document_reading(None)
    row = {r["key"]: r for r in body["settings"]}["pdf_reader"]
    assert (row["value"], row["saved"], row["restart_pending"]) == ("liteparse", "liteparse", False)


# ── The OCR block ────────────────────────────────────────────────────────


def test_the_ocr_block_without_a_workers_folder(harness: Harness) -> None:
    harness.launch()
    ocr = harness.body()["ocr"]
    assert ocr["workers_dir"] is None and ocr["worker_command_set"] is False
    assert [engine["name"] for engine in ocr["engines"]] == ["dots-mocr", "paddleocr-vl"]
    assert {engine["available"] for engine in ocr["engines"]} == {False}


def test_the_ocr_block_lists_saved_engines_and_the_worker_command(
    harness: Harness, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("OCR_WORKERS_DIR", str(tmp_path / "workers"))
    monkeypatch.setenv("OCR_WORKER_COMMAND", "python -m my_worker")
    harness.write('{ "ocr_engine_fallback": "my-engine" }')
    harness.launch()
    harness.write('{ "ocr_engine_fallback": "other-engine" }')
    ocr = harness.body()["ocr"]
    assert ocr["workers_dir"] == "~/workers"
    assert ocr["worker_command_set"] is True
    names = [engine["name"] for engine in ocr["engines"]]
    assert names == ["dots-mocr", "my-engine", "other-engine"]


# ── PUT checks 2 to 5 ────────────────────────────────────────────────────


def test_update_checks_follow_the_contract_order(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OCR_ROUTING_UNIT", "page")
    monkeypatch.setenv("OCR_ENGINE_FALLBACK", "x")
    harness.launch()
    launch = harness.state.launch_settings
    assert update_refusal({"embed_provider": "local"}, launch) == (
        400,
        "embed_provider is not a document reading setting.",
    )
    assert update_refusal({"ocr_engine_fallback": None, "ocr_routing_unit": 1}, launch) == (
        409,
        "Remove OCR_ROUTING_UNIT from the environment or .env to edit it here.",
    )
    assert update_refusal({"ocr_maths_page_fraction": 1.5}, launch) == (
        400,
        "ocr_maths_page_fraction: The value must be a number from 0.0 to 1.0.",
    )
    assert update_refusal({"pdf_reader": "pypdfium2"}, launch) == (
        400,
        "pdf_reader: This PDF reader is not installed. Install its package, then save again.",
    )
    assert update_refusal({"pdf_reader": "auto", "ocr_engine_primary": "nowhere"}, launch) is None


def test_the_builder_module_imports_no_web_framework() -> None:
    source = Path(document_reading.__file__).read_text(encoding="utf-8")
    assert "fastapi" not in source and "starlette" not in source
