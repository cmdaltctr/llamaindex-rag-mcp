"""``/v1/llamacpp/server`` routes: settings, scopes, lifecycle and shutdown (Part B.4).

A fake ``llama-server`` stands in for the real one. The keychain is a fake in
memory and no real provider is contacted.
"""

from __future__ import annotations

import json
import os
import signal
import sys
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from tests.unit import test_web_connections_edit as edit  # noqa: E402
from tests.unit.llamacpp_fake import (  # noqa: E402
    FakeServerProgram,
    free_port,
    install_fake,
    wait_until,
)
from tests.unit.test_web_openapi_conformance_support import (  # noqa: E402
    FAMILIES,
    ContractChecker,
)

from omrg.transports.api import security  # noqa: E402
from omrg.transports.api.llamacpp_server import LlamacppServer  # noqa: E402

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX process groups")

harness = edit.harness
ORIGIN = edit.ORIGIN
URL = "/v1/llamacpp/server"


class Rig:
    """One app, its fake program and its manager."""

    def __init__(self, h: Any, program: FakeServerProgram, model: Path, port: int) -> None:
        self.h, self.program, self.model, self.port = h, program, model, port
        self.client = h.client

    def get(self) -> dict[str, Any]:
        response = self.client.get(URL)
        assert response.status_code == 200, response.text
        return response.json()

    def put(self, body: dict[str, Any]) -> Any:
        return self.client.put(URL, json=body, headers=ORIGIN)

    def post(self, action: str) -> Any:
        return self.client.post(f"{URL}/{action}", headers=ORIGIN)

    def save_all(self, **extra: Any) -> None:
        body = {"binary": str(self.program.path), "model": str(self.model), "context_window": 4096}
        response = self.put({**body, **extra})
        assert response.status_code == 200, response.text

    def wait_state(self, state: str) -> dict[str, Any]:
        wait_until(lambda: self.get()["state"] == state)
        return self.get()


@pytest.fixture
def rig(harness: Any, tmp_path: Path):
    """Return a factory: ``with rig(**settings) as r``."""
    from contextlib import contextmanager

    @contextmanager
    def build(mode: str = "ok", **overrides: Any):
        program = install_fake(tmp_path / "bin", mode)
        model = tmp_path / "model.gguf"
        model.write_bytes(b"GGUF")
        port = free_port()
        overrides.setdefault("llamacpp_chat_url", f"http://127.0.0.1:{port}/v1")
        with harness(**overrides) as h:
            manager = LlamacppServer(
                tmp_path / "ws" / "llamacpp-server.log",
                health_timeout=20.0,
                stop_grace=3.0,
                poll_interval=0.05,
            )
            h.app.state.llamacpp_server = manager
            state = Rig(h, program, model, port)
            try:
                yield state
            finally:
                for pid in program.pids():
                    try:
                        os.killpg(pid, signal.SIGKILL)
                    except (ProcessLookupError, PermissionError):
                        pass

    return build


# ── GET shape and defaults ───────────────────────────────────────────────


def test_the_default_status(rig: Any) -> None:
    with rig() as r:
        body = r.get()
        assert (body["state"], body["reason"], body["exit_code"]) == ("stopped", None, None)
        assert (body["pid_running"], body["running_with"], body["pending_restart"]) == (
            False,
            None,
            False,
        )
        saved = body["saved"]
        assert set(saved) == {"binary", "model", "context_window", "idle_sleep"}
        assert (saved["binary"]["value"], saved["binary"]["source"]) == ("", "default")
        window = saved["context_window"]
        assert (window["value"], window["source"], window["locked"]) == (16384, "default", False)
        assert (window["min"], window["max"]) == (2048, 262144)


def test_get_needs_read_and_a_read_bearer_can_see_it(rig: Any) -> None:
    with rig() as r:
        r.client.cookies.clear()
        assert r.client.get(URL).status_code == 401
        header = edit.bearer(r.h.policy, "read")
        assert r.client.get(URL, headers=header).status_code == 200


