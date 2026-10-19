"""Private, renewed sign-in link of a login-item server (add-web-login-item, group 2).

Covers the ``local-web-workspace`` scenarios: the link file is private,
renews after each sign-in and after the failure limit, disappears at
shutdown, and never reaches the terminal or the log. The foreground
launch is unchanged.
"""

from __future__ import annotations

import signal
import stat
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("fastapi")

from typer.testing import CliRunner  # noqa: E402

from omrg.transports.api.launch_link import (  # noqa: E402
    LINK_FILE_NAME,
    RearmingAccessPolicy,
    write_link_file,
)
from omrg.transports.api.security import MAX_BOOTSTRAP_FAILURES  # noqa: E402
from omrg.transports.cli import app as cli_app  # noqa: E402

runner = CliRunner()
LINK_FRAGMENT = "#bootstrap="


def _secret(link: str) -> str:
    return link.strip().split(LINK_FRAGMENT, 1)[1]


def _make(tmp_path: Path) -> tuple[RearmingAccessPolicy, Path]:
    link_file = tmp_path / LINK_FILE_NAME
    policy = RearmingAccessPolicy.for_launch("127.0.0.1", 8765, link_file=link_file)
    policy.publish()
    return policy, link_file


# ── The policy and its file ─────────────────────────────────────────────


def test_publish_writes_a_private_one_line_link(tmp_path: Path) -> None:
    policy, link_file = _make(tmp_path)

    assert stat.S_IMODE(link_file.stat().st_mode) == 0o600
    text = link_file.read_text(encoding="utf-8")
    assert text == policy.launch_url() + "\n"
    assert text.startswith("http://127.0.0.1:8765/#bootstrap=")


def test_sign_in_renews_the_link(tmp_path: Path) -> None:
    policy, link_file = _make(tmp_path)
    first = link_file.read_text(encoding="utf-8")

    assert policy.exchange_bootstrap(_secret(first)) is not None

    second = link_file.read_text(encoding="utf-8")
    assert second != first
    assert policy.exchange_bootstrap(_secret(first)) is None
    assert policy.exchange_bootstrap(_secret(second)) is not None
    assert stat.S_IMODE(link_file.stat().st_mode) == 0o600


def test_failure_limit_renews_the_link(tmp_path: Path) -> None:
    policy, link_file = _make(tmp_path)
    old = link_file.read_text(encoding="utf-8")

    for _ in range(MAX_BOOTSTRAP_FAILURES):
        assert policy.exchange_bootstrap("omrg_bs_guess") is None

    assert policy.exchange_bootstrap(_secret(old)) is None
    new = link_file.read_text(encoding="utf-8")
    assert new != old
    assert policy.exchange_bootstrap(_secret(new)) is not None


def test_failures_below_the_limit_keep_the_link(tmp_path: Path) -> None:
    policy, link_file = _make(tmp_path)
    first = link_file.read_text(encoding="utf-8")

    for _ in range(MAX_BOOTSTRAP_FAILURES - 1):
        policy.exchange_bootstrap("omrg_bs_guess")

    assert link_file.read_text(encoding="utf-8") == first
    assert policy.exchange_bootstrap(_secret(first)) is not None


def test_retire_removes_the_file_and_is_repeatable(tmp_path: Path) -> None:
    policy, link_file = _make(tmp_path)

    policy.retire()
    policy.retire()

    assert not link_file.exists()


def test_write_replaces_without_leaving_temporary_files(tmp_path: Path) -> None:
    target = tmp_path / LINK_FILE_NAME

    write_link_file(target, "http://127.0.0.1:1/#bootstrap=a")
    write_link_file(target, "http://127.0.0.1:1/#bootstrap=b")

    assert target.read_text(encoding="utf-8") == "http://127.0.0.1:1/#bootstrap=b\n"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert [p.name for p in tmp_path.iterdir()] == [LINK_FILE_NAME]


def test_a_failed_write_does_not_break_sign_in(tmp_path: Path) -> None:
    policy, link_file = _make(tmp_path)
    secret = _secret(link_file.read_text(encoding="utf-8"))

    with patch("omrg.transports.api.launch_link.write_link_file", side_effect=OSError("disk full")):
        token = policy.exchange_bootstrap(secret)

    assert token is not None


def test_a_failed_renewal_is_retried_on_the_next_attempt(tmp_path: Path) -> None:
    """The file must not keep a spent link for good (CodeRabbit, PR 119)."""
    policy, link_file = _make(tmp_path)
    spent = link_file.read_text(encoding="utf-8")
    real_write = write_link_file
    calls = {"n": 0}

    def flaky(path: Path, url: str) -> None:
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("disk full")
        real_write(path, url)

    with patch("omrg.transports.api.launch_link.write_link_file", side_effect=flaky):
        assert policy.exchange_bootstrap(_secret(spent)) is not None
        assert link_file.read_text(encoding="utf-8") == spent
        # A browser that opened the spent link posts it again and is refused ...
        assert policy.exchange_bootstrap(_secret(spent)) is None

    # ... and that attempt put the new link in the file.
    renewed = link_file.read_text(encoding="utf-8")
    assert renewed != spent
    assert policy.exchange_bootstrap(_secret(renewed)) is not None


