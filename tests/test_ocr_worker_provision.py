"""Unit tests for the OCR engine provisioning script (tasks 1.5, 3.1).

Only the pure checks and the command plan are exercised here, with
``subprocess.run`` replaced by a recorder. Provisioning itself installs
a multi-gigabyte environment and downloads model weights; that belongs
to the per-engine smoke tests run by the operator, never to this suite.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKERS_DIR = REPO_ROOT / "ocr-workers"
PROVISION_SCRIPT = WORKERS_DIR / "provision.py"
ENGINES = ("dots-mocr", "paddleocr-vl")


def _load_provision_module():
    """Import provision.py directly from its script path."""
    spec = importlib.util.spec_from_file_location("omrg_ocr_provision", PROVISION_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def provision():
    """Load the provisioning module once for the test module."""
    return _load_provision_module()


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch, provision) -> list[dict[str, Any]]:
    """Record every subprocess the script would run; each succeeds."""
    calls: list[dict[str, Any]] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        calls.append({"command": list(command), **kwargs})
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(provision.subprocess, "run", fake_run)
    monkeypatch.setattr(provision.shutil, "which", lambda name: f"/usr/bin/{name}")
    return calls


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("3.12", (3, 12)),
        ("3.11", (3, 11)),
        ("3.13", (3, 13)),
        ("3.12.7", (3, 12)),
        ("3.13.2", (3, 13)),
        ("3.14.0rc1", (3, 14)),
    ],
)
def test_parse_python_version(provision, text: str, expected: tuple[int, int]) -> None:
    """The parser reads major.minor from version strings."""
    assert provision.parse_python_version(text) == expected


def test_parse_python_version_rejects_garbage(provision) -> None:
    """Unparsable text raises ValueError, not a stack trace."""
    with pytest.raises(ValueError):
        provision.parse_python_version("not-a-version")
    with pytest.raises(ValueError):
        provision.parse_python_version("")


@pytest.mark.parametrize("version", [(3, 11), (3, 12), (3, 13)])
def test_supported_versions_are_accepted(provision, version: tuple[int, int]) -> None:
    """3.11, 3.12, and 3.13 pass the guard."""
    provision.ensure_supported_python(version)


@pytest.mark.parametrize("version", [(2, 7), (3, 9), (3, 10), (3, 14), (3, 15), (4, 0)])
def test_unsupported_versions_are_rejected(provision, version: tuple[int, int]) -> None:
    """Out-of-range versions fail with an actionable, named error."""
    with pytest.raises(provision.UnsupportedPythonError) as excinfo:
        provision.ensure_supported_python(version)
    message = str(excinfo.value)
    assert ">=3.11,<3.14" in message, "error must name the supported range"
    assert "3.11" in message and "3.13" in message, "error must name usable versions"


@pytest.mark.parametrize("engine", [*ENGINES, "core"])
def test_guard_matches_every_manifest(engine: str) -> None:
    """The guard's range must equal every engine (and core) manifest declaration."""
    folder = WORKERS_DIR / "core" if engine == "core" else WORKERS_DIR / "engines" / engine
    manifest = tomllib.loads((folder / "pyproject.toml").read_text(encoding="utf-8"))
    assert manifest["project"]["requires-python"] == ">=3.11,<3.14"


def test_available_engines_are_the_engine_folders(provision) -> None:
    """Every folder with a pyproject.toml under engines/ is an engine."""
    assert provision.available_engines() == sorted(ENGINES)


@pytest.mark.parametrize("name", ["nope", "../core", "", ".hidden"])
def test_unknown_engine_is_rejected_before_anything_runs(
    provision, recorded: list, capsys: pytest.CaptureFixture[str], name: str
) -> None:
    """An unknown or path-like name fails, listing the real engines."""
    assert provision.main([name]) == 1
    assert recorded == []
    err = capsys.readouterr().err
    assert "available engines: dots-mocr, paddleocr-vl" in err


