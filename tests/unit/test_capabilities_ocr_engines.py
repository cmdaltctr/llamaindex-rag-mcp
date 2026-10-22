"""The OCR engine list of Settings > Document reading (document-reading-settings, task 1.5).

Each test builds a temporary workers folder. A provisioned engine is a folder
with a fake ``.venv/bin/python`` file; nothing runs it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from omrs.capabilities import (
    ENGINE_NOT_A_FOLDER,
    ENGINE_WORKERS_UNSET,
    ocr_engine_options,
)

POSIX_ONLY = pytest.mark.skipif(sys.platform == "win32", reason="POSIX engine layout")


def provision(root: Path, name: str) -> None:
    python = root / "engines" / name / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")


def test_no_folder_and_no_names_gives_an_empty_list() -> None:
    assert ocr_engine_options("", []) == []
    assert ocr_engine_options("  ", ["", "  "]) == []


def test_no_folder_marks_each_named_engine_unavailable() -> None:
    assert ocr_engine_options("", ["paddleocr-vl", "dots-mocr", "dots-mocr"]) == [
        {"name": "dots-mocr", "available": False, "reason": ENGINE_WORKERS_UNSET},
        {"name": "paddleocr-vl", "available": False, "reason": ENGINE_WORKERS_UNSET},
    ]
    assert ENGINE_WORKERS_UNSET == "OCR_WORKERS_DIR is not set, so no OCR engine can run."


@POSIX_ONLY
def test_provisioned_unprovisioned_and_invalid_engines(tmp_path: Path) -> None:
    provision(tmp_path, "dots-mocr")
    (tmp_path / "engines" / "half-done").mkdir()
    options = ocr_engine_options(str(tmp_path), ["paddleocr-vl", "../x"])
    assert options == [
        {"name": "../x", "available": False, "reason": ENGINE_NOT_A_FOLDER},
        {"name": "dots-mocr", "available": True, "reason": None},
        {
            "name": "half-done",
            "available": False,
            "reason": "Not provisioned. Run python3 ocr-workers/provision.py half-done.",
        },
        {
            "name": "paddleocr-vl",
            "available": False,
            "reason": "Not provisioned. Run python3 ocr-workers/provision.py paddleocr-vl.",
        },
    ]
    assert ENGINE_NOT_A_FOLDER == "The name is not a folder name."


@POSIX_ONLY
def test_the_scan_skips_files_and_folders_that_are_not_engine_names(tmp_path: Path) -> None:
    provision(tmp_path, "good")
    (tmp_path / "engines" / ".cache").mkdir()
    (tmp_path / "engines" / "has space").mkdir()
    (tmp_path / "engines" / "README.md").write_text("", encoding="utf-8")
    assert [option["name"] for option in ocr_engine_options(str(tmp_path), [])] == ["good"]


@POSIX_ONLY
def test_a_home_relative_folder_is_expanded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    provision(tmp_path / "workers", "dots-mocr")
    options = ocr_engine_options("~/workers", ["dots-mocr"])
    assert options == [{"name": "dots-mocr", "available": True, "reason": None}]


def test_a_missing_engines_folder_lists_only_the_names(tmp_path: Path) -> None:
    options = ocr_engine_options(str(tmp_path / "nowhere"), ["dots-mocr"])
    assert [(o["name"], o["available"]) for o in options] == [("dots-mocr", False)]
