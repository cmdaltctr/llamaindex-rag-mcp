"""Regression coverage: `omrg` is the only packaged console script.

Guards the v3 breaking change (`remove-rag-mcp-residue`) that deletes the
deprecated `rag-mcp` console-script alias: the distribution SHALL install
only `omrg`, and OMRG SHALL NOT provide a compatibility command or redirect
for a `rag-mcp` invocation.
"""

from __future__ import annotations

import sys
from importlib.metadata import entry_points
from pathlib import Path


def _omrg_console_scripts() -> dict[str, str]:
    """Return console-script entry points whose target is the OMRG CLI."""
    return {
        ep.name: ep.value
        for ep in entry_points(group="console_scripts")
        if ep.value.startswith("omrg.transports.cli")
    }


def test_omrg_is_the_only_packaged_console_script() -> None:
    """The distribution SHALL install `omrg` and SHALL NOT install `rag-mcp`."""
    scripts = _omrg_console_scripts()
    assert "omrg" in scripts
    assert "rag-mcp" not in scripts


def test_rag_mcp_invocation_does_not_resolve_in_this_environment() -> None:
    """`rag-mcp` SHALL NOT resolve inside this installation's own bin directory.

    Scoped to the interpreter running the tests, not the full system
    `PATH` — an unrelated global tool install (e.g. a stray `uv tool
    install rag-mcp` from a prior release) must not make this test flaky
    on a developer machine.
    """
    assert not (Path(sys.executable).parent / "rag-mcp").exists()
