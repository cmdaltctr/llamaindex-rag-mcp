"""MCP over HTTP end to end with the SDK's streamable HTTP client (tasks 4.5, 4.6).

A real web server runs on a loopback socket. The client sends the bearer
token. The tests cover the tool list, root-limited file paths, the shared
index and the shutdown order.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

import httpx
import httpx2
import pytest
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client
from tests.unit.test_web_mcp_http_support import (
    INITIALIZE,
    Live,
    enable_mcp,
    live_server,
    mcp_post,
)

pytest.importorskip("fastapi")

_SNAPSHOT = Path(__file__).resolve().parents[1] / "fixtures" / "mcp_tool_list.json"
_TEXT = "The quantum lantern array is calibrated at station one every Tuesday. " * 20


def _client(live: Live, token: str) -> Client:
    http = httpx2.AsyncClient(headers={"Authorization": f"Bearer {token}"}, timeout=60)
    return Client(streamable_http_client(live.mcp_url, http_client=http))


def _data(result: Any) -> Any:
    if getattr(result, "structured_content", None):
        return result.structured_content.get("result", result.structured_content)
    return json.loads(result.content[0].text)


def _wait_job(browser: httpx.Client, job_id: str) -> dict:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        job = browser.get(f"/v1/jobs/{job_id}").json()
        if job["status"] in {"completed", "failed"}:
            return job
        time.sleep(0.1)
    raise AssertionError("job did not finish")


@pytest.fixture
def roots(tmp_path: Path) -> tuple[Path, Path]:
    inside = tmp_path / "root"
    inside.mkdir()
    (inside / "lantern.txt").write_text(_TEXT, encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("outside the approved roots " * 20, encoding="utf-8")
    return inside, outside


async def test_http_serves_the_same_tools_as_stdio(tmp_path: Path) -> None:
    with live_server(tmp_path / "ws") as live:
        token = enable_mcp(live)
        async with _client(live, token) as client:
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
    assert json.loads(json.dumps(now, sort_keys=True)) == json.loads(_SNAPSHOT.read_text())


async def test_ingest_inside_a_root_search_it_and_refuse_a_path_outside(
    tmp_path: Path, roots: tuple[Path, Path]
) -> None:
    inside, outside = roots
    with live_server(tmp_path / "ws", roots=(inside,)) as live:
        token = enable_mcp(live)
        async with _client(live, token) as client:
            ingested = _data(
                await client.call_tool(
                    "ingest_documents", {"path": str(inside / "lantern.txt"), "collection": "e2e"}
                )
            )
            assert ingested["status"] == "ok", ingested

            hits = _data(
                await client.call_tool(
                    "search_documents",
                    {"query": "quantum lantern calibration", "collection": "e2e"},
                )
            )
            assert hits and "status" not in hits[0], hits
            assert "lantern" in hits[0]["text"]

            refused = _data(
                await client.call_tool(
                    "ingest_documents", {"path": str(outside / "secret.txt"), "collection": "e2e"}
                )
            )
            assert refused["status"] == "error"
            assert str(outside) not in json.dumps(refused)

            escape = inside / "link"
            escape.symlink_to(outside)
            via_symlink = _data(
                await client.call_tool(
                    "ingest_documents", {"path": str(escape / "secret.txt"), "collection": "e2e"}
                )
            )
            assert via_symlink["status"] == "error"

            mapped = await client.call_tool("get_codebase_map", {"path": str(outside)})
            assert json.loads(mapped.content[0].text)["status"] == "error"


async def test_a_document_ingested_through_v1_is_found_over_mcp_without_a_restart(
    tmp_path: Path, roots: tuple[Path, Path]
) -> None:
    inside, _ = roots
    with live_server(tmp_path / "ws", roots=(inside,)) as live:
        token = enable_mcp(live)
        browser = live.browser()
        async with _client(live, token) as client:
            before = _data(
                await client.call_tool("search_documents", {"query": "lantern", "collection": "w"})
            )
            assert before == [] or before[0].get("status") == "error" or not before

            job = browser.post(
                "/v1/ingestions", json={"path": str(inside / "lantern.txt"), "collection": "w"}
            ).json()
            assert _wait_job(browser, job["job_id"])["status"] == "completed"

            after = _data(
                await client.call_tool(
                    "search_documents",
                    {"query": "quantum lantern calibration", "collection": "w"},
                )
            )
            assert after and "status" not in after[0], after


async def test_tool_errors_over_http_carry_no_stack_trace(tmp_path: Path) -> None:
    with live_server(tmp_path / "ws") as live:
        token = enable_mcp(live)
        async with _client(live, token) as client:
            result = await client.call_tool(
                "delete_documents", {"metadata_filter": {}, "collection": "none"}
            )
    assert "Traceback" not in result.content[0].text


# ── 4.6 Shutdown order ───────────────────────────────────────────────────


async def test_a_running_tool_call_finishes_before_the_engine_closes(tmp_path: Path) -> None:
    from conftest import build_mcp_engine

    events: list[str] = []
    holder: dict[str, Any] = {}
    started = threading.Event()
    release = threading.Event()

    def factory() -> Any:
        engine = build_mcp_engine()
        real_close = engine.close

        def slow_search(*_args: Any, **_kwargs: Any) -> list[dict]:
            # The tool call must hold the runtime's admission, so shutdown waits.
            events.append(f"active={holder['live'].app.state.runtime.admission._active}")
            started.set()
            release.wait(timeout=30)
            events.append("search_done")
            return []

        def close() -> None:
            events.append("engine_closed")
            real_close()

        engine.search = slow_search
        engine.close = close
        return engine

    with live_server(tmp_path / "ws", engine_factory=factory) as live:
        holder["live"] = live
        token = enable_mcp(live)
        opened = mcp_post(live, token, INITIALIZE)
        session = {"Mcp-Session-Id": opened.headers["mcp-session-id"]}
        mcp_post(live, token, {"jsonrpc": "2.0", "method": "notifications/initialized"}, **session)
        call = {
            "jsonrpc": "2.0",
            "id": 9,
            "method": "tools/call",
            "params": {"name": "search_documents", "arguments": {"query": "x"}},
        }
        reply: dict[str, Any] = {}
        worker = threading.Thread(
            target=lambda: reply.setdefault("r", mcp_post(live, token, call, **session)),
            daemon=True,
        )
        worker.start()
        assert started.wait(timeout=30), "the tool call never reached the Engine"
        live.server.should_exit = True  # begin shutdown while the call runs
        time.sleep(0.3)
        assert "engine_closed" not in events  # the Engine stays open for the call
        assert events[0] == "active=1", events
        release.set()
        worker.join(timeout=30)
    assert reply["r"].status_code == 200
    assert events == ["active=1", "search_done", "engine_closed"], events
