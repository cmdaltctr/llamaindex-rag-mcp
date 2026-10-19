"""Shared fakes for the ``omrg web`` login item command tests.

One :class:`Harness` replaces every outside effect of the commands: the
home folder, the platform, ``launchctl``, the health check, the clock,
the port probe and the browser. No test touches the real ``~/Library``.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from omrg.transports.cli import app as cli_app
from omrg.transports.cli import web_login_item as wl

runner = CliRunner()


#: Health body of a healthy app of the given version.
def healthy(version: str = "1.0.0") -> dict[str, Any]:
    return {"status": "ok", "ready": True, "version": version}


def flat(text: str) -> str:
    """Collapse whitespace, so a wrapped terminal line still matches."""
    return " ".join(text.split())


class Harness:
    """Fake machine for one test."""

    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.home = tmp_path / "home"
        self.home.mkdir()
        self.cwd = tmp_path / "cwd"
        self.cwd.mkdir()
        self.command = tmp_path / "tool" / "bin" / "omrg"
        self.command.parent.mkdir(parents=True)
        self.command.write_text("#!/bin/sh\n", encoding="utf-8")
        monkeypatch.setenv("HOME", str(self.home))
        monkeypatch.chdir(self.cwd)

        self.macos = True
        self.interactive = False
        self.launchctl_calls: list[list[str]] = []
        self.launchctl_rc: dict[str, int] = {}
        self.listening = False
        self.now = 0.0
        self.installed: str | None = "1.0.0"
        self.opened: list[str] = []
        self.open_rc = 0
        #: Returns the health body at the current fake time, or None.
        self.health: Callable[[], dict[str, Any] | None] = lambda: None
        #: Ports the commands asked ``GET /v1/health`` on, in order.
        self.health_ports: list[int] = []
        #: Called after each launchctl command, so a test can change the app state.
        self.on_launchctl: Callable[[list[str]], None] = lambda cmd: None

        monkeypatch.setattr(wl, "_is_macos", lambda: self.macos)
        monkeypatch.setattr(wl, "_stdin_is_interactive", lambda: self.interactive)
        monkeypatch.setattr(wl._launchagent, "run_launchctl", self._launchctl)
        monkeypatch.setattr(wl.core, "fetch_health", self._fetch_health)
        monkeypatch.setattr(wl.core, "installed_version", lambda *a, **k: self.installed)
        monkeypatch.setattr(wl, "_clock", lambda: self.now)
        monkeypatch.setattr(wl, "_sleep", self._sleep)
        monkeypatch.setattr(wl, "_port_in_use", lambda host, port: self.listening)
        monkeypatch.setattr(wl, "_open_url", self._open)

    # ── fakes ────────────────────────────────────────────────────────────

    def _launchctl(self, cmd: list[str]) -> subprocess.CompletedProcess[str]:
        self.launchctl_calls.append(list(cmd))
        done = subprocess.CompletedProcess(cmd, self.launchctl_rc.get(cmd[1], 0), "", "")
        self.on_launchctl(cmd)
        return done

    def _fetch_health(self, host: str, port: int, **_: Any) -> dict[str, Any] | None:
        self.health_ports.append(port)
        return self.health()

    def _sleep(self, seconds: float) -> None:
        self.now += seconds

    def _open(self, url: str) -> int:
        self.opened.append(url)
        return self.open_rc

    # ── helpers ──────────────────────────────────────────────────────────

    @property
    def uid(self) -> int:
        return os.getuid()

    @property
    def plist(self) -> Path:
        return self.home / "Library" / "LaunchAgents" / "com.omrg.web.plist"

    @property
    def error_log(self) -> Path:
        return self.home / "Library" / "Logs" / "omrg" / "com.omrg.web.err.log"

    def verbs(self) -> list[str]:
        """The launchctl verbs called so far, in order."""
        return [call[1] for call in self.launchctl_calls]

    def serve(self, version: str = "1.0.0", *, after: float = 0.0) -> None:
        """From fake time *after* on, the app answers health."""
        self.health = lambda: healthy(version) if self.now >= after else None

    def install_plist(self) -> None:
        """Put a plist on disk, as an earlier install would."""
        self.plist.parent.mkdir(parents=True, exist_ok=True)
        self.plist.write_bytes(b"old plist")

    def install_real_plist(self, **options: Any) -> None:
        """Write the plist that ``install`` would write, so ``status`` can read it."""
        plan = wl.core.build_plan(command_path=str(self.command), home=self.home, **options)
        plan.plist_path.parent.mkdir(parents=True, exist_ok=True)
        plan.plist_path.write_bytes(wl.core.render_plist(plan))

    def write_link(
        self, port: int = 8765, fragment: str = "omrg_bs_SECRET", workspace: Path | None = None
    ) -> Path:
        """Write the link file where the workspace keeps it (default workspace if none)."""
        link = (workspace or self.home / ".omrg" / "workspace") / "launch-link"
        link.parent.mkdir(parents=True, exist_ok=True)
        link.write_text(f"http://127.0.0.1:{port}/#bootstrap={fragment}\n", encoding="utf-8")
        return link

    def invoke(self, *args: str, input: str | None = None) -> Any:
        return runner.invoke(cli_app, ["web", *args], input=input)