# ── PUT ──────────────────────────────────────────────────────────────────


def test_save_all_three_then_read_them_with_source_saved(rig: Any) -> None:
    with rig() as r:
        r.save_all()
        saved = r.get()["saved"]
        assert saved["binary"]["value"] == str(r.program.path)
        assert saved["model"]["value"] == str(r.model)
        assert saved["context_window"]["value"] == 4096
        assert {saved[k]["source"] for k in ("binary", "model", "context_window")} == {"saved"}


def test_a_null_clears_a_saved_value(rig: Any) -> None:
    with rig() as r:
        r.save_all()
        assert r.put({"model": None}).status_code == 200
        saved = r.get()["saved"]
        assert (saved["model"]["value"], saved["model"]["source"]) == ("", "default")
        assert saved["binary"]["source"] == "saved"


@pytest.mark.parametrize(
    "bad",
    ["relative/zz-marker/llama-server", "/bin/sh", "/no/such/zz-marker/llama-server", ""],
)
def test_a_bad_program_is_400_and_saves_nothing(rig: Any, bad: str) -> None:
    with rig() as r:
        response = r.put({"binary": bad})
        assert response.status_code == 400
        message = response.json()["message"]
        assert "llama-server" in message
        assert bad == "" or bad not in message
        assert r.get()["saved"]["binary"]["source"] == "default"


@pytest.mark.parametrize(
    "bad", ["--api-key", "-m", "a b", "zz-marker/", "../zz-marker", "/no/such/model.gguf", ""]
)
def test_a_bad_model_is_400_and_saves_nothing(rig: Any, bad: str) -> None:
    with rig() as r:
        response = r.put({"model": bad})
        assert response.status_code == 400
        assert "gguf" in response.json()["message"]
        assert bad == "" or bad not in response.json()["message"]
        assert r.get()["saved"]["model"]["source"] == "default"


def test_an_oversize_value_is_400(rig: Any) -> None:
    with rig() as r:
        assert r.put({"model": "x" * 3000}).status_code == 400
        assert r.put({"binary": "/" + "x" * 3000}).status_code == 400


def test_hugging_face_ids_are_saved(rig: Any) -> None:
    with rig() as r:
        assert r.put({"model": "Qwen/Qwen3-0.6B-GGUF:Q8_0"}).status_code == 200
        assert r.get()["saved"]["model"]["value"] == "Qwen/Qwen3-0.6B-GGUF:Q8_0"


@pytest.mark.parametrize("bad", [1000, 2047, 262145, "abc", 16384.5, True])
def test_a_bad_window_is_400(rig: Any, bad: Any) -> None:
    with rig() as r:
        response = r.put({"context_window": bad})
        assert response.status_code == 400
        assert "2048" in response.json()["message"]
        assert r.get()["saved"]["context_window"]["source"] == "default"


@pytest.mark.parametrize("extra", ["args", "extra_args", "port", "host", "env"])
def test_no_other_field_is_accepted(rig: Any, extra: str) -> None:
    with rig() as r:
        response = r.put({"context_window": 4096, extra: ["--api-key", "x"]})
        assert response.status_code == 400
        assert r.get()["saved"]["context_window"]["source"] == "default"


def test_an_empty_body_is_400(rig: Any) -> None:
    with rig() as r:
        assert r.put({}).status_code == 400


# ── Locks ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("field", "variable", "body"),
    [
        ("llamacpp_server_binary", "LLAMACPP_SERVER_BINARY", {"binary": "{program}"}),
        ("llamacpp_server_model", "LLAMACPP_SERVER_MODEL", {"model": "{model}"}),
        ("llamacpp_context_window", "LLAMACPP_CONTEXT_WINDOW", {"context_window": 4096}),
    ],
)
def test_an_environment_value_locks_the_field_and_names_the_variable(
    rig: Any, field: str, variable: str, body: dict[str, Any]
) -> None:
    with rig(explicit=frozenset({field})) as r:
        sent = {
            k: v.format(program=r.program.path, model=r.model) if isinstance(v, str) else v
            for k, v in body.items()
        }
        response = r.put(sent)
        assert response.status_code == 409
        assert variable in response.json()["message"]
        key = {"binary": "binary", "model": "model", "context_window": "context_window"}
        entry = r.get()["saved"][key[next(iter(body))]]
        assert (entry["locked"], entry["source"]) == (True, "env")


