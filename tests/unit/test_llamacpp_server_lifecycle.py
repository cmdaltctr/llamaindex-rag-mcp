"""Lifecycle of the managed llama.cpp server, with a fake ``llama-server`` (Part B.3).

Every process here is a small fake program from ``llamacpp_fake``. No real
``llama-server`` runs, Ollama is not touched and the user's own server on its
own port is never contacted. Fake keys are named constants.
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import socket
import subprocess
import sys
import time
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import pytest_asyncio
from tests.unit.llamacpp_fake import FakeServerProgram, await_until, free_port, install_fake

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX process groups")

from omrg.core.providers.llm.llamacpp_rules import REASONS  # noqa: E402
from omrg.transports.api import llamacpp_server as lifecycle  # noqa: E402
from omrg.transports.api.llamacpp_server import LaunchConfig, LlamacppServer  # noqa: E402

FAKE_KEY = "sk-or-v1-FAKEKEYFORTESTS0123456789"  # gitleaks:allow
HF_TOKEN = "hf_FAKE_TOKEN_FOR_TESTS"  # noqa: S105  # gitleaks:allow
CAP = 5 * 1024 * 1024


class Rig(SimpleNamespace):
    """The pieces of one test."""

    program: FakeServerProgram
    model: Path
    port: int
    log: Path
    manager: LlamacppServer
    popen_calls: list[dict[str, Any]]
    signals: list[tuple[int, int]]

    def config(self, **overrides: Any) -> LaunchConfig:
        values: dict[str, Any] = {
            "binary": str(self.program.path),
            "model": str(self.model),
            "context_window": 16384,
            "chat_url": f"http://127.0.0.1:{self.port}/v1",
        }
        values.update(overrides)
        return LaunchConfig(**values)

    def alive(self, pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        return True

    def last_pid(self) -> int:
        return self.program.pids()[-1]


@pytest_asyncio.fixture
async def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Rig]:
    program = install_fake(tmp_path / "bin")
    model = tmp_path / "model.gguf"
    model.write_bytes(b"GGUF")
    popen_calls: list[dict[str, Any]] = []
    sent: list[tuple[int, int]] = []

    def recording_popen(argv: list[str], **kwargs: Any) -> subprocess.Popen[bytes]:
        popen_calls.append({"argv": argv, **kwargs})
        return subprocess.Popen(argv, **kwargs)

    real_killpg = os.killpg

    def recording_killpg(pgid: int, sig: int) -> None:
        sent.append((pgid, sig))
        real_killpg(pgid, sig)

    monkeypatch.setattr(os, "killpg", recording_killpg)
    manager = LlamacppServer(
        tmp_path / "ws" / "llamacpp-server.log",
        health_timeout=20.0,
        stop_grace=3.0,
        poll_interval=0.05,
        popen=recording_popen,
    )
    state = Rig(
        program=program,
        model=model,
        port=free_port(),
        log=tmp_path / "ws" / "llamacpp-server.log",
        manager=manager,
        popen_calls=popen_calls,
        signals=sent,
    )
    yield state
    await manager.shutdown()
    for pid in program.pids():
        try:
            real_killpg(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


async def running(rig: Rig, **overrides: Any) -> Any:
    await rig.manager.start(rig.config(**overrides))
    await await_until(lambda: rig.manager.status().state == "running")
    return rig.manager.status()


# ── Healthy start, fixed argument list, no shell ─────────────────────────


async def test_start_moves_to_starting_then_running_and_stop_ends_it(rig: Rig) -> None:
    first = await rig.manager.start(rig.config())
    assert first.state in ("starting", "running")
    await await_until(lambda: rig.manager.status().state == "running")
    assert rig.manager.status().reason is None
    pid = rig.last_pid()
    assert rig.alive(pid)
    stopped = await rig.manager.stop()
    assert (stopped.state, stopped.reason) == ("stopped", None)
    await await_until(lambda: not rig.alive(pid))


async def test_the_argument_list_is_exact(rig: Rig) -> None:
    await running(rig)
    assert rig.program.argv() == [
        str(rig.program.path),
        "-m",
        str(rig.model),
        "--host",
        "127.0.0.1",
        "--port",
        str(rig.port),
        "-c",
        "16384",
    ]


async def test_a_hugging_face_model_starts_with_hf(rig: Rig) -> None:
    await running(rig, model="Qwen/Qwen3-0.6B-GGUF:Q8_0")
    assert rig.program.argv()[1:3] == ["-hf", "Qwen/Qwen3-0.6B-GGUF:Q8_0"]


async def test_the_process_is_a_list_with_no_shell_and_its_own_group(rig: Rig) -> None:
    await running(rig)
    call = rig.popen_calls[0]
    assert isinstance(call["argv"], list)
    assert not call.get("shell", False)
    assert call["stdin"] == subprocess.DEVNULL
    assert call["start_new_session"] is True
    assert call["stderr"] == subprocess.STDOUT


async def test_a_path_with_a_space_and_a_semicolon_is_one_argument(
    rig: Rig, tmp_path: Path
) -> None:
    odd = tmp_path / "my models; echo hi" / "q.gguf"
    odd.parent.mkdir()
    odd.write_bytes(b"GGUF")
    await running(rig, model=str(odd))
    assert rig.program.argv()[2] == str(odd)


async def test_the_child_environment_is_minimal_for_a_file_model(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_COMPATIBLE_API_KEY"):
        monkeypatch.setenv(name, FAKE_KEY)
    for name in ("HF_TOKEN", "LLAMA_CACHE", "HF_HOME"):
        monkeypatch.setenv(name, HF_TOKEN)
    await running(rig)
    env = rig.program.env()
    assert not {"OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_COMPATIBLE_API_KEY"} & set(env)
    assert not {"HF_TOKEN", "LLAMA_CACHE", "HF_HOME"} & set(env)
    assert FAKE_KEY not in json.dumps(env)


async def test_a_hugging_face_model_gets_the_cache_variables_but_still_no_provider_key(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_KEY)
    monkeypatch.setenv("HF_TOKEN", HF_TOKEN)
    await running(rig, model="Qwen/Qwen3-0.6B-GGUF")
    env = rig.program.env()
    assert env.get("HF_TOKEN") == HF_TOKEN
    assert "OPENROUTER_API_KEY" not in env


# ── Refusals before any launch ───────────────────────────────────────────


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"binary": ""}, "not-configured"),
        ({"model": ""}, "not-configured"),
        ({"model": "/absent/model.gguf"}, "model-invalid"),
        ({"model": "--api-key"}, "model-invalid"),
        ({"chat_url": "http://192.168.1.20:8081/v1"}, "not-loopback"),
        ({"chat_url": "https://127.0.0.1:8081/v1"}, "not-loopback"),
    ],
)
async def test_a_refused_start_is_failed_with_a_fixed_reason_and_no_process(
    rig: Rig, overrides: dict[str, Any], reason: str
) -> None:
    status = await rig.manager.start(rig.config(**overrides))
    assert (status.state, status.reason) == ("failed", reason)
    assert rig.program.pids() == []
    assert rig.popen_calls == []


async def test_a_program_replaced_by_a_directory_after_save_is_refused_at_launch(
    rig: Rig, tmp_path: Path
) -> None:
    folder = tmp_path / "other" / "llama-server"
    folder.mkdir(parents=True)
    status = await rig.manager.start(rig.config(binary=str(folder)))
    assert (status.state, status.reason) == ("failed", "binary-invalid")
    assert rig.popen_calls == []


async def test_a_program_with_another_name_is_refused_at_launch(rig: Rig) -> None:
    status = await rig.manager.start(rig.config(binary="/bin/sh"))
    assert (status.state, status.reason) == ("failed", "binary-invalid")
    assert rig.popen_calls == []


# ── Ownership: never touch a server the user started ─────────────────────


async def test_a_server_on_the_port_is_refused_and_never_signalled(
    rig: Rig, tmp_path: Path
) -> None:
    bystander = install_fake(tmp_path / "users-own")
    child = subprocess.Popen(  # noqa: S603 - the fake program of this test
        [
            str(bystander.path),
            "-m",
            str(rig.model),
            "--host",
            "127.0.0.1",
            "--port",
            str(rig.port),
            "-c",
            "2048",
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        await await_until(lambda: _listening(rig.port))
        status = await rig.manager.start(rig.config())
        assert (status.state, status.reason) == ("failed", "port-in-use")
        assert rig.popen_calls == []
        assert rig.signals == []
        stopped = await rig.manager.stop()
        assert stopped.state == "stopped"
        assert rig.signals == []
        assert child.poll() is None
        await rig.manager.shutdown()
        assert child.poll() is None
    finally:
        child.kill()
        child.wait(timeout=5)


def _listening(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
            return True
    except OSError:
        return False


async def test_stop_with_nothing_owned_sends_no_signal(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    kills: list[Any] = []
    monkeypatch.setattr(os, "kill", lambda *a: kills.append(a))
    status = await rig.manager.stop()
    assert status.state == "stopped"
    assert rig.signals == []
    assert kills == []


async def test_only_the_owned_group_is_ever_signalled(rig: Rig) -> None:
    await running(rig)
    pid = rig.last_pid()
    await rig.manager.stop()
    assert rig.signals
    assert {pgid for pgid, _ in rig.signals} == {pid}


async def test_start_while_running_does_not_start_a_second_process(rig: Rig) -> None:
    await running(rig)
    again = await rig.manager.start(rig.config())
    assert again.state == "running"
    assert len(rig.program.pids()) == 1


# ── Failure reasons ──────────────────────────────────────────────────────


async def test_exit_while_starting_is_failed_exited_with_the_code(rig: Rig) -> None:
    rig.program.set_mode("exit:3")
    await rig.manager.start(rig.config())
    await await_until(lambda: rig.manager.status().state == "failed")
    status = rig.manager.status()
    assert (status.reason, status.exit_code) == ("exited", 3)
    assert status.pid_running is False


async def test_child_text_never_reaches_the_status(rig: Rig) -> None:
    rig.program.set_mode("exit:3")
    await rig.manager.start(rig.config())
    await await_until(lambda: rig.manager.status().state == "failed")
    status = rig.manager.status()
    assert status.reason in REASONS
    assert "SECRET-CHILD-TEXT" not in repr(status)
    await await_until(lambda: "SECRET-CHILD-TEXT" in rig.log.read_text())


async def test_a_kill_from_outside_shows_failed_exited_on_the_next_read(rig: Rig) -> None:
    await running(rig)
    os.kill(rig.last_pid(), signal.SIGKILL)
    await await_until(lambda: rig.manager.status().state == "failed")
    assert rig.manager.status().reason == "exited"


async def test_no_health_in_time_is_timeout_and_the_process_is_stopped(
    rig: Rig, tmp_path: Path
) -> None:
    rig.program.set_mode("hang")
    children: list[subprocess.Popen[bytes]] = []

    def spawn(argv: list[str], **kwargs: Any) -> subprocess.Popen[bytes]:
        children.append(subprocess.Popen(argv, **kwargs))
        return children[-1]

    quick = LlamacppServer(
        rig.log, health_timeout=1.0, stop_grace=2.0, poll_interval=0.05, popen=spawn
    )
    await quick.start(rig.config())
    await await_until(lambda: quick.status().state == "failed")
    assert quick.status().reason == "timeout"
    # Take the pid from the spawn, not from starts.log: under load the 1 s
    # health timeout can stop the fake before it writes its pid there.
    pid = children[-1].pid
    await await_until(lambda: not rig.alive(pid))
    await quick.shutdown()


async def test_a_slow_health_check_keeps_the_state_starting_until_200(rig: Rig) -> None:
    rig.program.set_mode("slow:1.5")
    await rig.manager.start(rig.config())
    assert rig.manager.status().state == "starting"
    await await_until(lambda: rig.manager.status().state == "running")


# ── Stop, restart, shutdown ──────────────────────────────────────────────


async def test_a_graceful_stop_sends_no_sigkill(rig: Rig) -> None:
    await running(rig)
    await rig.manager.stop()
    assert [sig for _, sig in rig.signals] == [signal.SIGTERM]


async def test_a_process_that_ignores_sigterm_gets_sigkill_to_its_group(rig: Rig) -> None:
    rig.program.set_mode("ignore-term")
    manager = LlamacppServer(
        rig.log, health_timeout=20.0, stop_grace=0.5, poll_interval=0.05, popen=subprocess.Popen
    )
    await manager.start(rig.config())
    await await_until(lambda: manager.status().state == "running")
    pid = rig.last_pid()
    await manager.stop()
    assert [sig for _, sig in rig.signals] == [signal.SIGTERM, signal.SIGKILL]
    await await_until(lambda: not rig.alive(pid))
    assert manager.status().state == "stopped"


async def test_restart_stops_then_starts_with_the_new_values(rig: Rig) -> None:
    await running(rig)
    first = rig.last_pid()
    await rig.manager.restart(rig.config(context_window=8192))
    await await_until(lambda: rig.manager.status().state == "running")
    assert rig.program.argv()[-2:] == ["-c", "8192"]
    assert rig.last_pid() != first
    await await_until(lambda: not rig.alive(first))


async def test_the_status_reports_what_the_process_started_with(rig: Rig) -> None:
    status = await running(rig, context_window=4096)
    assert status.started_with is not None
    assert (status.started_with.context_window, status.started_with.model_kind) == (4096, "file")
    assert status.started_with.model == str(rig.model)
    await rig.manager.stop()
    assert rig.manager.status().started_with is None


async def test_shutdown_stops_the_owned_group(rig: Rig) -> None:
    await running(rig)
    pid = rig.last_pid()
    await rig.manager.shutdown()
    await await_until(lambda: not rig.alive(pid))
    assert rig.manager.status().state == "stopped"


async def test_the_exit_hook_stops_the_owned_group(rig: Rig) -> None:
    await running(rig)
    pid = rig.last_pid()
    rig.manager.stop_now()
    await await_until(lambda: not rig.alive(pid))


# ── Log file ─────────────────────────────────────────────────────────────


async def test_output_goes_to_the_log_file_and_each_start_empties_it(rig: Rig) -> None:
    rig.program.set_mode("exit:3")
    await rig.manager.start(rig.config())
    await await_until(lambda: rig.manager.status().state == "failed")
    await await_until(lambda: "SECRET-CHILD-TEXT" in rig.log.read_text())
    rig.program.set_mode("ok")
    await running(rig)
    assert "SECRET-CHILD-TEXT" not in rig.log.read_text()
    assert oct(rig.log.stat().st_mode & 0o777) == "0o600"


async def test_the_log_never_grows_past_five_mebibytes(rig: Rig) -> None:
    rig.program.set_mode("flood")
    await running(rig)
    await await_until(lambda: rig.log.stat().st_size >= CAP)
    await rig.manager.stop()
    assert rig.log.stat().st_size <= CAP


def test_a_cap_applies_to_a_single_large_write(tmp_path: Path) -> None:
    lifecycle.pump_capped(_Pipe([b"y" * (CAP + 4096)]), tmp_path / "log", CAP)
    assert (tmp_path / "log").stat().st_size == CAP


class _Pipe:
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = list(chunks)

    def read(self, size: int) -> bytes:
        return self.chunks.pop(0) if self.chunks else b""


# ── Static guards ────────────────────────────────────────────────────────


def test_the_module_looks_up_no_process_by_name_or_port() -> None:
    source = Path(lifecycle.__file__).read_text(encoding="utf-8")
    for word in (
        "pkill",
        "killall",
        "lsof",
        "pgrep",
        "psutil",
        "process_iter",
        "netstat",
        "shell=True",
    ):
        assert word not in source


def test_the_module_is_not_imported_by_the_cli_or_stdio_transports() -> None:
    root = Path(lifecycle.__file__).parents[1]
    for folder in ("cli", "mcp"):
        for path in (root / folder).rglob("*.py"):
            assert "llamacpp_server" not in path.read_text(encoding="utf-8"), path


@pytest.mark.skipif(sys.platform == "win32", reason="process groups are POSIX only")
def test_a_child_outside_its_own_group_is_signalled_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the child did not get its own group, never signal the group it shares."""
    child = SimpleNamespace(pid=424242, poll=lambda: None)
    group_kills: list[tuple[int, int]] = []
    single_kills: list[tuple[int, int]] = []
    monkeypatch.setattr(lifecycle.os, "getpgid", lambda pid: 1000)  # not its own group
    monkeypatch.setattr(lifecycle.os, "killpg", lambda pgid, sig: group_kills.append((pgid, sig)))
    monkeypatch.setattr(lifecycle.os, "kill", lambda pid, sig: single_kills.append((pid, sig)))
    LlamacppServer._signal(child, signal.SIGTERM)
    assert group_kills == []
    assert single_kills == [(424242, signal.SIGTERM)]


