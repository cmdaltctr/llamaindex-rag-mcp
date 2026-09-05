"""End-to-end smoke test: server over stdio transport.

Launches ``uv run omrg`` as a subprocess, performs MCP handshake,
and verifies tool discovery. Marked ``slow`` — skipped by default,
and skipped under CI: the probe only ever usefully runs against a
local checkout (GitHub-hosted runners have no Ollama, so the CI slow
step already exits early; the marker keeps that policy explicit if a
self-hosted Ollama runner ever appears).
"""

from __future__ import annotations

import json
import os
import subprocess
import time

import pytest

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        os.environ.get("CI") == "true",
        reason="stdio server probe runs locally only (uv run pytest -m slow)",
    ),
]


def test_stdio_server_lists_tools() -> None:
    """Launch the server over stdio and verify all tools are present."""
    proc = subprocess.Popen(
        ["uv", "run", "omrg"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        # MCP initialise handshake
        _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "0.0.1"},
                },
            },
        )

        # List tools
        response = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {},
            },
        )

        tool_names = {t["name"] for t in response["result"]["tools"]}
        assert tool_names == {
            "ingest_documents",
            "search_documents",
            "answer_documents",
            "list_indexed_documents",
            "list_collections",
            "delete_documents",
            "get_codebase_map",
            "change_collection_profile",
        }
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def _send(proc: subprocess.Popen, message: dict) -> dict:
    """Send a JSON-RPC message and read the response."""
    proc.stdin.write(json.dumps(message) + "\n")
    proc.stdin.flush()
    time.sleep(0.5)
    line = proc.stdout.readline()
    return json.loads(line)
