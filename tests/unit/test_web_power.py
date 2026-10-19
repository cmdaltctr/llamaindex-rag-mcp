"""Route tests for ``GET`` and ``POST /v1/server/power`` (``add-web-power-menu`` 2.3).

Each test follows one scenario of the ``web-login-item`` spec delta. A fake
runner records the argv, so no test runs ``launchctl``. The ASGI app is
wrapped once to see when the response body leaves, which pins that the
server acts after it answers.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_web_documents_support import (  # noqa: E402
    BASE,
    ORIGIN,
    bearer,
    lance_store,
    login,
    make_engine,
)
from tests.unit.test_web_openapi_conformance_support import FAMILIES, ContractChecker  # noqa: E402

from omrg.transports.api.app import create_app  # noqa: E402
from omrg.transports.api.lifespan import WebConfig  # noqa: E402
from omrg.transports.api.power_control import PowerControl  # noqa: E402
from omrg.transports.api.security import AccessPolicy  # noqa: E402

LABEL = "com.omrg.web"
UID = 501
URL = "/v1/server/power"


class Recorder:
    """Records the order of ASGI sends and runner calls."""

    def __init__(self) -> None:
        self.events: list[str] = []
        self.argvs: list[list[str]] = []

    def runner(self, argv: list[str]) -> int:
        self.events.append("run")
        self.argvs.append(argv)
        return 0


class Harness:
    """The app, its policy, a recorder and the wrapped ASGI callable."""

    def __init__(self, app: Any, policy: AccessPolicy, recorder: Recorder) -> None:
        self.app = app
        self.policy = policy
        self.recorder = recorder

    async def asgi(self, scope: Any, receive: Any, send: Any) -> None:
        async def spy(message: Any) -> None:
            if message["type"] == "http.response.body" and not message.get("more_body"):
                self.recorder.events.append("sent")
            await send(message)

        await self.app(scope, receive, spy if scope["type"] == "http" else send)

    def manage(self) -> None:
        """Make this launch the login item with a fake runner and no delay."""
        self.app.state.power_control = PowerControl(
            label=LABEL, uid=UID, runner=self.recorder.runner, delay=0
        )


@pytest.fixture
def harness(tmp_path: Path, effective_settings: Any) -> Iterator[Harness]:
    engine = make_engine(lance_store(tmp_path), effective_settings())
    config = WebConfig(workspace=tmp_path / "ws", port=8765, static_dir=None)
    policy = AccessPolicy.for_launch(config.host, config.port)
    app = create_app(config, policy=policy, engine_factory=lambda: engine)
    yield Harness(app, policy, Recorder())


@pytest.fixture
def client(harness: Harness) -> Iterator[TestClient]:
    with TestClient(harness.asgi, base_url=BASE) as test_client:
        login(test_client, harness.policy)
        yield test_client


# ── Managed or not ───────────────────────────────────────────────────────


def test_get_answers_managed_true_for_the_login_item(harness: Harness, client: TestClient) -> None:
    harness.manage()
    body = client.get(URL).json()
    assert body["managed"] is True


def test_foreground_server_is_not_managed_and_signals_nothing(
    harness: Harness, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[Any] = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append(a))
    assert client.get(URL).json()["managed"] is False
    for action in ("restart", "off"):
        response = client.post(URL, json={"action": action}, headers=ORIGIN)
        assert response.status_code == 409, action
        assert response.json()["status"] == "error"
    assert calls == [] and harness.recorder.argvs == []


# ── Authorisation ────────────────────────────────────────────────────────


def test_a_bearer_credential_is_refused_and_signals_nothing(
    harness: Harness, client: TestClient
) -> None:
    harness.manage()
    client.cookies.clear()
    header = bearer(harness.policy, "read", "graph", "run")
    assert client.get(URL, headers=header).status_code == 403
    refused = client.post(URL, json={"action": "off"}, headers={**ORIGIN, **header})
    assert refused.status_code == 403
    assert refused.json()["status"] == "error"
    assert harness.recorder.argvs == []


def test_no_credential_is_unauthorised(harness: Harness, client: TestClient) -> None:
    harness.manage()
    client.cookies.clear()
    assert client.get(URL).status_code == 401
    assert client.post(URL, json={"action": "off"}, headers=ORIGIN).status_code == 401
    assert harness.recorder.argvs == []


# ── Body ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("action", ["sleep", "", "OFF", "restart ", "off;rm"])
def test_an_unknown_action_is_422_and_signals_nothing(
    harness: Harness, client: TestClient, action: str
) -> None:
    harness.manage()
    response = client.post(URL, json={"action": action}, headers=ORIGIN)
    assert response.status_code == 422, action
    assert response.json()["status"] == "error"
    assert harness.recorder.argvs == []


@pytest.mark.parametrize(
    "content",
    [{"action": 3}, {"action": None}, {}, {"action": "off", "extra": 1}, ["off"], "off"],
)
def test_a_body_of_the_wrong_shape_is_400_and_signals_nothing(
    harness: Harness, client: TestClient, content: Any
) -> None:
    harness.manage()
    response = client.post(URL, json=content, headers=ORIGIN)
    assert response.status_code == 400, content
    assert harness.recorder.argvs == []


def test_a_body_that_is_not_json_is_400(harness: Harness, client: TestClient) -> None:
    harness.manage()
    response = client.post(
        URL, content=b"not json", headers={**ORIGIN, "Content-Type": "application/json"}
    )
    assert response.status_code == 400
    assert harness.recorder.argvs == []


def test_an_unknown_action_is_refused_before_the_managed_check(
    harness: Harness, client: TestClient
) -> None:
    """A foreground server still reports a bad action as 422."""
    response = client.post(URL, json={"action": "sleep"}, headers=ORIGIN)
    assert response.status_code == 422


# ── Work in progress ─────────────────────────────────────────────────────


def test_admitted_work_blocks_the_action(harness: Harness, client: TestClient) -> None:
    harness.manage()
    runtime = harness.app.state.runtime
    held = runtime.admission.enter()
    client.portal.call(held.__aenter__)
    try:
        response = client.post(URL, json={"action": "off"}, headers=ORIGIN)
    finally:
        client.portal.call(held.__aexit__, None, None, None)
    assert response.status_code == 409
    message = response.json()["message"]
    assert message and "\n" not in message
    assert harness.recorder.argvs == []
    # With the work finished the same request is accepted.
    assert client.post(URL, json={"action": "off"}, headers=ORIGIN).status_code == 202


@pytest.mark.parametrize(
    "service",
    [
        SimpleNamespace(active_run_id="run_1", waiting_count=0),
        SimpleNamespace(active_run_id=None, waiting_count=2),
    ],
    ids=["active-run", "waiting-run"],
)
def test_an_active_or_waiting_run_blocks_the_action(
    harness: Harness, client: TestClient, service: Any
) -> None:
    harness.manage()
    runtime = harness.app.state.runtime
    original = runtime.run_service
    runtime.run_service = SimpleNamespace(service=service)
    try:
        response = client.post(URL, json={"action": "restart"}, headers=ORIGIN)
    finally:
        runtime.run_service = original
    assert response.status_code == 409
    assert harness.recorder.argvs == []


def test_an_idle_run_service_does_not_block(harness: Harness, client: TestClient) -> None:
    harness.manage()
    runtime = harness.app.state.runtime
    original = runtime.run_service
    idle = SimpleNamespace(active_run_id=None, waiting_count=0)
    runtime.run_service = SimpleNamespace(service=idle)
    try:
        response = client.post(URL, json={"action": "restart"}, headers=ORIGIN)
    finally:
        runtime.run_service = original
    assert response.status_code == 202


# ── Accepted ─────────────────────────────────────────────────────────────


def test_restart_answers_202_and_sends_sigterm(harness: Harness, client: TestClient) -> None:
    harness.manage()
    response = client.post(URL, json={"action": "restart"}, headers=ORIGIN)
    assert response.status_code == 202
    assert response.json() == {"status": "ok", "action": "restart"}
    assert harness.recorder.argvs == [["launchctl", "kill", "SIGTERM", f"gui/{UID}/{LABEL}"]]


def test_off_answers_202_and_boots_the_agent_out(harness: Harness, client: TestClient) -> None:
    harness.manage()
    response = client.post(URL, json={"action": "off"}, headers=ORIGIN)
    assert response.status_code == 202
    assert response.json() == {"status": "ok", "action": "off"}
    assert harness.recorder.argvs == [["launchctl", "bootout", f"gui/{UID}/{LABEL}"]]


def test_the_runner_runs_after_the_response_was_sent(harness: Harness, client: TestClient) -> None:
    harness.manage()
    client.post(URL, json={"action": "restart"}, headers=ORIGIN)
    events = harness.recorder.events
    assert "run" in events
    assert events.index("sent") < events.index("run")


def test_a_runner_failure_after_the_response_does_not_change_it(
    harness: Harness, client: TestClient
) -> None:
    def failing(argv: list[str]) -> int:
        raise RuntimeError("launchctl missing")

    harness.app.state.power_control = PowerControl(label=LABEL, uid=UID, runner=failing, delay=0)
    response = client.post(URL, json={"action": "off"}, headers=ORIGIN)
    assert response.status_code == 202


# ── Contract ─────────────────────────────────────────────────────────────


def test_power_responses_conform(harness: Harness, client: TestClient) -> None:
    check = ContractChecker()
    check.check(client.get(URL), 200)
    check.check(client.post(URL, json={"action": "off"}, headers=ORIGIN), 409)
    harness.manage()
    assert check.check(client.get(URL), 200)["managed"] is True
    check.check(client.post(URL, json={"action": "sleep"}, headers=ORIGIN), 422)
    check.check(client.post(URL, json={"action": "restart"}, headers=ORIGIN), 202)
    held = harness.app.state.runtime.admission.enter()
    client.portal.call(held.__aenter__)
    try:
        check.check(client.post(URL, json={"action": "off"}, headers=ORIGIN), 409)
    finally:
        client.portal.call(held.__aexit__, None, None, None)
    client.cookies.clear()
    read = bearer(harness.policy, "read")
    check.check(client.get(URL, headers=read), 403)
    check.check(client.post(URL, json={"action": "off"}, headers={**ORIGIN, **read}), 403)
    check.check(client.get(URL), 401)
    check.check(client.post(URL, json={"action": "off"}, headers=ORIGIN), 401)
    assert check.operations >= FAMILIES["power"]
