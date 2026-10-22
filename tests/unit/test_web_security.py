"""Tests for local HTTP protection (task 6.2).

Covers loopback-only binding, Host and Origin checks, the one-time
bootstrap exchange, the session cookie, scoped and revocable bearer
credentials, stream-endpoint protection and credential redaction.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi import Depends  # noqa: E402
from fastapi.responses import StreamingResponse  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from omrs.transports.api.app import create_app  # noqa: E402
from omrs.transports.api.bind_address import validate_bind_host  # noqa: E402
from omrs.transports.api.lifespan import WebConfig  # noqa: E402
from omrs.transports.api.security import (  # noqa: E402
    BEARER_SCOPES,
    AccessPolicy,
    RedactingFilter,
    redact,
    require_scope,
)

BASE = "http://127.0.0.1:8765"
ORIGIN = {"Origin": BASE}


class FakeEngine:
    def close(self) -> None:
        return None


def _make(tmp_path: Path) -> tuple[Any, AccessPolicy]:
    config = WebConfig(workspace=tmp_path / "ws", host="127.0.0.1", port=8765, static_dir=None)
    policy = AccessPolicy.for_launch(config.host, config.port)
    app = create_app(config, policy=policy, engine_factory=FakeEngine)

    async def events() -> StreamingResponse:
        async def gen() -> Any:
            yield b"data: hello\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream")

    app.add_api_route(
        "/v1/probe/{run_id}/events",
        events,
        methods=["GET"],
        dependencies=[Depends(require_scope("read"))],
    )
    return app, policy


def _login(client: TestClient, policy: AccessPolicy) -> None:
    response = client.post(
        "/v1/session", json={"bootstrap": policy.bootstrap_secret}, headers=ORIGIN
    )
    assert response.status_code == 200, response.text


# ── Binding ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1", "127.0.0.2"])
def test_loopback_hosts_are_accepted(host: str) -> None:
    assert validate_bind_host(host)


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "10.0.0.5", "example.com", ""])  # noqa: S104
def test_remote_bind_is_rejected_with_explanation(host: str) -> None:
    with pytest.raises(ValueError, match="loopback"):
        validate_bind_host(host)


def test_create_app_rejects_remote_bind(tmp_path: Path) -> None:
    config = WebConfig(workspace=tmp_path, host="0.0.0.0", port=8765)  # noqa: S104
    with pytest.raises(ValueError, match="loopback"):
        create_app(config, engine_factory=FakeEngine)


# ── Host and Origin ──────────────────────────────────────────────────────


@pytest.mark.parametrize("host", ["evil.example:8765", "127.0.0.1:9999", "localhost.evil:8765"])
def test_invalid_host_header_is_rejected(tmp_path: Path, host: str) -> None:
    """DNS-rebinding style requests fail before any route runs."""
    app, _ = _make(tmp_path)
    with TestClient(app, base_url=BASE) as client:
        response = client.get("/v1/health", headers={"Host": host})
    assert response.status_code == 400
    assert response.json()["status"] == "error"


def test_localhost_host_header_is_accepted(tmp_path: Path) -> None:
    app, _ = _make(tmp_path)
    with TestClient(app, base_url="http://localhost:8765") as client:
        assert client.get("/v1/health").status_code == 200


def test_foreign_origin_cannot_submit_work_even_with_session(tmp_path: Path) -> None:
    """An unrelated web page is rejected before core work is admitted."""
    app, policy = _make(tmp_path)
    with TestClient(app, base_url=BASE) as client:
        _login(client, policy)
        response = client.post(
            "/v1/credentials", json={"scopes": ["read"]}, headers={"Origin": "http://evil.example"}
        )
        null_origin = client.post(
            "/v1/credentials", json={"scopes": ["read"]}, headers={"Origin": "null"}
        )
    assert response.status_code == 403
    assert null_origin.status_code == 403
    assert policy.list_bearers() == []


def test_cookie_post_without_origin_is_rejected(tmp_path: Path) -> None:
    """A cookie-authenticated state change must carry the app's Origin."""
    app, policy = _make(tmp_path)
    with TestClient(app, base_url=BASE) as client:
        _login(client, policy)
        response = client.post("/v1/credentials", json={"scopes": ["read"]})
    assert response.status_code == 403
    assert policy.list_bearers() == []


def test_same_site_fetch_metadata_is_rejected(tmp_path: Path) -> None:
    """Another localhost port is same-site; it must not reach the API."""
    app, policy = _make(tmp_path)
    with TestClient(app, base_url=BASE) as client:
        _login(client, policy)
        response = client.get("/v1/session", headers={"Sec-Fetch-Site": "same-site"})
    assert response.status_code == 403


# ── Bootstrap and session ────────────────────────────────────────────────


