"""Tests for ``scripts/check_web_wheel.py``, the release wheel asset gate.

The script fails release preparation when a wheel cannot serve the web
workspace. These tests build small zip files that stand in for wheels.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import zipfile
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_web_wheel.py"
_STATIC = "omrg/transports/api/static/"
_INDEX_HTML = (
    "<!doctype html><html><head>"
    '<script type="module" src="./assets/index-abc.js"></script>'
    '<link rel="stylesheet" href="./assets/index-def.css">'
    "</head><body></body></html>"
)


def _load_script() -> ModuleType:
    """Import the script as a module without putting ``scripts/`` on the path."""
    spec = importlib.util.spec_from_file_location("check_web_wheel", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check_web_wheel = _load_script()


def _wheel(tmp_path: Path, members: dict[str, str]) -> Path:
    """Write a zip file with the given members and return its path."""
    path = tmp_path / "omrg-0.0.0-py3-none-any.whl"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("omrg/__init__.py", "")
        for name, text in members.items():
            archive.writestr(name, text)
    return path


def _complete_members() -> dict[str, str]:
    return {
        _STATIC + "index.html": _INDEX_HTML,
        _STATIC + "assets/index-abc.js": "console.log(1);",
        _STATIC + "assets/index-def.css": "body{}",
    }


def test_complete_wheel_passes(tmp_path: Path) -> None:
    wheel = _wheel(tmp_path, _complete_members())

    assert check_web_wheel.check_wheel(str(wheel)) == []
    assert check_web_wheel.main([str(wheel)]) == 0


def test_wheel_without_index_fails_with_build_instruction(tmp_path: Path) -> None:
    members = _complete_members()
    del members[_STATIC + "index.html"]
    wheel = _wheel(tmp_path, members)

    problems = check_web_wheel.check_wheel(str(wheel))

    assert len(problems) == 1
    assert "missing omrg/transports/api/static/index.html" in problems[0]
    assert "npm run build" in problems[0]
    assert check_web_wheel.main([str(wheel)]) == 1


def test_wheel_missing_a_referenced_asset_fails_and_names_it(tmp_path: Path) -> None:
    members = _complete_members()
    del members[_STATIC + "assets/index-def.css"]
    wheel = _wheel(tmp_path, members)

    problems = check_web_wheel.check_wheel(str(wheel))

    assert problems == [
        f"{wheel}: {_STATIC}index.html references missing {_STATIC}assets/index-def.css"
    ]
    assert check_web_wheel.main([str(wheel)]) == 1


def test_index_that_references_no_assets_fails(tmp_path: Path) -> None:
    wheel = _wheel(tmp_path, {_STATIC + "index.html": "<html></html>"})

    problems = check_web_wheel.check_wheel(str(wheel))

    assert len(problems) == 1
    assert "references no ./assets/ files" in problems[0]


def test_main_without_arguments_prints_usage(capsys: pytest.CaptureFixture[str]) -> None:
    assert check_web_wheel.main([]) == 2
    assert "usage:" in capsys.readouterr().err


def test_command_line_exit_code_follows_the_check(tmp_path: Path) -> None:
    good = _wheel(tmp_path, _complete_members())
    bad_dir = tmp_path / "bad"
    bad_dir.mkdir()
    bad = _wheel(bad_dir, {})

    ok = subprocess.run([sys.executable, str(_SCRIPT), str(good)], capture_output=True, text=True)
    failed = subprocess.run(
        [sys.executable, str(_SCRIPT), str(good), str(bad)], capture_output=True, text=True
    )

    assert ok.returncode == 0, ok.stderr
    assert failed.returncode == 1
    assert "missing omrg/transports/api/static/index.html" in failed.stderr
