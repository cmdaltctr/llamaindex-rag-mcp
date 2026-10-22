"""The MCP tools run on the lifespan Engine alone (design D1, D2).

With the process-default store and settings cleared, every tool still
works. A handler that reads either default would raise, so the test fails
if one does. A second test pins the tool list (names, descriptions,
annotations, input schemas) to the list taken before the refactor.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from conftest import build_mcp_server, connected_client
from omrs.core.settings import reset_default_effective_settings
from omrs.core.vectordb import reset_default_store

_SNAPSHOT = Path(__file__).resolve().parents[1] / "fixtures" / "mcp_tool_list.json"


def _data(result: Any) -> Any:
    if getattr(result, "structured_content", None):
        return result.structured_content.get("result", result.structured_content)
    return json.loads(result.content[0].text)


class _Llm:
    async def acomplete(self, prompt: str, **kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(text="The capital of France is Paris [1].")


async def test_every_tool_works_with_process_defaults_cleared(fixtures_dir: Path) -> None:
    server = build_mcp_server(answer_llm_factory=lambda: _Llm())
    # From here on, any read of a process default raises.
    reset_default_store()
    reset_default_effective_settings()
    with pytest.raises(RuntimeError):
        from omrs.core.vectordb import get_default_store

        get_default_store()

    async with connected_client(server) as client:
        ingested = _data(
            await client.call_tool(
                "ingest_documents", {"path": str(fixtures_dir), "collection": "np"}
            )
        )
        assert ingested["status"] == "ok", ingested

        hits = _data(
            await client.call_tool(
                "search_documents", {"query": "capital of France", "collection": "np"}
            )
        )
        assert isinstance(hits, list) and hits and "status" not in hits[0], hits

        answered = _data(
            await client.call_tool(
                "answer_documents",
                {"query": "capital of France", "collection": "np", "similarity_threshold": 0.0},
            )
        )
        assert answered["status"] == "ok", answered

        listed = _data(await client.call_tool("list_indexed_documents", {"collection": "np"}))
        assert listed and "status" not in listed[0], listed

        collections = _data(await client.call_tool("list_collections", {}))
        assert any(row["name"] == "np" for row in collections), collections

        preview = _data(
            await client.call_tool(
                "change_collection_profile", {"collection": "np", "profile": "codebase"}
            )
        )
        assert preview["status"] == "preview", preview

        dry = _data(
            await client.call_tool("delete_documents", {"collection": "np", "dry_run": True})
        )
        assert dry.get("status") != "error", dry

        mapped = await client.call_tool("get_codebase_map", {"path": str(fixtures_dir)})
        assert "Traceback" not in mapped.content[0].text
        assert '"status": "error"' not in mapped.content[0].text


async def test_tool_list_equals_the_pre_refactor_list(mcp_server) -> None:
    """Names, descriptions, annotations and input schemas are unchanged."""
    async with connected_client(mcp_server) as client:
        listed = await client.list_tools()
    now = sorted(
        (
            {
                "name": tool.name,
                "description": tool.description,
                "annotations": (
                    tool.annotations.model_dump(exclude_none=True) if tool.annotations else None
                ),
                "inputSchema": tool.input_schema,
            }
            for tool in listed.tools
        ),
        key=lambda row: row["name"],
    )
    expected = json.loads(_SNAPSHOT.read_text(encoding="utf-8"))
    assert json.loads(json.dumps(now, sort_keys=True)) == expected
