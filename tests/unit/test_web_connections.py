"""Provider connections over HTTP: ``GET /v1/connections`` and the test action (7.1, 7.2).

Settings are built in memory (no ``.env``) and patched into the
composition root. The test action talks to local fake servers on loopback
ports. No real provider, model or cloud request happens. A test result
holds ``reachable`` and a ``reason`` from a fixed set; it never holds a
response body or exception text.
"""

from __future__ import annotations

import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_connection_summary import SECRET, make_settings  # noqa: E402
from tests.unit.test_web_documents_support import (  # noqa: E402
    BASE,
    ORIGIN,
    bearer,
    build_app,
    lance_store,
    login,
    make_engine,
)
from tests.unit.test_web_openapi_conformance_support import FAMILIES, ContractChecker  # noqa: E402

import omrg.core.providers.llm.openrouter as openrouter_llm  # noqa: E402
from omrg import compose  # noqa: E402
from omrg.transports.api import connection_probe  # noqa: E402

BODY_MARKER = "BODY-MARKER-do-not-return"


class FakeProvider:
    """A loopback HTTP server with a status and delay for each path."""

    def __init__(self) -> None:
        self.responses: dict[str, tuple[int, float]] = {}
        self.seen: list[tuple[str, str | None]] = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                owner.seen.append((self.path, self.headers.get("Authorization")))
                status, delay = owner.responses.get(self.path, (404, 0.0))
                time.sleep(delay)
                body = BODY_MARKER.encode()
                try:
                    self.send_response(status)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except OSError:
                    pass  # the client gave up (timeout test)

            def log_message(self, *args: Any) -> None:
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(
            target=self.server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True
        )
        self.thread.start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def fake() -> Any:
    server = FakeProvider()
    yield server
    server.close()