def test_a_config_file_value_locks_the_field(rig: Any) -> None:
    from omrg import compose

    with rig(explicit=frozenset({"llamacpp_context_window"})) as r:
        # make_settings restates the sources, so the test restates what omrg.jsonc set.
        settings = compose.get_settings()
        object.__setattr__(settings, "config_file_fields", frozenset({"llamacpp_context_window"}))
        object.__setattr__(settings, "user_config_dir", "/home/u/.config/omrg")
        response = r.put({"context_window": 4096})
        assert response.status_code == 409
        assert "omrg.jsonc" in response.json()["message"]
        assert r.get()["saved"]["context_window"]["source"] == "config-file"


# ── Scopes ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("put", "", {"context_window": 4096}),
        ("post", "/start", None),
        ("post", "/stop", None),
        ("post", "/restart", None),
    ],
)
def test_a_bearer_token_never_writes_or_controls(
    rig: Any, method: str, path: str, body: Any
) -> None:
    with rig() as r:
        r.client.cookies.clear()
        header = {**edit.bearer(r.h.policy, "read", "graph", "run")}
        kwargs: dict[str, Any] = {"headers": header}
        if body is not None:
            kwargs["json"] = body
        response = getattr(r.client, method)(URL + path, **kwargs)
        assert response.status_code == 403


def test_changing_the_program_or_model_needs_the_credentials_scope(
    rig: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    with rig() as r:
        monkeypatch.setattr(security, "SESSION_SCOPES", security.SESSION_SCOPES - {"credentials"})
        assert r.put({"model": str(r.model)}).status_code == 403
        assert r.put({"binary": str(r.program.path)}).status_code == 403
        assert r.put({"context_window": 8192, "model": str(r.model)}).status_code == 403
        saved = r.get()["saved"]
        assert (saved["binary"]["source"], saved["model"]["source"]) == ("default", "default")
        assert saved["context_window"]["source"] == "default"
        assert r.put({"context_window": 8192}).status_code == 200
        assert r.post("stop").status_code == 200


def test_the_window_and_the_controls_need_manage(rig: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    with rig() as r:
        monkeypatch.setattr(security, "SESSION_SCOPES", security.SESSION_SCOPES - {"manage"})
        assert r.put({"context_window": 8192}).status_code == 403
        assert r.post("start").status_code == 403


# ── Lifecycle through the routes ─────────────────────────────────────────


def test_start_pending_restart_restart_and_stop(rig: Any) -> None:
    with rig() as r:
        r.save_all()
        started = r.post("start")
        assert started.status_code == 200
        assert started.json()["state"] in ("starting", "running")
        body = r.wait_state("running")
        assert body["pid_running"] is True
        assert body["running_with"] == {"context_window": 4096, "model_kind": "file"}
        assert body["pending_restart"] is False
        assert r.program.argv()[-2:] == ["-c", "4096"]
        first = r.program.pids()[-1]

        assert r.put({"context_window": 8192}).status_code == 200
        body = r.get()
        assert (body["state"], body["pending_restart"]) == ("running", True)
        assert r.program.pids()[-1] == first  # a save keeps the server running

        restarted = r.post("restart")
        assert restarted.status_code == 200
        body = r.wait_state("running")
        assert body["pending_restart"] is False
        assert r.program.argv()[-2:] == ["-c", "8192"]
        assert r.program.pids()[-1] != first

        stopped = r.post("stop").json()
        assert (stopped["state"], stopped["pid_running"], stopped["running_with"]) == (
            "stopped",
            False,
            None,
        )


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({}, "not-configured"),
        ({"llamacpp_chat_url": "http://192.168.1.20:8081/v1"}, "not-loopback"),
    ],
)
def test_a_refused_start_is_failed_with_a_fixed_reason(
    rig: Any, overrides: dict[str, Any], reason: str
) -> None:
    with rig(**overrides) as r:
        if reason != "not-configured":
            r.save_all()
        response = r.post("start")
        assert response.status_code == 200
        body = response.json()
        assert (body["state"], body["reason"]) == ("failed", reason)
        assert r.program.pids() == []