def test_bootstrap_exchanges_once_for_strict_httponly_cookie(tmp_path: Path) -> None:
    app, policy = _make(tmp_path)
    secret = policy.bootstrap_secret
    with TestClient(app, base_url=BASE) as client:
        first = client.post("/v1/session", json={"bootstrap": secret}, headers=ORIGIN)
        cookie = first.headers["set-cookie"]
        session = client.get("/v1/session")
        client.cookies.clear()
        second = client.post("/v1/session", json={"bootstrap": secret}, headers=ORIGIN)
    assert first.status_code == 200
    assert "httponly" in cookie.lower()
    assert "samesite=strict" in cookie.lower()
    assert "path=/" in cookie.lower()
    assert secret not in cookie
    assert session.status_code == 200
    assert session.json()["kind"] == "session"
    assert second.status_code == 401
    assert secret not in second.text


def test_wrong_bootstrap_is_rejected_and_not_echoed(tmp_path: Path) -> None:
    app, policy = _make(tmp_path)
    with TestClient(app, base_url=BASE) as client:
        response = client.post("/v1/session", json={"bootstrap": "omrs_bs_guess"}, headers=ORIGIN)
        after = client.post(
            "/v1/session", json={"bootstrap": policy.bootstrap_secret}, headers=ORIGIN
        )
    assert response.status_code == 401
    assert "omrs_bs_guess" not in response.text
    assert after.status_code == 200  # a failed guess does not burn the secret


def test_bootstrap_requires_matching_origin(tmp_path: Path) -> None:
    app, policy = _make(tmp_path)
    with TestClient(app, base_url=BASE) as client:
        response = client.post(
            "/v1/session",
            json={"bootstrap": policy.bootstrap_secret},
            headers={"Origin": "http://evil.example"},
        )
    assert response.status_code == 403


def test_secrets_in_query_string_never_authenticate(tmp_path: Path) -> None:
    app, policy = _make(tmp_path)
    token = policy.issue_bearer({"read"}).token
    with TestClient(app, base_url=BASE) as client:
        by_query = client.get(f"/v1/session?access_token={token}")
        by_bootstrap = client.get(f"/v1/session?bootstrap={policy.bootstrap_secret}")
        by_value = client.get(f"/v1/session?q={token}")
    for response in (by_query, by_bootstrap, by_value):
        assert response.status_code == 400
        assert token not in response.text
        assert policy.bootstrap_secret not in response.text


# ── Bearer credentials ───────────────────────────────────────────────────


def test_bearer_scopes_exclude_plugin_admin_and_file_grants() -> None:
    assert {"graph", "read", "run"} == set(BEARER_SCOPES)
    policy = AccessPolicy.for_launch("127.0.0.1", 8765)
    for forbidden in ("plugins", "files", "credentials"):
        with pytest.raises(ValueError):
            policy.issue_bearer({forbidden})


def test_bearer_scope_is_enforced(tmp_path: Path) -> None:
    app, policy = _make(tmp_path)
    run_only = policy.issue_bearer({"run"}).token
    reader = policy.issue_bearer({"read"}).token
    with TestClient(app, base_url=BASE) as client:
        denied = client.get("/v1/probe/r1/events", headers={"Authorization": f"Bearer {run_only}"})
        allowed = client.get("/v1/probe/r1/events", headers={"Authorization": f"Bearer {reader}"})
        roots = client.get("/v1/roots", headers={"Authorization": f"Bearer {reader}"})
        mint = client.post(
            "/v1/credentials",
            json={"scopes": ["read"]},
            headers={"Authorization": f"Bearer {reader}"},
        )
    assert denied.status_code == 403
    assert allowed.status_code == 200
    assert allowed.headers["content-type"].startswith("text/event-stream")
    assert roots.status_code == 403  # file grants are session-only
    assert mint.status_code == 403  # bearers cannot mint bearers


def test_stream_endpoint_rejects_missing_credentials(tmp_path: Path) -> None:
    """Run events use the same policy as run inspection."""
    app, _ = _make(tmp_path)
    with TestClient(app, base_url=BASE) as client:
        response = client.get("/v1/probe/r1/events")
    assert response.status_code == 401
    assert response.json()["status"] == "error"
    assert "bearer" in response.headers.get("www-authenticate", "").lower()


def test_session_mints_lists_and_revokes_bearer(tmp_path: Path) -> None:
    app, policy = _make(tmp_path)
    with TestClient(app, base_url=BASE) as client:
        _login(client, policy)
        created = client.post(
            "/v1/credentials", json={"scopes": ["read", "run"], "label": "nb"}, headers=ORIGIN
        )
        body = created.json()
        token = body["token"]
        listed = client.get("/v1/credentials").json()
        bad_scope = client.post("/v1/credentials", json={"scopes": ["plugins"]}, headers=ORIGIN)
        client.cookies.clear()
        before = client.get("/v1/session", headers={"Authorization": f"Bearer {token}"})
        policy.revoke_bearer(body["id"])
        after = client.get("/v1/session", headers={"Authorization": f"Bearer {token}"})
    assert created.status_code == 201
    assert sorted(body["scopes"]) == ["read", "run"]
    assert all("token" not in item for item in listed["credentials"])
    assert token not in str(listed)
    assert bad_scope.status_code == 400
    assert before.status_code == 200
    assert after.status_code == 401