def test_a_failed_renewal_that_keeps_failing_never_breaks_sign_in(tmp_path: Path) -> None:
    policy, link_file = _make(tmp_path)
    spent = link_file.read_text(encoding="utf-8")

    with patch("omrg.transports.api.launch_link.write_link_file", side_effect=OSError("full")):
        assert policy.exchange_bootstrap(_secret(spent)) is not None
        assert policy.exchange_bootstrap("omrg_bs_guess") is None

    assert link_file.read_text(encoding="utf-8") == spent


# ── The command ──────────────────────────────────────────────────────────


class _Served:
    """What the fake server saw at the moment it ran."""

    def __init__(self) -> None:
        self.link: str | None = None
        self.mode: int | None = None
        self.access_log: bool | None = None
        self.log_text = ""


def _run_web(workspace: Path, *args: str) -> tuple[Any, _Served]:
    served = _Served()
    link_file = workspace / LINK_FILE_NAME

    def fake_serve(application: Any, sock: Any, **kwargs: Any) -> bool:
        if link_file.exists():
            served.link = link_file.read_text(encoding="utf-8")
            served.mode = stat.S_IMODE(link_file.stat().st_mode)
        served.access_log = kwargs.get("access_log", True)
        buffer = application.state.log_buffer
        served.log_text = str(buffer.records())
        return True

    sock = MagicMock()
    sock.getsockname.return_value = ("127.0.0.1", 4242)
    with (
        patch("omrg.transports.cli.web._bind_socket", return_value=sock),
        patch("omrg.transports.cli.web._serve", side_effect=fake_serve),
    ):
        result = runner.invoke(cli_app, ["web", "--workspace", str(workspace), *args])
    return result, served


