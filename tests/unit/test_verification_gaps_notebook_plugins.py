"""Notebook trust notice text and its frontend copy (verification gap B).

The server shows one trust notice wherever an experiment or a notebook
editor is approved or opened. These tests pin the two warnings the spec
asks for (network permissions, and no operating-system sandbox), check
that every route uses the same constant, and tie the frontend test copy
to the server constant by reading the TypeScript source as text.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from omrg.transports.api import routes_experiments, routes_plugins  # noqa: E402

_REPO = Path(__file__).resolve().parents[2]
_FRONTEND_FIXTURE = _REPO / "web" / "src" / "experiments" / "test" / "experimentsServer.ts"
_FRONTEND_SOURCES = _REPO / "web" / "src"


def test_trust_notice_names_filesystem_network_and_no_sandbox() -> None:
    """The notice warns about filesystem and network access and the missing sandbox."""
    notice = routes_experiments.TRUST_NOTICE
    assert "filesystem" in notice
    assert "network" in notice
    assert "not an operating-system sandbox" in notice
    assert "Open only notebooks you trust." in notice


def test_plugin_routes_reuse_the_experiment_trust_notice() -> None:
    """Plugin and experiment routes return one notice object, not two copies."""
    assert routes_plugins.TRUST_NOTICE is routes_experiments.TRUST_NOTICE


def _typescript_constant(source: str, name: str) -> str:
    """Return the string value of ``export const <name> = "...";``."""
    match = re.search(rf'export const {name}\s*=\s*"((?:[^"\\]|\\.)*)";', source)
    assert match is not None, f"{name} not found"
    return match.group(1).replace('\\"', '"')


@pytest.mark.skipif(not _FRONTEND_FIXTURE.exists(), reason="frontend sources not present")
def test_frontend_trust_copy_matches_the_server_constant() -> None:
    """The Vitest fixture copy equals the server text, word for word."""
    source = _FRONTEND_FIXTURE.read_text(encoding="utf-8")
    assert _typescript_constant(source, "TRUST") == routes_experiments.TRUST_NOTICE


@pytest.mark.skipif(not _FRONTEND_SOURCES.exists(), reason="frontend sources not present")
def test_frontend_views_render_the_server_notice_instead_of_a_copy() -> None:
    """No production view hard-codes the notice; views show the server's text."""
    hard_coded = [
        path.relative_to(_REPO).as_posix()
        for path in sorted(_FRONTEND_SOURCES.rglob("*.ts*"))
        if "/test/" not in path.as_posix()
        and ".test." not in path.name
        and "operating-system sandbox" in path.read_text(encoding="utf-8")
    ]
    assert hard_coded == []
    view = (_FRONTEND_SOURCES / "experiments" / "ExperimentsView.tsx").read_text(encoding="utf-8")
    assert "trust_notice" in view
