"""Folder guides for agents (organise-backend-folders, design D12 and D13).

Ten folders carry a short ``AGENTS.md`` and a ``CLAUDE.md`` symbolic link to
it.  Claude Code reads a nested ``CLAUDE.md``; Codex and OpenCode read
``AGENTS.md``.  Each guide stays short and links back to the root
``AGENTS.md`` instead of repeating it.  The guides stay out of the wheel.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_ROOT_GUIDE = _REPO / "AGENTS.md"
_MAX_LINES = 40

_GUIDE_FOLDERS = [
    "src/omrg",
    "src/omrg/core",
    "src/omrg/core/vectordb",
    "src/omrg/core/retrieval",
    "src/omrg/core/ingestion",
    "src/omrg/core/pipelines",
    "src/omrg/transports",
    "src/omrg/integrations",
    "web/src",
    "tests",
]


@pytest.fixture(params=_GUIDE_FOLDERS)
def folder(request: pytest.FixtureRequest) -> Path:
    """Return one guide folder, with its path as the test id."""
    return _REPO / request.param


def test_folder_has_an_agents_guide(folder: Path) -> None:
    assert (folder / "AGENTS.md").is_file(), f"{folder.relative_to(_REPO)}/AGENTS.md is missing"


def test_claude_md_is_a_link_to_agents_md(folder: Path) -> None:
    link = folder / "CLAUDE.md"
    assert link.is_symlink(), f"{link.relative_to(_REPO)} must be a symbolic link"
    assert os.readlink(link) == "AGENTS.md"


def test_guide_stays_short(folder: Path) -> None:
    lines = (folder / "AGENTS.md").read_text(encoding="utf-8").splitlines()
    assert len(lines) <= _MAX_LINES, f"{folder.relative_to(_REPO)}/AGENTS.md has {len(lines)} lines"


def test_guide_links_back_to_the_root_guide(folder: Path) -> None:
    target = os.path.relpath(_ROOT_GUIDE, folder)
    text = (folder / "AGENTS.md").read_text(encoding="utf-8")
    assert f"]({target})" in text, f"{folder.relative_to(_REPO)}/AGENTS.md must link to {target}"


def test_wheel_excludes_the_guides() -> None:
    """Hatch ships every file under ``src/omrg``, so the guides need an ``exclude``."""
    config = tomllib.loads((_REPO / "pyproject.toml").read_text(encoding="utf-8"))
    wheel = config["tool"]["hatch"]["build"]["targets"]["wheel"]
    assert {"AGENTS.md", "CLAUDE.md"} <= set(wheel.get("exclude", []))
