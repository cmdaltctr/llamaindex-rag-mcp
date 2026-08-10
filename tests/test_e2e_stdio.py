"""End-to-end smoke test: server over stdio transport.

Launches ``uv run rag-mcp`` as a subprocess, performs MCP handshake,
and verifies tool discovery. Marked ``slow`` — skipped by default.
"""

from __future__ import annotations

import json
import subprocess
import time

import pytest


@pytest.mark.slow
def test_stdio_server_lists_tools() -> None:
    """Launch the server over stdio and verify all tools are present."""
    proc = subprocess.Popen(
        ["uv", "run", "rag-mcp"],
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
            "list_indexed_documents",
            "list_collections",
            "delete_documents",
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