def test_a_server_that_exits_reports_the_code_and_never_its_text(rig: Any) -> None:
    with rig(mode="exit:3") as r:
        r.save_all()
        r.post("start")
        body = r.wait_state("failed")
        assert (body["reason"], body["exit_code"]) == ("exited", 3)
        wait_until(
            lambda: "SECRET-CHILD-TEXT" in (r.h.app.state.llamacpp_server.log_path).read_text()
        )
        assert "SECRET-CHILD-TEXT" not in json.dumps(body)
        logs = r.client.get("/v1/logs")
        assert "SECRET-CHILD-TEXT" not in logs.text
        assert "SECRET-CHILD-TEXT" not in r.client.get(URL).text


def test_leaving_the_app_stops_the_owned_server(rig: Any) -> None:
    pid = 0
    program = None
    with rig() as r:
        r.save_all()
        r.post("start")
        r.wait_state("running")
        pid, program = r.program.pids()[-1], r.program
    assert program is not None
    wait_until(lambda: not _alive(pid))


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def test_the_responses_conform_to_the_contract(rig: Any) -> None:
    check = ContractChecker()
    with rig() as r:
        check.check(r.client.get(URL), 200)
        check.check(r.put({"context_window": 1000}), 400)
        check.check(r.put({"binary": "relative"}), 400)
        check.check(r.put({"context_window": 4096}), 200)
        r.save_all()
        check.check(r.client.get(URL), 200)
        check.check(r.post("start"), 200)
        r.wait_state("running")
        check.check(r.post("restart"), 200)
        r.wait_state("running")
        check.check(r.post("stop"), 200)
    assert check.operations >= FAMILIES["llamacpp_server"]


def test_the_routes_start_no_process_themselves() -> None:
    source = (
        Path(__file__).parents[2] / "src/omrg/transports/api/routes/llamacpp_server.py"
    ).read_text(encoding="utf-8")
    assert "subprocess" not in source
    assert "os.kill" not in source


# ── Idle sleep (task 17.9) ───────────────────────────────────────────────


def test_idle_sleep_defaults_to_300_and_is_passed_at_start(rig: Any) -> None:
    with rig() as r:
        sleep = r.get()["saved"]["idle_sleep"]
        assert (sleep["value"], sleep["source"], sleep["min"], sleep["max"]) == (
            300,
            "default",
            0,
            86400,
        )
        r.save_all()
        assert r.post("start").status_code == 200
        r.wait_state("running")
        argv = r.program.argv()
        assert argv[argv.index("--sleep-idle-seconds") + 1] == "300"


def test_idle_sleep_zero_sends_no_flag_and_a_change_needs_a_restart(rig: Any) -> None:
    with rig() as r:
        r.save_all(idle_sleep=0)
        assert r.post("start").status_code == 200
        body = r.wait_state("running")
        assert "--sleep-idle-seconds" not in r.program.argv()
        assert body["pending_restart"] is False
        assert r.put({"idle_sleep": 120}).status_code == 200
        assert r.get()["pending_restart"] is True
        assert r.post("restart").status_code == 200
        r.wait_state("running")
        argv = r.program.argv()
        assert argv[argv.index("--sleep-idle-seconds") + 1] == "120"


@pytest.mark.parametrize("bad", [-1, 86401, "soon", 1.5])
def test_an_idle_sleep_out_of_range_is_400(rig: Any, bad: object) -> None:
    with rig() as r:
        assert r.put({"idle_sleep": bad}).status_code == 400
        assert r.get()["saved"]["idle_sleep"]["source"] == "default"