def test_dots_mocr_without_the_flag_stops_before_uv_sync(
    provision, recorded: list, capsys: pytest.CaptureFixture[str]
) -> None:
    """Spec: dots-mocr refuses to provision without licence acceptance.

    Nothing runs, and the error names the licence file and the flag.
    """
    assert provision.main(["dots-mocr"]) == provision.EXIT_LICENCE_NOT_ACCEPTED
    assert recorded == [], "no command may run before the licence is accepted"
    err = capsys.readouterr().err
    assert str(WORKERS_DIR / "engines" / "dots-mocr" / "LICENCE-NOTES.md") in err
    assert "--accept-model-licence" in err


def test_dots_mocr_with_the_flag_syncs_then_fetches(provision, recorded: list) -> None:
    """With acceptance: locked sync in the engine folder, then the fetch script."""
    assert provision.main(["dots-mocr", "--accept-model-licence"]) == 0
    folder = WORKERS_DIR / "engines" / "dots-mocr"
    assert [call["command"] for call in recorded] == [
        ["uv", "sync", "--locked", "--python", "3.12"],
        [str(folder / ".venv" / "bin" / "omrg-ocr-fetch")],
    ]
    for call in recorded:
        assert call["cwd"] == folder
        assert call["env"]["UV_PROJECT"] == str(folder)
        assert call["env"]["UV_PROJECT_ENVIRONMENT"] == str(folder / ".venv")


def test_dry_run_installs_and_fetches_nothing(provision, recorded: list) -> None:
    """``--dry-run`` runs only ``uv sync --locked --dry-run``, never the fetch."""
    assert provision.main(["dots-mocr", "--accept-model-licence", "--dry-run"]) == 0
    assert [call["command"] for call in recorded] == [
        ["uv", "sync", "--locked", "--python", "3.12", "--dry-run"]
    ]


def test_paddle_needs_no_licence_flag_and_has_no_fetch(provision, recorded: list) -> None:
    """PaddleOCR-VL (Apache-2.0) provisions without the flag and fetches nothing."""
    assert provision.main(["paddleocr-vl", "--python", "3.13"]) == 0
    assert [call["command"] for call in recorded] == [
        ["uv", "sync", "--locked", "--python", "3.13"]
    ]
    assert recorded[0]["cwd"] == WORKERS_DIR / "engines" / "paddleocr-vl"


def test_unsupported_python_is_rejected_before_anything_runs(provision, recorded: list) -> None:
    """The Python range check runs before uv."""
    assert provision.main(["paddleocr-vl", "--python", "3.10"]) == 1
    assert recorded == []


def test_failed_sync_stops_before_the_fetch(provision, monkeypatch: pytest.MonkeyPatch) -> None:
    """A failing ``uv sync`` returns its status and never runs the fetch."""
    calls: list[list[str]] = []

    def failing_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        calls.append(list(command))
        return subprocess.CompletedProcess(command, 7)

    monkeypatch.setattr(provision.subprocess, "run", failing_run)
    monkeypatch.setattr(provision.shutil, "which", lambda name: f"/usr/bin/{name}")
    assert provision.main(["dots-mocr", "--accept-model-licence"]) == 7
    assert len(calls) == 1


def test_missing_uv_is_reported(provision, monkeypatch: pytest.MonkeyPatch) -> None:
    """Without uv on PATH the script stops with an install hint."""
    monkeypatch.setattr(provision.shutil, "which", lambda name: None)
    assert provision.main(["paddleocr-vl"]) == 1


def test_minimal_toml_reader_matches_tomllib(provision) -> None:
    """The fallback reader (for Python < 3.11) agrees on the fields it reads."""
    for engine in ENGINES:
        text = (WORKERS_DIR / "engines" / engine / "pyproject.toml").read_text(encoding="utf-8")
        full = tomllib.loads(text)
        minimal = provision._minimal_toml(text)
        assert provision.licence_gate(minimal) == provision.licence_gate(full)
        assert provision.has_fetch_script(minimal) == provision.has_fetch_script(full)


def test_provision_script_never_targets_the_repo_root(provision) -> None:
    """The provisioning working directories are engine folders only."""
    assert provision.WORKERS_DIR == WORKERS_DIR.resolve()
    assert provision.engine_dir("paddleocr-vl").parent == provision.ENGINES_DIR
    assert provision.WORKERS_DIR != REPO_ROOT