def test_login_item_hands_the_link_over_in_a_private_file(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"

    result, served = _run_web(workspace, "--login-item")

    assert result.exit_code == 0, result.output
    assert served.mode == 0o600
    assert served.link is not None
    assert served.link.startswith("http://127.0.0.1:4242/#bootstrap=")
    secret = _secret(served.link)
    assert secret not in result.output
    assert secret not in served.log_text


def test_login_item_turns_the_access_log_off(tmp_path: Path) -> None:
    _, served = _run_web(tmp_path / "ws", "--login-item")

    assert served.access_log is False


def test_clean_shutdown_removes_the_file(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"

    _run_web(workspace, "--login-item")

    assert not (workspace / LINK_FILE_NAME).exists()


def test_the_file_is_removed_when_the_server_fails_to_start(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    sock = MagicMock()
    sock.getsockname.return_value = ("127.0.0.1", 4242)

    with (
        patch("omrg.transports.cli.web._bind_socket", return_value=sock),
        patch("omrg.transports.cli.web._serve", return_value=False),
    ):
        result = runner.invoke(cli_app, ["web", "--workspace", str(workspace), "--login-item"])

    assert result.exit_code == 1
    assert not (workspace / LINK_FILE_NAME).exists()


def test_foreground_launch_is_unchanged(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"

    result, served = _run_web(workspace)

    assert result.exit_code == 0, result.output
    assert "http://127.0.0.1:4242/#bootstrap=" in result.output
    assert served.link is None
    assert served.access_log is True
    assert not (workspace / LINK_FILE_NAME).exists()


def test_serve_passes_the_access_log_choice_to_uvicorn() -> None:
    from omrg.transports.cli.web import _serve

    with (
        patch("uvicorn.Config") as config,
        patch("uvicorn.Server.run"),
        patch("omrg.transports.api.security.install_log_redaction"),
    ):
        _serve(MagicMock(), MagicMock(), access_log=False)
        assert config.call_args.kwargs["access_log"] is False
        _serve(MagicMock(), MagicMock())
        assert config.call_args.kwargs["access_log"] is True


# ── The stop hook ────────────────────────────────────────────────────────
#
# Uvicorn re-raises SIGTERM after a graceful stop, and the default action
# ends the process. Code after ``_serve()`` then never runs, so the link
# file has to go inside Uvicorn's own shutdown step.


def _serve_through_shutdown(**kwargs: Any) -> list[str]:
    """Run ``_serve`` with a fake ``run`` that only drives ``shutdown``."""
    import asyncio

    from omrg.transports.cli.web import _serve

    order: list[str] = []

    async def parent_shutdown(self: Any, sockets: Any = None) -> None:
        order.append("shutdown")

    def run(self: Any, sockets: Any = None) -> None:
        asyncio.run(self.shutdown(sockets))

    with (
        patch("uvicorn.Config"),
        patch("uvicorn.Server.shutdown", parent_shutdown),
        patch("uvicorn.Server.run", run),
        patch("omrg.transports.api.security.install_log_redaction"),
    ):
        _serve(MagicMock(), MagicMock(), **kwargs)
    return order


def test_on_stop_runs_once() -> None:
    calls: list[str] = []

    _serve_through_shutdown(on_stop=lambda: calls.append("on_stop"))

    assert calls == ["on_stop"]


def test_on_stop_comes_after_the_parent_shutdown() -> None:
    import asyncio

    from omrg.transports.cli.web import _serve

    order: list[str] = []

    async def parent_shutdown(self: Any, sockets: Any = None) -> None:
        order.append("shutdown")

    def run(self: Any, sockets: Any = None) -> None:
        asyncio.run(self.shutdown(sockets))

    with (
        patch("uvicorn.Config"),
        patch("uvicorn.Server.shutdown", parent_shutdown),
        patch("uvicorn.Server.run", run),
        patch("omrg.transports.api.security.install_log_redaction"),
    ):
        _serve(MagicMock(), MagicMock(), on_stop=lambda: order.append("on_stop"))

    assert order == ["shutdown", "on_stop"]


def test_serve_without_on_stop_adds_no_hook() -> None:
    assert _serve_through_shutdown() == ["shutdown"]


def test_a_failing_on_stop_does_not_stop_the_shutdown() -> None:
    def on_stop() -> None:
        raise OSError("read-only file system")

    # Must not raise out of ``shutdown``.
    assert _serve_through_shutdown(on_stop=on_stop) == ["shutdown"]


_CHILD = """
import sys
import types
from pathlib import Path

from omrg.transports.api.launch_link import write_link_file
from omrg.transports.cli.web import _bind_socket, _serve

link_file = Path(sys.argv[1])
port_file = Path(sys.argv[2])


async def app(scope, receive, send):
    if scope["type"] == "lifespan":
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            else:
                await send({"type": "lifespan.shutdown.complete"})
                return
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


app.state = types.SimpleNamespace()
sock = _bind_socket("127.0.0.1", 0)
write_link_file(link_file, "http://127.0.0.1/#bootstrap=x")
port_file.write_text(str(sock.getsockname()[1]), encoding="utf-8")
_serve(app, sock, on_stop=lambda: link_file.unlink(missing_ok=True))
# Reached only when the process was not ended by the re-raised signal.
Path(sys.argv[3]).write_text("returned", encoding="utf-8")
"""


def _wait_for(check: Any, what: str, timeout: float = 8.0) -> Any:
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError(f"Timed out waiting for {what}.")


def _answers(port: int) -> bool:
    import urllib.request

    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=1) as reply:
            return reply.status == 200
    except OSError:
        return False


def _run_child_and_send_sigterm(tmp_path: Path, script: str) -> tuple[int, Path, Path]:
    import signal
    import subprocess
    import sys

    link_file = tmp_path / LINK_FILE_NAME
    port_file = tmp_path / "port"
    returned = tmp_path / "returned"
    source = tmp_path / "child.py"
    source.write_text(script, encoding="utf-8")
    child = subprocess.Popen(
        [sys.executable, "-I", str(source), str(link_file), str(port_file), str(returned)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        try:
            port = int(_wait_for(lambda: port_file.exists() and port_file.read_text(), "the port"))
            _wait_for(lambda: link_file.exists() and _answers(port), "the server to answer")
        except AssertionError as exc:
            child.kill()
            _, err = child.communicate()
            raise AssertionError(
                f"{exc} Child stderr: {err.decode(errors='replace')[-800:]}"
            ) from None
        child.send_signal(signal.SIGTERM)
        code = child.wait(timeout=8)
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()
        if child.stderr is not None:
            child.stderr.close()
    return code, link_file, returned


@pytest.mark.skipif(sys.platform == "win32", reason="needs POSIX signals")
def test_sigterm_removes_the_link_file_and_ends_by_signal(tmp_path: Path) -> None:
    pytest.importorskip("uvicorn")

    code, link_file, returned = _run_child_and_send_sigterm(tmp_path, _CHILD)

    assert not link_file.exists()
    assert not returned.exists()  # code after _serve() never ran
    assert code == -signal.SIGTERM


@pytest.mark.skipif(sys.platform == "win32", reason="needs POSIX signals")
def test_a_removal_after_serve_returns_is_left_behind_by_sigterm(tmp_path: Path) -> None:
    """Control: this is the old behaviour, and why the hook sits in shutdown."""
    pytest.importorskip("uvicorn")
    old_style = _CHILD.replace(
        "_serve(app, sock, on_stop=lambda: link_file.unlink(missing_ok=True))",
        "_serve(app, sock)\nlink_file.unlink(missing_ok=True)",
    )
    assert old_style != _CHILD

    code, link_file, _ = _run_child_and_send_sigterm(tmp_path, old_style)

    assert link_file.exists()
    assert code == -signal.SIGTERM