@pytest.mark.skipif(sys.platform == "win32", reason="process groups are POSIX only")
def test_a_child_that_leads_its_group_gets_a_group_signal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    child = SimpleNamespace(pid=424242, poll=lambda: None)
    group_kills: list[tuple[int, int]] = []
    monkeypatch.setattr(lifecycle.os, "getpgid", lambda pid: pid)
    monkeypatch.setattr(lifecycle.os, "killpg", lambda pgid, sig: group_kills.append((pgid, sig)))
    monkeypatch.setattr(lifecycle.os, "kill", lambda pid, sig: pytest.fail("single kill used"))
    LlamacppServer._signal(child, signal.SIGTERM)
    assert group_kills == [(424242, signal.SIGTERM)]


async def test_a_status_read_while_a_timed_out_start_is_stopping_never_says_exited(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The page polls the status. Our own SIGTERM must not read as the server exiting.

    After the health timeout the manager signals the hung child and waits for it.
    The child dies at once, but the wait goes on, so a status read in that window
    saw a dead process and reported ``exited`` in place of ``timeout``.
    """
    rig.program.set_mode("hang")
    real_terminate = LlamacppServer._terminate

    def slow_terminate(self: LlamacppServer, proc: Any) -> None:
        real_terminate(self, proc)  # the child is dead from here on
        time.sleep(0.6)  # the manager is still "stopping" for a while

    monkeypatch.setattr(LlamacppServer, "_terminate", slow_terminate)
    quick = LlamacppServer(
        rig.log, health_timeout=0.5, stop_grace=2.0, poll_interval=0.05, popen=subprocess.Popen
    )
    await quick.start(rig.config())
    seen: set[tuple[str, str | None]] = set()
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        status = quick.status()
        seen.add((status.state, status.reason))
        if status.state == "failed":
            break
        await asyncio.sleep(0.01)
    await asyncio.sleep(0.8)  # let the slow terminate finish and the watcher end
    seen.add((quick.status().state, quick.status().reason))
    assert ("failed", "exited") not in seen, seen
    assert quick.status().reason == "timeout"
    await quick.shutdown()