def test_revoke_route_requires_session(tmp_path: Path) -> None:
    app, policy = _make(tmp_path)
    issued = policy.issue_bearer({"read"})
    with TestClient(app, base_url=BASE) as client:
        _login(client, policy)
        revoked = client.delete(f"/v1/credentials/{issued.id}", headers=ORIGIN)
        unknown = client.delete("/v1/credentials/nope", headers=ORIGIN)
    assert revoked.status_code == 200
    assert unknown.status_code == 404
    assert policy.authenticate_bearer(issued.token) is None


def test_unknown_api_path_with_session_is_json_404(tmp_path: Path) -> None:
    app, policy = _make(tmp_path)
    with TestClient(app, base_url=BASE) as client:
        _login(client, policy)
        response = client.get("/v1/nothing-here")
    assert response.status_code == 404
    assert response.json() == {"status": "error", "message": "Not Found"}


def test_every_protected_route_declares_a_scope(tmp_path: Path) -> None:
    """New ``/v1`` routes must state their scope (fail-closed review aid)."""
    app, _ = _make(tmp_path)
    from tests.unit.test_web_openapi_conformance_support import iter_api_routes

    public = {"/v1/health", "/v1/session"}
    checked = 0
    # FastAPI 0.143 wraps included routers; iter_api_routes flattens them, so
    # this loop sees the real routes (a bare ``app.routes`` loop saw none).
    for path, route in iter_api_routes(app):
        if not path.startswith("/v1") or path in public:
            continue
        calls = [dep.call for dep in route.dependant.dependencies]
        assert any(getattr(c, "omrs_scope", None) for c in calls), path
        checked += 1
    assert checked > 0, "no protected /v1 routes were inspected"


# ── Redaction ────────────────────────────────────────────────────────────


def test_redacting_filter_removes_every_credential_form() -> None:
    policy = AccessPolicy.for_launch("127.0.0.1", 8765)
    token = policy.issue_bearer({"read"}).token
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        "GET %s auth=%s cookie=%s",
        (f"/x#{policy.bootstrap_secret}", f"Bearer {token}", "omrs_ss_abcdef123456"),
        None,
    )
    assert RedactingFilter().filter(record)
    text = record.getMessage()
    assert policy.bootstrap_secret not in text
    assert token not in text
    assert "omrs_ss_abcdef123456" not in text
    assert "omrs_bt_***" in text


def test_two_keys_sharing_a_prefix_leave_no_fragment_of_either() -> None:
    old = "sk-or-v1-" + "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8"
    new = "sk-or-v1-" + "z9y8x7w6v5u4t3s2r1q0p9o8n7m6l5k4j3i2"
    for secret in (old, new):
        for cut in (12, 20, 30, len(secret) - 1):
            fragment = secret[:cut]
            text = redact(f"upstream echoed {fragment} here", [old, new])
            tail = fragment[9:]
            assert tail[:4] not in text, (cut, text)
            assert text == "upstream echoed *** here", (cut, text)
        assert secret not in redact(f"key={secret}", [old, new])


def test_redacting_filter_scrubs_tracebacks() -> None:
    try:
        raise RuntimeError("failed with omrs_bt_abc123.secretpart")
    except RuntimeError:
        import sys

        record = logging.LogRecord("x", logging.ERROR, __file__, 1, "boom", (), sys.exc_info())
    RedactingFilter().filter(record)
    assert record.exc_info is None
    assert "secretpart" not in record.getMessage()
    assert "RuntimeError" in record.getMessage()


