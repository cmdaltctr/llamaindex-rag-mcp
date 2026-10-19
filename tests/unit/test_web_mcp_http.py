"""MCP over HTTP: the gate, the state API and the token (tasks 4.2 to 4.4).

Each test runs the real web app on a loopback socket. Refusals must come
before any MCP processing, so a spy on the Engine proves no tool ran.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import httpx
import pytest
from tests.unit.test_web_mcp_http_support import (
    INITIALIZE,
    Live,
    enable_mcp,
    live_server,
    mcp_post,
)

pytest.importorskip("fastapi")

_TOOL_CALL = {
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {"name": "search_documents", "arguments": {"query": "x"}},
}


@pytest.fixture
def live(tmp_path: Path):
    with live_server(tmp_path / "ws") as server:
        yield server


def _spy_on_search(live: Live) -> list[int]:
    calls: list[int] = []
    real = live.engine.search

    def spy(*args: Any, **kwargs: Any) -> Any:
        calls.append(1)
        return real(*args, **kwargs)

    live.engine.search = spy
    return calls


# ── Off by default, then the gate order ──────────────────────────────────


def test_mcp_is_off_by_default_even_with_a_valid_looking_token(live: Live) -> None:
    assert mcp_post(live, None, INITIALIZE).status_code == 404
    assert mcp_post(live, "omrg_mcp_whatever", INITIALIZE).status_code == 404


def test_off_state_has_a_json_error_envelope(live: Live) -> None:
    body = mcp_post(live, None, INITIALIZE).json()
    assert body["status"] == "error"


def test_default_state_api_reports_off_without_a_token(live: Live) -> None:
    state = live.browser().get("/v1/mcp").json()
    assert state == {
        "status": "ok",
        "enabled": False,
        "url": live.mcp_url,
        "token": {"exists": False, "created_at": None},
    }


def test_missing_or_wrong_token_is_401_before_any_tool_runs(live: Live) -> None:
    token = enable_mcp(live)
    calls = _spy_on_search(live)

    assert mcp_post(live, None, _TOOL_CALL).status_code == 401
    assert mcp_post(live, "omrg_mcp_wrong", _TOOL_CALL).status_code == 401
    assert mcp_post(live, token + "x", _TOOL_CALL).status_code == 401
    assert mcp_post(live, None, _TOOL_CALL).headers["www-authenticate"].lower() == "bearer"
    assert calls == []


def test_foreign_origin_is_403_even_with_a_valid_token(live: Live) -> None:
    token = enable_mcp(live)
    calls = _spy_on_search(live)

    response = mcp_post(live, token, _TOOL_CALL, Origin="https://example.com")

    assert response.status_code == 403
    assert calls == []


def test_an_approved_origin_passes_the_gate_and_the_sdk_check(tmp_path: Path) -> None:
    """``--allow-origin`` reaches both the gate and the MCP SDK's own origin list."""
    approved = "http://wt.orca.localhost:57977"
    with live_server(tmp_path / "ws", extra_origins=(approved,)) as server:
        token = enable_mcp(server)
        accepted = mcp_post(server, token, INITIALIZE, Origin=approved)
        refused = mcp_post(server, token, INITIALIZE, Origin="http://other.orca.localhost:57977")
    assert accepted.status_code == 200, accepted.text
    assert refused.status_code == 403


def test_an_absent_origin_passes_the_gate(live: Live) -> None:
    token = enable_mcp(live)
    response = mcp_post(live, token, INITIALIZE)
    assert response.status_code == 200, response.text


def test_the_gate_order_is_off_then_origin_then_token(live: Live) -> None:
    foreign = {"Origin": "https://example.com"}
    assert mcp_post(live, None, INITIALIZE, **foreign).status_code == 404  # off first
    enable_mcp(live, token=False)
    assert mcp_post(live, None, INITIALIZE, **foreign).status_code == 403  # origin before token
    assert mcp_post(live, None, INITIALIZE).status_code == 401


def test_a_rebound_host_header_is_refused(live: Live) -> None:
    token = enable_mcp(live)
    response = mcp_post(live, token, INITIALIZE, Host="evil.example:80")
    assert response.status_code in (400, 421)


def test_the_exact_path_answers_without_a_redirect(live: Live) -> None:
    enable_mcp(live, token=False)
    response = httpx.post(live.mcp_url, json=INITIALIZE, follow_redirects=False)
    assert response.status_code == 401  # not a 307 to /mcp/


# ── State changes ────────────────────────────────────────────────────────


