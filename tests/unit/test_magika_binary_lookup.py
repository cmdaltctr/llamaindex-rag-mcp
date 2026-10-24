"""Magika lookup when the app runs without its own scripts folder on PATH.

``magika`` is a base dependency, so ``uv tool install`` puts the ``magika``
program next to the app's Python. The login item starts ``omrs web`` with a
short PATH that does not hold that folder, so a PATH-only lookup reported
Magika as not installed on the Integrations page while it was there.
"""

from __future__ import annotations

import os
import stat
import types
from pathlib import Path

import pytest

from omrs.integrations import magika


def _program(folder: Path, name: str) -> Path:
    path = folder / name
    path.write_text("#!/bin/sh\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def _settings(binary: str = "magika") -> types.SimpleNamespace:
    return types.SimpleNamespace(magika_binary=binary)


@pytest.fixture
def scripts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A scripts folder for the running Python, and a PATH that does not hold it."""
    folder = tmp_path / "tool-bin"
    folder.mkdir()
    empty = tmp_path / "path-bin"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    monkeypatch.setattr(magika, "_scripts_folder", lambda: folder)
    return folder


def test_finds_magika_next_to_the_running_python_when_path_lacks_it(scripts: Path) -> None:
    program = _program(scripts, "magika")
    assert magika._is_magika_available(_settings())
    assert magika._resolve_magika(_settings()) == str(program)


def test_reports_magika_missing_when_neither_path_nor_scripts_hold_it(scripts: Path) -> None:
    assert not magika._is_magika_available(_settings())
    assert magika._resolve_magika(_settings()) is None


def test_prefers_the_program_on_path(
    scripts: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _program(scripts, "magika")
    on_path = tmp_path / "path-bin"
    found = _program(on_path, "magika")
    monkeypatch.setenv("PATH", str(on_path))
    assert magika._resolve_magika(_settings()) == str(found)


def test_a_configured_path_is_used_as_given(scripts: Path, tmp_path: Path) -> None:
    _program(scripts, "magika")
    custom = _program(tmp_path, "my-magika")
    assert magika._resolve_magika(_settings(str(custom))) == str(custom)
    assert magika._resolve_magika(_settings(str(tmp_path / "absent"))) is None


def test_scan_runs_the_program_it_found(scripts: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    program = _program(scripts, "magika")
    calls: list[list[str]] = []

    def fake_run(argv: list[str], **_: object) -> types.SimpleNamespace:
        calls.append(argv)
        return types.SimpleNamespace(stdout="", returncode=0)

    monkeypatch.setattr(magika.subprocess, "run", fake_run)
    magika.scan_with_magika(os.fspath(scripts), _settings())
    assert calls and calls[0][0] == str(program)
