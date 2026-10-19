"""``omrg web install | uninstall | status | restart | open`` (add-web-login-item, group 4).

Every case runs on the fakes in ``test_web_login_item_support``: a
temporary home, a fake ``launchctl`` runner, a fake health check and a
fake clock.
"""

from __future__ import annotations

import json
import plistlib
from pathlib import Path
from typing import Any

import pytest
from tests.unit.test_web_login_item_support import Harness, flat, healthy

from omrg.transports.cli import web_login_item as wl


@pytest.fixture
def h(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Harness:
    return Harness(tmp_path, monkeypatch)


def _install(h: Harness, *args: str, input: str | None = None):
    return h.invoke("install", "--command-path", str(h.command), *args, input=input)


# ── install ──────────────────────────────────────────────────────────────


def test_install_prints_the_plan(h: Harness) -> None:
    h.serve(link_port=8765)

    result = _install(h, "--yes")

    text = flat(result.output)
    assert "com.omrg.web" in text
    assert f"{h.command} web --login-item" in text
    assert str(h.plist) in text
    assert str(h.error_log) in text


def test_install_writes_the_plist_and_loads_it(h: Harness) -> None:
    h.serve(link_port=8765)

    result = _install(h, "--yes")

    assert result.exit_code == 0, result.output
    data = plistlib.loads(h.plist.read_bytes())
    assert data["Label"] == "com.omrg.web"
    assert data["ProgramArguments"] == [str(h.command), "web", "--login-item"]
    assert h.launchctl_calls[-1] == ["launchctl", "bootstrap", f"gui/{h.uid}", str(h.plist)]
    assert h.verbs() == ["bootout", "bootstrap"]


def test_install_waits_for_the_app_and_reports_it(h: Harness) -> None:
    h.serve("2.5.0", after=5.0, link_port=8765)

    result = _install(h, "--yes")

    assert result.exit_code == 0, result.output
    assert h.now >= 5.0
    assert "2.5.0" in result.output
    assert "omrg web open" in flat(result.output)


def test_install_creates_the_omrg_folder_and_the_log_folder(h: Harness) -> None:
    h.serve(link_port=8765)

    _install(h, "--yes")

    assert (h.home / ".omrg").is_dir()
    assert h.error_log.parent.is_dir()


def test_options_reach_the_agent(h: Harness, tmp_path: Path) -> None:
    h.serve(link_port=8765)
    papers = tmp_path / "papers"
    papers.mkdir()
    h.write_link(port=9000)

    result = _install(h, "--root", str(papers), "--port", "9000", "--yes")

    assert result.exit_code == 0, result.output
    argv = plistlib.loads(h.plist.read_bytes())["ProgramArguments"]
    assert argv[argv.index("--root") + 1] == str(papers)
    assert argv[argv.index("--port") + 1] == "9000"
    assert "--workspace" not in argv


def test_existing_plist_is_refused_without_force(h: Harness) -> None:
    h.install_plist()

    result = _install(h, "--yes")

    assert result.exit_code != 0
    assert h.plist.read_bytes() == b"old plist"
    assert "--force" in flat(result.output)
    assert h.launchctl_calls == []


def test_force_replaces_an_existing_plist(h: Harness) -> None:
    h.install_plist()
    h.serve(link_port=8765)

    result = _install(h, "--force", "--yes")

    assert result.exit_code == 0, result.output
    assert plistlib.loads(h.plist.read_bytes())["Label"] == "com.omrg.web"
    assert "bootstrap" in h.verbs()


def test_dry_run_writes_nothing_and_skips_launchctl(h: Harness) -> None:
    result = _install(h, "--dry-run")

    assert result.exit_code == 0, result.output
    assert not h.plist.exists()
    assert not (h.home / ".omrg").exists()
    assert not (h.home / "Library").exists()
    assert h.launchctl_calls == []
    text = flat(result.output)
    assert "com.omrg.web" in text
    assert str(h.plist) in text


def test_dry_run_works_on_other_platforms(h: Harness) -> None:
    h.macos = False

    result = _install(h, "--dry-run")

    assert result.exit_code == 0, result.output
    assert h.launchctl_calls == []


def test_install_is_refused_outside_macos(h: Harness) -> None:
    h.macos = False

    result = _install(h, "--yes")

    assert result.exit_code != 0
    assert "macOS" in flat(result.output)
    assert not h.plist.exists()
    assert h.launchctl_calls == []


def test_relative_command_path_is_refused(h: Harness) -> None:
    result = h.invoke("install", "--command-path", "omrg", "--yes")

    assert result.exit_code != 0
    assert "absolute" in flat(result.output)
    assert not h.plist.exists()


def test_a_busy_port_gives_a_warning_and_the_install_goes_on(h: Harness) -> None:
    h.listening = True
    h.serve(link_port=8765)

    result = _install(h, "--yes")

    assert result.exit_code == 0, result.output
    text = flat(result.output)
    assert "8765" in text
    assert "Stop that process" in text


def test_the_port_check_uses_the_port_option(h: Harness) -> None:
    h.listening = True
    h.serve(link_port=9100)

    result = _install(h, "--port", "9100", "--yes")

    assert "9100" in flat(result.output)


# ── checkout confirmation ────────────────────────────────────────────────


@pytest.fixture
def checkout(h: Harness, tmp_path: Path) -> Path:
    """Move the executable into a ``.venv`` of a git checkout."""
    proj = tmp_path / "proj"
    (proj / ".git").mkdir(parents=True)
    (proj / ".venv" / "bin").mkdir(parents=True)
    h.command = proj / ".venv" / "bin" / "omrg"
    h.command.write_text("#!/bin/sh\n", encoding="utf-8")
    return proj


def test_a_checkout_executable_shows_a_warning(h: Harness, checkout: Path) -> None:
    h.serve(link_port=8765)

    result = _install(h, "--yes")

    assert "uv tool install" in flat(result.output)


def test_a_checkout_executable_needs_confirmation_when_not_interactive(
    h: Harness, checkout: Path
) -> None:
    result = _install(h)

    assert result.exit_code != 0
    assert "--yes" in flat(result.output)
    assert not h.plist.exists()
    assert h.launchctl_calls == []


def test_an_interactive_run_asks_and_a_no_stops(h: Harness, checkout: Path) -> None:
    h.interactive = True

    result = _install(h, input="n\n")

    assert result.exit_code != 0
    assert not h.plist.exists()


def test_an_interactive_run_asks_and_a_yes_installs(h: Harness, checkout: Path) -> None:
    h.interactive = True
    h.serve(link_port=8765)

    result = _install(h, input="y\ny\n")

    assert result.exit_code == 0, result.output
    assert h.plist.exists()


# ── failures ─────────────────────────────────────────────────────────────


def test_a_health_time_out_exits_non_zero_and_keeps_the_plist(h: Harness) -> None:
    result = _install(h, "--yes")

    assert result.exit_code != 0
    assert h.plist.exists()
    assert h.now >= 60.0
    text = flat(result.output)
    assert str(h.error_log) in text
    assert "omrg web status" in text


def test_a_launchctl_failure_exits_non_zero(h: Harness) -> None:
    h.launchctl_rc["bootstrap"] = 5

    result = _install(h, "--yes")

    assert result.exit_code != 0
    assert "bootstrap" in flat(result.output)


# ── .env files ───────────────────────────────────────────────────────────


def test_install_never_reads_or_creates_a_dotenv(h: Harness) -> None:
    h.serve(link_port=8765)
    dotenv = h.cwd / ".env"
    dotenv.write_text("OPENROUTER_API_KEY=sentinel-value\n", encoding="utf-8")
    before = (dotenv.read_text(encoding="utf-8"), dotenv.stat().st_mtime_ns)

    result = _install(h, "--yes")

    assert (dotenv.read_text(encoding="utf-8"), dotenv.stat().st_mtime_ns) == before
    assert not (h.home / ".omrg" / ".env").exists()
    assert "sentinel-value" not in result.output
    assert "does not read" in flat(result.output)
    assert "omrg config init" in flat(result.output)


def test_dry_run_names_the_settings_file_and_suggests_config_init(h: Harness) -> None:
    dotenv = h.cwd / ".env"
    dotenv.write_text("OPENROUTER_API_KEY=sentinel-value\n", encoding="utf-8")
    before = (dotenv.read_text(encoding="utf-8"), dotenv.stat().st_mtime_ns)

    result = _install(h, "--dry-run")

    text = flat(result.output)
    assert result.exit_code == 0, result.output
    assert "~/.config/omrg/omrg.jsonc" in text
    assert "~/.omrg/.env is optional" in text
    assert "does not read" in text
    assert str(dotenv) in text
    assert "omrg config init" in text
    assert "sentinel-value" not in result.output
    assert (dotenv.read_text(encoding="utf-8"), dotenv.stat().st_mtime_ns) == before
    assert not (h.home / ".omrg").exists()
    assert not (h.home / ".config").exists()


def test_dry_run_honours_omrg_config_dir(h: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = h.home.parent / "elsewhere"
    monkeypatch.setenv("OMRG_CONFIG_DIR", str(folder))

    result = _install(h, "--dry-run")

    assert str(folder / "omrg.jsonc") in flat(result.output)


def test_install_does_not_report_success_for_a_server_it_did_not_start(h: Harness) -> None:
    """A hand-run 'omrg web' answers health but writes no link file."""
    h.serve()

    result = _install(h, "--yes")

    text = flat(result.output)
    assert result.exit_code != 0
    assert "The app is running" not in text
    assert "8765" in text
    assert "Stop that process" in text
    assert h.plist.exists()
    assert h.now >= 60.0


def test_install_ignores_a_link_file_for_another_port(h: Harness) -> None:
    h.serve(link_port=9999)

    result = _install(h, "--yes")

    assert result.exit_code != 0
    assert "The app is running" not in flat(result.output)


# ── uninstall ────────────────────────────────────────────────────────────


def test_uninstall_unloads_the_agent_and_deletes_the_plist(h: Harness) -> None:
    h.install_plist()

    result = h.invoke("uninstall", "--yes")

    assert result.exit_code == 0, result.output
    assert not h.plist.exists()
    assert h.launchctl_calls == [["launchctl", "bootout", f"gui/{h.uid}/com.omrg.web"]]


def test_uninstall_keeps_the_workspace_and_the_logs(h: Harness) -> None:
    h.install_plist()
    record = h.home / ".omrg" / "workspace" / "workspace.db"
    record.parent.mkdir(parents=True)
    record.write_bytes(b"data")
    h.error_log.parent.mkdir(parents=True)
    h.error_log.write_text("log line\n", encoding="utf-8")

    h.invoke("uninstall", "--yes")

    assert record.read_bytes() == b"data"
    assert h.error_log.read_text(encoding="utf-8") == "log line\n"


def test_uninstall_asks_first_and_a_no_changes_nothing(h: Harness) -> None:
    h.install_plist()

    result = h.invoke("uninstall", input="n\n")

    assert result.exit_code != 0
    assert h.plist.exists()
    assert h.launchctl_calls == []


def test_uninstall_asks_first_and_a_yes_removes(h: Harness) -> None:
    h.install_plist()

    result = h.invoke("uninstall", input="y\n")

    assert result.exit_code == 0, result.output
    assert not h.plist.exists()


def test_uninstall_with_nothing_installed_succeeds(h: Harness) -> None:
    result = h.invoke("uninstall", "--yes")

    assert result.exit_code == 0, result.output
    assert "nothing is installed" in flat(result.output).lower()
    assert h.launchctl_calls == []


def test_uninstall_removes_the_plist_of_an_agent_that_was_never_loaded(h: Harness) -> None:
    h.install_plist()
    h.launchctl_rc.update({"bootout": 3, "print": 113})

    result = h.invoke("uninstall", "--yes")

    assert result.exit_code == 0, result.output
    assert not h.plist.exists()


def test_uninstall_keeps_the_plist_when_the_agent_stays_loaded(h: Harness) -> None:
    h.install_plist()
    h.launchctl_rc.update({"bootout": 5, "print": 0})

    result = h.invoke("uninstall", "--yes")

    assert result.exit_code != 0
    assert h.plist.exists()
    assert "bootout" in flat(result.output)


# ── status ───────────────────────────────────────────────────────────────


def test_status_running_and_current(h: Harness) -> None:
    h.install_real_plist()
    h.serve("1.0.0")
    h.installed = "1.0.0"

    result = h.invoke("status")

    assert result.exit_code == 0, result.output
    text = flat(result.output).lower()
    assert "running" in text
    assert "restart" not in text


def test_status_says_a_restart_picks_up_a_newer_install(h: Harness) -> None:
    h.install_real_plist()
    h.serve("1.0.0")
    h.installed = "1.1.0"

    result = h.invoke("status")

    assert result.exit_code == 0, result.output
    text = flat(result.output)
    assert "1.0.0" in text
    assert "1.1.0" in text
    assert "omrg web restart" in text


def test_status_when_not_installed(h: Harness) -> None:
    result = h.invoke("status")

    assert result.exit_code == 1
    text = flat(result.output).lower()
    assert "not installed" in text
    assert "omrg web install" in text
    assert h.launchctl_calls == []


def test_status_when_the_app_does_not_answer(h: Harness) -> None:
    h.install_real_plist()

    result = h.invoke("status")

    assert result.exit_code == 1
    text = flat(result.output)
    assert "not answering" in text
    assert str(h.error_log) in text


def test_status_json_is_one_object_with_the_facts(h: Harness) -> None:
    h.install_real_plist()
    h.serve("1.0.0")
    h.installed = "1.2.0"

    result = h.invoke("status", "--json")

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["installed"] is True
    assert data["loaded"] is True
    assert data["running"] is True
    assert data["running_version"] == "1.0.0"
    assert data["installed_version"] == "1.2.0"
    assert data["port"] == 8765
    assert data["workspace"] == str(h.home / ".omrg" / "workspace")
    assert data["plist"] == str(h.plist)
    assert data["stderr_log"] == str(h.error_log)
    assert data["restart_needed"] is True


def test_status_json_when_not_installed(h: Harness) -> None:
    result = h.invoke("status", "--json")

    assert result.exit_code == 1
    assert json.loads(result.output)["installed"] is False


def test_status_reports_an_agent_that_is_not_loaded(h: Harness) -> None:
    h.install_real_plist()
    h.launchctl_rc["print"] = 113

    result = h.invoke("status", "--json")

    assert json.loads(result.output)["loaded"] is False
    assert result.exit_code == 1


def test_status_reads_the_port_from_the_link_file(h: Harness) -> None:
    h.install_real_plist(port=9000)
    h.write_link(port=9123)
    h.serve()

    h.invoke("status")

    assert h.health_ports == [9123]


def test_status_falls_back_to_the_plist_port_and_then_the_default(h: Harness) -> None:
    h.install_real_plist(port=9000)
    h.serve()
    h.invoke("status")
    (h.home / "Library" / "LaunchAgents" / "com.omrg.web.plist").unlink()
    h.install_real_plist()
    h.invoke("status")

    assert h.health_ports == [9000, 8765]


def test_status_never_prints_the_sign_in_secret(h: Harness) -> None:
    h.install_real_plist()
    h.write_link(fragment="omrg_bs_TOPSECRET")
    h.serve()

    plain = h.invoke("status")
    as_json = h.invoke("status", "--json")

    assert "TOPSECRET" not in plain.output
    assert "TOPSECRET" not in as_json.output


# ── restart ──────────────────────────────────────────────────────────────


def _restartable_app(h: Harness, old: str = "1.0.0", new: str | None = "1.1.0") -> dict[str, Any]:
    """An app that stops on ``kill`` and starts the new version on ``kickstart``."""
    state: dict[str, Any] = {"version": old, "at_kickstart": "unset"}
    h.health = lambda: healthy(state["version"]) if state["version"] else None

    def hook(cmd: list[str]) -> None:
        if cmd[1] == "kill":
            state["version"] = None
        if cmd[1] == "kickstart":
            state["at_kickstart"] = h.health()
            state["version"] = new

    h.on_launchctl = hook
    return state


def test_restart_stops_with_sigterm_then_starts_without_dash_k(h: Harness) -> None:
    h.install_real_plist()
    _restartable_app(h)

    result = h.invoke("restart")

    assert result.exit_code == 0, result.output
    assert [c for c in h.launchctl_calls if c[1] != "print"] == [
        ["launchctl", "kill", "SIGTERM", f"gui/{h.uid}/com.omrg.web"],
        ["launchctl", "kickstart", f"gui/{h.uid}/com.omrg.web"],
    ]
    assert "1.1.0" in result.output


def test_restart_starts_the_new_process_only_after_the_old_one_stopped(h: Harness) -> None:
    h.install_real_plist()
    state = _restartable_app(h)

    h.invoke("restart")

    assert state["at_kickstart"] is None


def test_restart_waits_while_the_old_app_drains(h: Harness) -> None:
    h.install_real_plist()
    started = {"new": False}
    drain_until = 6.0

    def health() -> dict[str, Any] | None:
        if started["new"]:
            return healthy("1.1.0")
        return healthy("1.0.0") if h.now < drain_until else None

    h.health = health
    h.on_launchctl = lambda cmd: started.update(new=True) if cmd[1] == "kickstart" else None

    result = h.invoke("restart")

    assert result.exit_code == 0, result.output
    assert h.now >= drain_until


def test_restart_waits_for_the_old_process_to_exit_not_only_for_health(h: Harness) -> None:
    """Uvicorn closes its socket first and finishes cleanup later (CodeRabbit, PR 119)."""
    h.install_real_plist()
    socket_closed_at, process_exits_at = 2.0, 8.0
    state: dict[str, Any] = {"new": False, "kickstart_at": None}

    def health() -> dict[str, Any] | None:
        if state["new"]:
            return healthy("1.1.0")
        return healthy("1.0.0") if h.now < socket_closed_at else None

    def on(cmd: list[str]) -> None:
        if cmd[1] == "kickstart":
            state["kickstart_at"] = h.now
            state["new"] = True

    h.health = health
    h.alive = lambda: state["new"] or h.now < process_exits_at
    h.on_launchctl = on

    result = h.invoke("restart")

    assert result.exit_code == 0, result.output
    assert state["kickstart_at"] is not None
    assert state["kickstart_at"] >= process_exits_at


def test_restart_stops_when_the_process_never_exits_although_health_is_down(h: Harness) -> None:
    h.install_real_plist()
    h.health = lambda: None
    h.alive = lambda: True

    result = h.invoke("restart")

    assert result.exit_code != 0
    assert h.changes() == ["kill"]
    assert h.now >= 15.0


def test_restart_restarts_an_app_that_is_still_starting_up(h: Harness) -> None:
    """Health is down but the process lives, for example while it loads models."""
    h.install_real_plist()
    state: dict[str, Any] = {"alive": True, "new": False}
    h.health = lambda: healthy("1.1.0") if state["new"] else None
    h.alive = lambda: state["alive"] or state["new"]

    def on(cmd: list[str]) -> None:
        if cmd[1] == "kill":
            state["alive"] = False
        if cmd[1] == "kickstart":
            state["new"] = True

    h.on_launchctl = on

    result = h.invoke("restart")

    assert result.exit_code == 0, result.output
    assert h.changes() == ["kill", "kickstart"]


def test_restart_stops_when_the_old_app_does_not_stop(h: Harness) -> None:
    h.install_real_plist()
    h.serve()

    result = h.invoke("restart")

    assert result.exit_code != 0
    assert h.changes() == ["kill"]
    assert h.now >= 15.0
    assert "omrg web status" in flat(result.output)


def test_restart_starts_an_app_that_is_not_running(h: Harness) -> None:
    """After a clean exit launchd keeps the app stopped; restart starts it."""
    h.install_real_plist()
    state: dict[str, Any] = {"version": None}
    h.health = lambda: healthy("1.1.0") if state["version"] else None
    h.on_launchctl = lambda cmd: state.update(version="1.1.0") if cmd[1] == "kickstart" else None

    result = h.invoke("restart")

    assert result.exit_code == 0, result.output
    assert h.changes() == ["kickstart"]


def test_restart_reports_a_new_app_that_never_answers(h: Harness) -> None:
    h.install_real_plist()
    state = _restartable_app(h, new=None)

    result = h.invoke("restart")

    assert state["version"] is None
    assert result.exit_code != 0
    assert h.now >= 60.0
    assert str(h.error_log) in flat(result.output)


class _Launchd:
    """A fake launchd that respawns the app by itself after a signal.

    Uvicorn re-raises SIGTERM, so launchd sees a crash and starts a new
    process. The old process is 42, the one launchd starts is 43 and the one
    ``kickstart`` starts is 44. *respawn_after* is the number of seconds
    between ``kill`` and launchd's own start; ``None`` means launchd never
    starts one.
    """

    def __init__(self, h: Harness, respawn_after: float | None, new: str = "1.1.0") -> None:
        self.h = h
        self.respawn_after = respawn_after
        self.new = new
        self.killed_at: float | None = None
        self.kickstarted_at: float | None = None
        h.pid = self.pid
        h.health = self.health
        h.on_launchctl = self.on_launchctl

    def pid(self) -> int | None:
        if self.kickstarted_at is not None:
            return 44
        if self.killed_at is None:
            return 42
        if self.respawn_after is not None and self.h.now - self.killed_at >= self.respawn_after:
            return 43
        return None

    def health(self) -> dict[str, Any] | None:
        pid = self.pid()
        if pid is None:
            return None
        return healthy("1.0.0" if pid == 42 else self.new)

    def on_launchctl(self, cmd: list[str]) -> None:
        if cmd[1] == "kill":
            self.killed_at = self.h.now
        if cmd[1] == "kickstart":
            self.kickstarted_at = self.h.now


@pytest.mark.parametrize("respawn_after", [0.0, 1.0])
def test_restart_does_not_kickstart_when_launchd_starts_a_new_process_at_once(
    h: Harness, respawn_after: float
) -> None:
    """The signal ends the old process by signal; launchd starts a new one within 1 s.

    At 0.0 the pid goes from 42 straight to 43, so the old process is gone
    although no poll ever sees "no process".
    """
    h.install_real_plist()
    launchd = _Launchd(h, respawn_after=respawn_after)

    result = h.invoke("restart")

    assert result.exit_code == 0, result.output
    assert h.changes() == ["kill"]
    assert launchd.kickstarted_at is None
    assert "1.1.0" in result.output


def test_restart_waits_in_the_grace_for_a_new_process_before_it_kickstarts(h: Harness) -> None:
    """A new process 3 s after the signal is inside the 5 s grace."""
    h.install_real_plist()
    launchd = _Launchd(h, respawn_after=3.0)

    result = h.invoke("restart")

    assert result.exit_code == 0, result.output
    assert h.changes() == ["kill"]
    assert launchd.kickstarted_at is None


def test_restart_kickstarts_once_after_the_grace_when_launchd_starts_nothing(h: Harness) -> None:
    h.install_real_plist()
    launchd = _Launchd(h, respawn_after=None)

    result = h.invoke("restart")

    assert result.exit_code == 0, result.output
    assert h.changes() == ["kill", "kickstart"]
    assert launchd.killed_at is not None and launchd.kickstarted_at is not None
    assert launchd.kickstarted_at - launchd.killed_at >= wl.RESPAWN_GRACE == 5.0


def test_restart_fails_without_kickstart_when_the_old_process_never_ends(h: Harness) -> None:
    h.install_real_plist()
    h.pid = lambda: 42
    h.health = lambda: healthy("1.0.0")

    result = h.invoke("restart")

    assert result.exit_code != 0
    assert h.changes() == ["kill"]
    assert h.now >= wl.STOP_TIMEOUT
    assert "omrg web status" in flat(result.output)


def test_restart_only_kills_and_kickstarts_when_nothing_is_running(h: Harness) -> None:
    """No health and no process id: there is nothing to stop."""
    h.install_real_plist()
    h.pid = lambda: None
    h.health = lambda: None
    h.on_launchctl = lambda cmd: (
        setattr(h, "health", lambda: healthy("1.1.0")) if (cmd[1] == "kickstart") else None
    )

    result = h.invoke("restart")

    assert result.exit_code == 0, result.output
    assert h.changes() == ["kickstart"]


def test_restart_treats_the_same_process_id_as_not_restarted_although_health_blinked(
    h: Harness,
) -> None:
    """Health went down and came back, but the process id is still the old one."""
    h.install_real_plist()
    state = {"killed_at": None}
    h.pid = lambda: 42
    h.health = lambda: (
        None
        if state["killed_at"] is not None and h.now < state["killed_at"] + 3.0
        else healthy("1.0.0")
    )
    h.on_launchctl = lambda cmd: state.update(killed_at=h.now) if cmd[1] == "kill" else None

    result = h.invoke("restart")

    assert result.exit_code != 0
    assert h.changes() == ["kill"]
    assert "omrg web status" in flat(result.output)


def test_restart_waits_for_health_to_stop_when_the_process_id_is_unreadable(h: Harness) -> None:
    """Health answers but ``launchctl print`` shows no pid: wait for the health to stop."""
    h.install_real_plist()
    state: dict[str, Any] = {"killed_at": None, "kickstarted": False}
    h.pid = lambda: None

    def health() -> dict[str, Any] | None:
        if state["kickstarted"]:
            return healthy("1.1.0")
        if state["killed_at"] is None or h.now < state["killed_at"] + 4.0:
            return healthy("1.0.0")
        return None

    def on(cmd: list[str]) -> None:
        if cmd[1] == "kill":
            state["killed_at"] = h.now
        if cmd[1] == "kickstart":
            state["kickstarted"] = True
            state["kickstart_at"] = h.now

    h.health = health
    h.on_launchctl = on

    result = h.invoke("restart")

    assert result.exit_code == 0, result.output
    assert h.changes() == ["kill", "kickstart"]
    assert state["kickstart_at"] - state["killed_at"] >= 4.0


def test_restart_reports_a_launchctl_failure(h: Harness) -> None:
    h.install_real_plist()
    h.launchctl_rc["kickstart"] = 113

    result = h.invoke("restart")

    assert result.exit_code != 0
    assert "kickstart" in flat(result.output)


def test_restart_when_not_installed(h: Harness) -> None:
    result = h.invoke("restart")

    assert result.exit_code != 0
    assert "not installed" in flat(result.output).lower()
    assert "omrg web install" in flat(result.output)
    assert h.launchctl_calls == []


# ── open ─────────────────────────────────────────────────────────────────


def test_open_opens_the_link_and_hides_the_secret(h: Harness) -> None:
    h.install_real_plist()
    h.write_link(fragment="omrg_bs_TOPSECRET")
    h.serve()

    result = h.invoke("open")

    assert result.exit_code == 0, result.output
    assert h.opened == ["http://127.0.0.1:8765/#bootstrap=omrg_bs_TOPSECRET"]
    assert "TOPSECRET" not in result.output
    assert "http://127.0.0.1:8765/" in result.output


def test_open_print_shows_the_full_link_and_opens_nothing(h: Harness) -> None:
    h.install_real_plist()
    h.write_link(fragment="omrg_bs_TOPSECRET")
    h.serve()

    result = h.invoke("open", "--print")

    assert result.exit_code == 0, result.output
    assert "http://127.0.0.1:8765/#bootstrap=omrg_bs_TOPSECRET" in flat(result.output)
    assert h.opened == []


def test_open_checks_health_on_the_port_in_the_link(h: Harness) -> None:
    h.install_real_plist()
    h.write_link(port=9123)
    h.serve()

    h.invoke("open")

    assert h.health_ports == [9123]


def test_open_follows_the_workspace_of_the_installed_login_item(h: Harness, tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    h.install_real_plist(workspace=ws)
    h.write_link(workspace=ws)
    h.serve()

    result = h.invoke("open")

    assert result.exit_code == 0, result.output
    assert len(h.opened) == 1


def test_open_without_a_link_file_says_the_login_item_is_not_running(h: Harness) -> None:
    h.install_real_plist()
    h.serve()

    result = h.invoke("open")

    assert result.exit_code != 0
    assert "not running" in flat(result.output)
    assert "omrg web status" in flat(result.output)
    assert h.opened == []


def test_open_with_an_old_link_file_and_a_dead_port_opens_nothing(h: Harness) -> None:
    h.install_real_plist()
    h.write_link()

    result = h.invoke("open")

    assert result.exit_code != 0
    assert "not running" in flat(result.output)
    assert h.opened == []


def test_open_when_not_installed(h: Harness) -> None:
    result = h.invoke("open")

    assert result.exit_code != 0
    assert "not running" in flat(result.output)
    assert h.opened == []


def test_open_reports_a_browser_that_does_not_open(h: Harness) -> None:
    h.install_real_plist()
    h.write_link(fragment="omrg_bs_TOPSECRET")
    h.serve()
    h.open_rc = 1

    result = h.invoke("open")

    assert result.exit_code != 0
    assert "--print" in flat(result.output)
    assert "TOPSECRET" not in result.output


def test_open_never_starts_a_server(h: Harness) -> None:
    h.install_real_plist()
    h.write_link()
    h.serve()

    h.invoke("open")

    assert h.launchctl_calls == []
