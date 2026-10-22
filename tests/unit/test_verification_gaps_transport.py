"""Transport-separation gaps from the verification report (section B).

* ``omrs`` with no arguments starts the MCP server only: no web server,
  no socket, no notebook editor, and no web or workspace modules.
* The parameters and annotations of all eight MCP tools match a snapshot
  taken from the ``v3`` branch (commit ``3ca82a0``), so the web work
  changed no MCP tool contract.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any
from unittest.mock import patch

from typer.testing import CliRunner

from conftest import connected_client
from omrs.transports.cli import app as cli_app

#: Modules that only ``omrs web`` or the notebook editor may load. The workspace
#: modules (``omrs.core.workspace``, ``omrs.integrations.workspace_sqlite``) are
#: not listed: the stdio server reads the default workspace catalogue (D11).
_WEB_ONLY_MODULES = (
    "fastapi",
    "marimo",
    "omrs.transports.api",
    "omrs.core.plugins",
    "omrs.integrations.process_launcher",
)

_REQUIRED = "<required>"

#: name -> (parameter defaults, required parameters, annotations), from v3.
_V3_TOOLS: dict[str, tuple[dict[str, Any], list[str], dict[str, bool]]] = {
    "answer_documents": (
        {
            "collection": "documents",
            "diagnostics": False,
            "expand_window": 0,
            "hybrid": None,
            "metadata_filter": None,
            "query": _REQUIRED,
            "rerank": None,
            "similarity_threshold": None,
            "top_k": None,
        },
        ["query"],
        {"destructiveHint": False, "readOnlyHint": True},
    ),
    "change_collection_profile": (
        {"collection": _REQUIRED, "confirm": False, "profile": _REQUIRED},
        ["collection", "profile"],
        {"destructiveHint": True, "readOnlyHint": False},
    ),
    "delete_documents": (
        {"collection": "documents", "dry_run": False, "metadata_filter": None, "path": None},
        [],
        {"destructiveHint": True, "readOnlyHint": False},
    ),
    "get_codebase_map": (
        {"path": ".", "refresh": False},
        [],
        {"destructiveHint": False, "readOnlyHint": True},
    ),
    "ingest_documents": (
        {"collection": "documents", "path": _REQUIRED},
        ["path"],
        {"destructiveHint": True, "readOnlyHint": False},
    ),
    "list_collections": ({}, [], {"destructiveHint": False, "readOnlyHint": True}),
    "list_indexed_documents": (
        {"collection": "documents"},
        [],
        {"destructiveHint": False, "readOnlyHint": True},
    ),
    # Added after v3 (unify-profiles-and-pipelines, task 8.4).
    "list_profiles": ({}, [], {"destructiveHint": False, "readOnlyHint": True}),
    "search_documents": (
        {
            "collection": "documents",
            "diagnostics": False,
            "expand_window": 0,
            "hybrid": None,
            "metadata_filter": None,
            "query": _REQUIRED,
            "rerank": None,
            "similarity_threshold": None,
            "top_k": None,
        },
        ["query"],
        {"destructiveHint": False, "readOnlyHint": True},
    ),
}


# ── No-argument start ────────────────────────────────────────────────────


def test_no_argument_start_never_calls_the_web_server() -> None:
    """``omrs`` with no arguments runs MCP and never binds or serves HTTP."""
    with (
        patch("omrs.transports.mcp.compose.build_engine"),
        patch("omrs.transports.mcp.create_mcp_server") as factory,
        patch("omrs.transports.cli.web._serve") as serve,
        patch("omrs.transports.cli.web._bind_socket") as bind,
        patch("logging.basicConfig"),
    ):
        result = CliRunner().invoke(cli_app, [])
    assert result.exit_code == 0, result.output
    factory.return_value.run.assert_called_once()
    serve.assert_not_called()
    bind.assert_not_called()


def test_no_argument_entry_point_loads_no_web_or_editor_modules(tmp_path: Path) -> None:
    """The ``omrs`` console entry point, run in a clean process, imports no web code."""
    script = textwrap.dedent(
        f"""
        import json, sys
        from unittest.mock import patch
        with (
            patch("omrs.transports.mcp.compose.build_engine"),
            patch("omrs.transports.mcp.create_mcp_server") as factory,
        ):
            from omrs.transports.cli import run_cli
            sys.argv = ["omrs"]
            try:
                run_cli()
            except SystemExit as exc:
                code = exc.code
            else:
                code = 0
        loaded = [m for m in {list(_WEB_ONLY_MODULES)!r} if m in sys.modules]
        runs = factory.return_value.run.call_count
        print(json.dumps({{"code": code, "mcp_runs": runs, "loaded": loaded}}))
        """
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env=dict(os.environ),
        timeout=120,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout.strip().splitlines()[-1])
    assert report == {"code": 0, "mcp_runs": 1, "loaded": []}


# ── MCP tool contract ────────────────────────────────────────────────────


def _tool_contract(tool: Any) -> tuple[dict[str, Any], list[str], dict[str, bool]]:
    schema = tool.input_schema
    required = list(schema.get("required", []))
    defaults = {
        name: prop.get("default", _REQUIRED if name in required else "<no default>")
        for name, prop in schema.get("properties", {}).items()
    }
    assert tool.annotations is not None, tool.name
    annotations = tool.annotations.model_dump(by_alias=True, exclude_none=True)
    annotations.pop("title", None)
    return defaults, sorted(required), annotations


async def test_every_mcp_tool_keeps_its_v3_parameters_and_annotations(mcp_server: Any) -> None:
    """Each tool's parameters, defaults, required set and safety hints are unchanged."""
    async with connected_client(mcp_server) as client:
        listed = await client.list_tools()

    contracts = {tool.name: _tool_contract(tool) for tool in listed.tools}
    assert sorted(contracts) == sorted(_V3_TOOLS)
    for name, expected in _V3_TOOLS.items():
        assert contracts[name] == expected, name