def test_enable_and_token_survive_a_restart(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    with live_server(workspace) as first:
        token = enable_mcp(first)
    with live_server(workspace) as second:
        state = second.browser().get("/v1/mcp").json()
        assert state["enabled"] is True
        assert state["token"]["exists"] is True
        assert mcp_post(second, token, INITIALIZE).status_code == 200


def test_turning_mcp_off_ends_an_open_session(live: Live) -> None:
    token = enable_mcp(live)
    opened = mcp_post(live, token, INITIALIZE)
    session = opened.headers.get("mcp-session-id")
    assert opened.status_code == 200
    follow_up = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    headers = {"Mcp-Session-Id": session} if session else {}
    assert mcp_post(live, token, follow_up, **headers).status_code in (200, 202)

    assert live.browser().put("/v1/mcp", json={"enabled": False}).json()["enabled"] is False

    assert mcp_post(live, token, _TOOL_CALL, **headers).status_code == 404


def test_put_returns_the_stored_state(live: Live) -> None:
    browser = live.browser()
    on = browser.put("/v1/mcp", json={"enabled": True}).json()
    assert on["enabled"] is True and on["url"] == live.mcp_url
    assert browser.get("/v1/mcp").json()["enabled"] is True


@pytest.mark.parametrize("body", [{}, {"enabled": "yes"}, {"enabled": None}, {"on": True}])
def test_put_rejects_a_bad_body(live: Live, body: dict) -> None:
    response = live.browser().put("/v1/mcp", json=body)
    assert response.status_code == 400
    assert live.browser().get("/v1/mcp").json()["enabled"] is False


# ── The token ────────────────────────────────────────────────────────────


def test_the_token_is_shown_once(live: Live) -> None:
    browser = live.browser()
    created = browser.post("/v1/mcp/token")
    assert created.status_code in (200, 201)
    body = created.json()
    assert body["token"].startswith("omrg_mcp_")
    assert re.fullmatch(r".*T.*", body["created_at"])
    state = browser.get("/v1/mcp")
    assert body["token"] not in state.text
    assert state.json()["token"] == {"exists": True, "created_at": body["created_at"]}


def test_rotation_refuses_the_old_token(live: Live) -> None:
    old = enable_mcp(live)
    new = live.browser().post("/v1/mcp/token").json()["token"]
    assert new != old
    assert mcp_post(live, old, INITIALIZE).status_code == 401
    assert mcp_post(live, new, INITIALIZE).status_code == 200


def test_revoking_the_token_refuses_it(live: Live) -> None:
    token = enable_mcp(live)
    browser = live.browser()
    assert browser.delete("/v1/mcp/token").status_code in (200, 204)
    assert mcp_post(live, token, INITIALIZE).status_code == 401
    assert browser.get("/v1/mcp").json()["token"] == {"exists": False, "created_at": None}


def test_bearer_credentials_cannot_change_mcp(live: Live) -> None:
    token = enable_mcp(live)
    issued = live.policy.issue_bearer({"graph", "read", "run"})
    auth = {"Authorization": f"Bearer {issued.token}"}
    for method, path, body in (
        ("PUT", "/v1/mcp", {"enabled": False}),
        ("POST", "/v1/mcp/token", None),
        ("DELETE", "/v1/mcp/token", None),
    ):
        response = httpx.request(method, live.base + path, json=body, headers=auth)
        assert response.status_code == 403, (method, path, response.text)
    assert mcp_post(live, token, INITIALIZE).status_code == 200  # nothing changed


def test_a_bearer_with_read_scope_can_read_the_state(live: Live) -> None:
    issued = live.policy.issue_bearer({"read"})
    response = httpx.get(live.base + "/v1/mcp", headers={"Authorization": f"Bearer {issued.token}"})
    assert response.status_code == 200
    assert "token" in response.json()


_PUBLIC = {"/v1/health", "/v1/session"}


def _api_routes() -> list[tuple[str, str]]:
    from omrg.transports.api.app import API_ROUTERS

    found = []
    for router in API_ROUTERS:
        for route in router.routes:
            path = getattr(route, "path", "")
            if not path.startswith("/v1") or path in _PUBLIC:
                continue
            for method in getattr(route, "methods", None) or ():
                if method in {"GET", "POST", "PUT", "DELETE", "PATCH"}:
                    found.append((method, re.sub(r"\{[^}]+\}", "x", path)))
    return sorted(set(found))


def test_the_mcp_token_is_refused_on_every_v1_route(live: Live) -> None:
    token = enable_mcp(live)
    routes = _api_routes()
    assert len(routes) > 20  # the sweep really covers the API
    for method, path in routes:
        response = httpx.request(
            method,
            live.base + path,
            headers={"Authorization": f"Bearer {token}"},
            json={} if method in {"POST", "PUT", "PATCH"} else None,
        )
        assert response.status_code == 401, (method, path, response.status_code)


def test_the_browser_session_cannot_call_mcp(live: Live) -> None:
    enable_mcp(live, token=False)
    browser = live.browser()
    response = browser.post(
        "/mcp",
        json=INITIALIZE,
        headers={"Accept": "application/json, text/event-stream"},
    )
    assert response.status_code == 401


# ── 4.4 Log redaction ────────────────────────────────────────────────────


def test_redact_removes_an_mcp_token() -> None:
    from omrg.integrations.workspace_sqlite.tokens import MCP_TOKEN_PREFIX
    from omrg.transports.api.security import redact

    token = MCP_TOKEN_PREFIX + "AbC-123_xyz.-"
    cleaned = redact(f"failed with {token} and Authorization: Bearer {token}")
    assert "AbC-123" not in cleaned
    assert MCP_TOKEN_PREFIX in cleaned  # the prefix stays, so the line stays readable


def test_the_logging_filter_removes_a_logged_mcp_token() -> None:
    import logging

    from omrg.transports.api.security import RedactingFilter

    token = "omrg_mcp_" + "Zq9-secret_value"
    record = logging.LogRecord("omrg", logging.WARNING, __file__, 1, "bad token %s", (token,), None)
    RedactingFilter().filter(record)
    assert "secret_value" not in record.getMessage()