def test_internal_errors_do_not_leak_details(tmp_path: Path) -> None:
    app, policy = _make(tmp_path)
    token = policy.issue_bearer({"read"}).token

    async def explode() -> None:
        raise RuntimeError(f"leaked {token}")

    app.add_api_route(
        "/v1/explode", explode, methods=["GET"], dependencies=[Depends(require_scope("read"))]
    )
    with TestClient(app, base_url=BASE, raise_server_exceptions=False) as client:
        response = client.get("/v1/explode", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 500
    assert response.json()["status"] == "error"
    assert token not in response.text
    assert "Traceback" not in response.text


def test_validation_errors_use_envelope_without_echoing_input(tmp_path: Path) -> None:
    """A malformed body gets a 400 envelope that names the field, not its value."""
    app, _ = _make(tmp_path)
    with TestClient(app, base_url=BASE) as client:
        response = client.post("/v1/session", json={"wrong": "omrs_bs_leak"}, headers=ORIGIN)
    assert response.status_code == 400
    body = response.json()
    assert body["status"] == "error"
    assert body["error_type"] == "validation"
    assert "bootstrap" in body["message"]
    assert "omrs_bs_leak" not in response.text


# ── Approved extra origins (--allow-origin) ──────────────────────────────

APPROVED = "http://wt.orca.localhost:57977"


def _make_approved(tmp_path: Path) -> tuple[Any, AccessPolicy]:
    config = WebConfig(workspace=tmp_path / "ws", host="127.0.0.1", port=8765, static_dir=None)
    policy = AccessPolicy.for_launch(config.host, config.port, extra_origins=[APPROVED])
    return create_app(config, policy=policy, engine_factory=FakeEngine), policy


def test_approved_origin_can_sign_in_and_submit_work(tmp_path: Path) -> None:
    app, policy = _make_approved(tmp_path)
    with TestClient(app, base_url=BASE) as client:
        login = client.post(
            "/v1/session", json={"bootstrap": policy.bootstrap_secret}, headers={"Origin": APPROVED}
        )
        created = client.post(
            "/v1/credentials", json={"scopes": ["read"]}, headers={"Origin": APPROVED}
        )
    assert login.status_code == 200
    assert "set-cookie" in login.headers
    assert created.status_code == 201


def test_unapproved_origin_is_still_rejected_beside_an_approved_one(tmp_path: Path) -> None:
    app, policy = _make_approved(tmp_path)
    other = {"Origin": "http://other.orca.localhost:57977"}
    secret = {"bootstrap": policy.bootstrap_secret}
    with TestClient(app, base_url=BASE) as client:
        login = client.post("/v1/session", json=secret, headers=other)
    assert login.status_code == 403


def test_origin_is_rejected_when_nothing_is_approved(tmp_path: Path) -> None:
    """With no flag the Orca origin gets the 403 it gets today."""
    app, policy = _make(tmp_path)
    with TestClient(app, base_url=BASE) as client:
        login = client.post(
            "/v1/session", json={"bootstrap": policy.bootstrap_secret}, headers={"Origin": APPROVED}
        )
    assert login.status_code == 403
    assert policy.allowed_origins == AccessPolicy.for_launch("127.0.0.1", 8765).allowed_origins


def test_approved_origin_does_not_relax_host_or_fetch_metadata(tmp_path: Path) -> None:
    app, policy = _make_approved(tmp_path)
    secret = {"bootstrap": policy.bootstrap_secret}
    with TestClient(app, base_url=BASE) as client:
        bad_host = client.post(
            "/v1/session", json=secret, headers={"Origin": APPROVED, "Host": "evil.example:8765"}
        )
        cross_site = client.post(
            "/v1/session",
            json=secret,
            headers={"Origin": APPROVED, "Sec-Fetch-Site": "cross-site"},
        )
    assert bad_host.status_code == 400
    assert cross_site.status_code == 403
    assert policy.allowed_hosts == AccessPolicy.for_launch("127.0.0.1", 8765).allowed_hosts


def test_policy_lists_approved_origin_for_the_mcp_sdk(tmp_path: Path) -> None:
    _, policy = _make_approved(tmp_path)
    assert APPROVED in policy.allowed_origins
    assert BASE in policy.allowed_origins


def test_policy_refuses_a_non_loopback_extra_origin() -> None:
    with pytest.raises(ValueError, match="loopback"):
        AccessPolicy.for_launch("127.0.0.1", 8765, extra_origins=["http://example.com"])


# ── SecretSet (design D7; task 6.2) ──────────────────────────────────────


def test_secret_set_is_append_only_and_hides_values_in_repr() -> None:
    from omrs.transports.api.security import RedactingFilter, SecretSet

    secrets = SecretSet(["first-secret-value", ""])
    secrets.add("second-secret-value")
    secrets.add("first-secret-value")
    secrets.add("")
    assert list(secrets) == ["first-secret-value", "second-secret-value"]
    assert "secret-value" not in repr(secrets)
    assert not hasattr(secrets, "remove") and not hasattr(secrets, "discard")
    log_filter = RedactingFilter(secrets)
    record = logging.LogRecord(
        "x", logging.INFO, __file__, 1, "key %s", ("late-added-secret-value",), None
    )
    log_filter.filter(record)
    assert "late-added-secret-value" in record.getMessage()
    secrets.add("late-added-secret-value")
    record = logging.LogRecord(
        "x", logging.INFO, __file__, 1, "key %s", ("late-added-secret-value",), None
    )
    log_filter.filter(record)
    assert record.getMessage() == "key ***"