def refused_url() -> str:
    """Return a loopback URL that nothing listens on."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return f"http://127.0.0.1:{sock.getsockname()[1]}"


@pytest.fixture(autouse=True)
def no_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")


@pytest.fixture
def configure(monkeypatch: pytest.MonkeyPatch) -> Any:
    def apply(**overrides: Any) -> Any:
        settings = make_settings(**overrides)
        monkeypatch.setattr(compose, "get_settings", lambda: settings)
        return settings

    return apply


@pytest.fixture
def setup(tmp_path: Path, effective_settings: Any, configure: Any):
    configure()
    engine = make_engine(lance_store(tmp_path), effective_settings())
    app, policy = build_app(tmp_path, engine)
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        yield client, policy


def run_test(client: TestClient, provider: str) -> Any:
    return client.post(f"/v1/connections/{provider}/test", headers=ORIGIN)


# ── GET /v1/connections ──────────────────────────────────────────────────


def test_connections_response_shape(setup: Any, configure: Any) -> None:
    client, _ = setup
    configure(openrouter_api_key=SECRET)
    response = client.get("/v1/connections")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ok"
    assert body["config_dir"] == str(Path.cwd())
    assert [c["provider"] for c in body["connections"]] == [
        "ollama",
        "llamacpp",
        "openrouter",
        "openai_compatible",
        "anthropic",
    ]
    key = next(f for f in body["connections"][2]["fields"] if f["id"] == "api_key")
    assert key["set"] is True and key["source"] == "keychain"
    assert body["keychain"] == "unavailable"


def test_no_key_value_in_any_response(setup: Any, configure: Any, fake: FakeProvider) -> None:
    client, policy = setup
    configure(openrouter_api_key=SECRET)
    texts = [client.get("/v1/connections").text]
    texts.append(run_test(client, "openrouter").text)
    texts.append(run_test(client, "ollama").text)
    client.cookies.clear()
    texts.append(client.get("/v1/connections", headers=bearer(policy, "read")).text)
    texts.append(client.get("/v1/connections").text)
    for text in texts:
        assert SECRET not in text
        assert SECRET[:10] not in text


def test_connections_needs_read_scope(setup: Any) -> None:
    client, policy = setup
    client.cookies.clear()
    assert client.get("/v1/connections").status_code == 401
    assert client.get("/v1/connections", headers=bearer(policy, "graph")).status_code == 403
    assert client.get("/v1/connections", headers=bearer(policy, "read")).status_code == 200


def test_opening_connections_sends_no_provider_request(
    setup: Any, monkeypatch: pytest.MonkeyPatch, configure: Any
) -> None:
    client, _ = setup
    configure(openrouter_api_key=SECRET)

    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("a provider request was sent without a Test action")

    monkeypatch.setattr(connection_probe.httpx, "AsyncClient", forbidden)
    assert client.get("/v1/connections").status_code == 200
    assert client.get("/v1/integrations").status_code == 200


# ── POST /v1/connections/{provider}/test ─────────────────────────────────


def test_ollama_reachable_uses_api_tags(setup: Any, configure: Any, fake: FakeProvider) -> None:
    client, _ = setup
    configure(ollama_base_url=fake.url + "/")
    fake.responses["/api/tags"] = (200, 0.0)
    response = run_test(client, "ollama")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "reachable": True, "reason": None}
    assert fake.seen == [("/api/tags", None)]
    assert BODY_MARKER not in response.text


def test_refused(setup: Any, configure: Any) -> None:
    client, _ = setup
    configure(ollama_base_url=refused_url())
    assert run_test(client, "ollama").json() == {
        "status": "ok",
        "reachable": False,
        "reason": "refused",
    }


def test_timeout(
    setup: Any, configure: Any, fake: FakeProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = setup
    configure(ollama_base_url=fake.url)
    fake.responses["/api/tags"] = (200, 1.5)
    monkeypatch.setattr(connection_probe, "TEST_TIMEOUT_SECONDS", 0.2)
    started = time.monotonic()
    body = run_test(client, "ollama").json()
    assert body == {"status": "ok", "reachable": False, "reason": "timeout"}
    assert time.monotonic() - started < 1.4


def test_the_timeout_is_five_seconds() -> None:
    assert connection_probe.TEST_TIMEOUT_SECONDS == 5.0


@pytest.mark.parametrize(
    ("status", "reason"),
    [(401, "unauthorised"), (403, "unauthorised"), (404, "http-404"), (500, "http-500")],
)
def test_error_statuses(
    setup: Any, configure: Any, fake: FakeProvider, status: int, reason: str
) -> None:
    client, _ = setup
    configure(ollama_base_url=fake.url)
    fake.responses["/api/tags"] = (status, 0.0)
    response = run_test(client, "ollama")
    assert response.json() == {"status": "ok", "reachable": False, "reason": reason}
    assert BODY_MARKER not in response.text


def test_a_redirect_is_an_http_error_not_followed(
    setup: Any, configure: Any, fake: FakeProvider
) -> None:
    client, _ = setup
    configure(ollama_base_url=fake.url)
    fake.responses["/api/tags"] = (302, 0.0)
    assert run_test(client, "ollama").json()["reason"] == "http-302"


def test_llamacpp_tests_each_configured_url(setup: Any, configure: Any, fake: FakeProvider) -> None:
    client, _ = setup
    configure(llamacpp_embed_url=fake.url + "/v1", llamacpp_chat_url=fake.url + "/chat/v1")
    fake.responses["/v1/models"] = (200, 0.0)
    fake.responses["/chat/v1/models"] = (200, 0.0)
    assert run_test(client, "llamacpp").json()["reachable"] is True
    assert [path for path, _ in fake.seen] == ["/v1/models", "/chat/v1/models"]
    fake.responses["/chat/v1/models"] = (503, 0.0)
    failed = run_test(client, "llamacpp").json()
    assert (failed["reachable"], failed["reason"]) == (False, "http-503")


def test_llamacpp_with_one_url_down_is_refused(
    setup: Any, configure: Any, fake: FakeProvider
) -> None:
    client, _ = setup
    configure(llamacpp_embed_url=fake.url + "/v1", llamacpp_chat_url=refused_url() + "/v1")
    fake.responses["/v1/models"] = (200, 0.0)
    body = run_test(client, "llamacpp").json()
    assert (body["reachable"], body["reason"]) == (False, "refused")


def test_openrouter_sends_the_key_to_the_fixed_base_and_never_returns_it(
    setup: Any, configure: Any, fake: FakeProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = setup
    configure(openrouter_api_key=SECRET)
    monkeypatch.setattr(openrouter_llm, "_OPENROUTER_API_BASE", fake.url + "/api/v1")
    fake.responses["/api/v1/key"] = (200, 0.0)
    response = run_test(client, "openrouter")
    assert response.json() == {"status": "ok", "reachable": True, "reason": None}
    assert fake.seen == [("/api/v1/key", f"Bearer {SECRET}")]
    fake.responses["/api/v1/key"] = (401, 0.0)
    rejected = run_test(client, "openrouter")
    assert rejected.json()["reason"] == "unauthorised"
    assert SECRET not in rejected.text


@pytest.mark.parametrize(
    ("provider", "overrides"),
    [
        ("openrouter", {}),
        ("ollama", {"ollama_base_url": "   "}),
        ("llamacpp", {"llamacpp_embed_url": "", "llamacpp_chat_url": " "}),
    ],
)
def test_not_configured_sends_nothing(
    setup: Any,
    configure: Any,
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
    overrides: dict[str, str],
) -> None:
    client, _ = setup
    configure(**overrides)

    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("a request was sent for a provider that is not configured")

    monkeypatch.setattr(connection_probe.httpx, "AsyncClient", forbidden)
    assert run_test(client, provider).json() == {
        "status": "ok",
        "reachable": False,
        "reason": "not-configured",
    }


def test_exception_text_is_never_returned(
    setup: Any, configure: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = setup
    configure(ollama_base_url="http://127.0.0.1:9", openrouter_api_key=SECRET)

    class Boom:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> Boom:
            return self

        async def __aexit__(self, *exc: object) -> None:
            return None

        def stream(self, *args: Any, **kwargs: Any) -> Any:
            raise connection_probe.httpx.ConnectError(f"connect failed for key {SECRET}")

    monkeypatch.setattr(connection_probe.httpx, "AsyncClient", Boom)
    response = run_test(client, "ollama")
    assert response.json() == {"status": "ok", "reachable": False, "reason": "refused"}
    assert "connect failed" not in response.text and SECRET not in response.text


def test_unknown_provider_is_404(setup: Any) -> None:
    client, _ = setup
    response = run_test(client, "mystery")
    assert response.status_code == 404 and response.json()["status"] == "error"


def test_test_action_is_session_only_with_manage_scope(setup: Any, fake: FakeProvider) -> None:
    client, policy = setup
    client.cookies.clear()
    header = bearer(policy, "read", "graph", "run")
    assert client.post("/v1/connections/ollama/test", headers=header).status_code == 403
    assert client.post("/v1/connections/ollama/test", headers=ORIGIN).status_code == 401
    assert fake.seen == []


def test_test_action_needs_the_application_origin(setup: Any) -> None:
    client, _ = setup
    response = client.post("/v1/connections/ollama/test", headers={"Origin": "http://evil.example"})
    assert response.status_code == 403


def test_connection_responses_conform(setup: Any, configure: Any, fake: FakeProvider) -> None:
    client, policy = setup
    configure(ollama_base_url=fake.url, openrouter_api_key=SECRET)
    fake.responses["/api/tags"] = (200, 0.0)
    check = ContractChecker()
    check.check(client.get("/v1/connections"), 200)
    check.check(run_test(client, "ollama"), 200)
    check.check(run_test(client, "openrouter"), 200)
    check.check(run_test(client, "mystery"), 404)
    # Default settings let Ollama make embeddings, so its address is locked.
    body = {"fields": {"base_url": "http://gpu.test:11434"}}
    check.check(client.put("/v1/connections/ollama", json=body, headers=ORIGIN), 409)
    check.check(client.put("/v1/connections/mystery", json=body, headers=ORIGIN), 404)
    check.check(
        client.put("/v1/connections/ollama", json={"fields": {"base_url": "x"}}, headers=ORIGIN),
        400,
    )
    key = {"api_key": "k" * 20}
    check.check(client.put("/v1/connections/openrouter/key", json=key, headers=ORIGIN), 409)
    check.check(client.delete("/v1/connections/openrouter/key", headers=ORIGIN), 409)
    models = client.post("/v1/connections/ollama/models", headers=ORIGIN)
    check.check(models, 200)
    client.cookies.clear()
    read = bearer(policy, "read")
    check.check(client.get("/v1/connections", headers=read), 200)
    check.check(client.post("/v1/connections/ollama/test", headers=read), 403)
    check.check(client.get("/v1/connections"), 401)
    assert check.operations >= FAMILIES["connections"]
