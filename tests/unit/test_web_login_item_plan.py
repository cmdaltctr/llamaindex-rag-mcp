"""Plan and plist of the web login item (add-web-login-item, group 3).

Pure logic: the plan, the plist, the checkout and settings checks, and the
health, version and link helpers. Every path derives from an explicit
temporary ``home``, so no test touches the real ``~/Library``.
"""

from __future__ import annotations

import json
import plistlib
import subprocess
from pathlib import Path
from typing import Any

import pytest

from omrs.transports.cli import _web_login_item as wli
from omrs.transports.cli import _web_login_item_settings as login_settings
from omrs.transports.cli._launchagent import InstallerError


@pytest.fixture
def home(tmp_path: Path) -> Path:
    path = tmp_path / "home"
    path.mkdir()
    return path


def _plan(home: Path, **kwargs: Any) -> wli.WebLoginItemPlan:
    kwargs.setdefault("command_path", "/opt/omrs/bin/omrs")
    return wli.build_plan(home=home, **kwargs)


def _plist(plan: wli.WebLoginItemPlan) -> dict[str, Any]:
    return plistlib.loads(wli.render_plist(plan))


# ── Label and paths ──────────────────────────────────────────────────────


def test_label_and_paths(home: Path) -> None:
    plan = _plan(home)

    assert plan.label == "com.omrs.web"
    assert plan.plist_path == home / "Library" / "LaunchAgents" / "com.omrs.web.plist"
    assert plan.stdout_log == home / "Library" / "Logs" / "omrs" / "com.omrs.web.out.log"
    assert plan.stderr_log == home / "Library" / "Logs" / "omrs" / "com.omrs.web.err.log"


def test_working_directory_is_the_absolute_omrs_folder(home: Path) -> None:
    plan = _plan(home)

    assert plan.working_directory == home / ".omrs"
    assert plan.working_directory.is_absolute()
    assert _plist(plan)["WorkingDirectory"] == str(home / ".omrs")


# ── Arguments ────────────────────────────────────────────────────────────


def test_arguments_without_options(home: Path) -> None:
    plan = _plan(home)

    assert wli.build_program_arguments(plan) == ["/opt/omrs/bin/omrs", "web", "--login-item"]


def test_workspace_option_reaches_the_arguments(home: Path, tmp_path: Path) -> None:
    ws = tmp_path / "ws"

    args = wli.build_program_arguments(_plan(home, workspace=ws))

    assert args[-2:] == ["--workspace", str(ws)]


def test_port_option_reaches_the_arguments(home: Path) -> None:
    args = wli.build_program_arguments(_plan(home, port=9000))

    assert args[-2:] == ["--port", "9000"]


def test_root_options_reach_the_arguments_as_absolute_paths(home: Path, tmp_path: Path) -> None:
    one, two = tmp_path / "one", tmp_path / "two"

    args = wli.build_program_arguments(_plan(home, roots=(one, two)))

    assert args[3:] == ["--root", str(one), "--root", str(two)]


def test_experiment_root_option_reaches_the_arguments(home: Path, tmp_path: Path) -> None:
    exp = tmp_path / "exp"

    args = wli.build_program_arguments(_plan(home, experiment_roots=(exp,)))

    assert args[3:] == ["--experiment-root", str(exp)]


def test_options_are_made_absolute(
    home: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)

    args = wli.build_program_arguments(_plan(home, roots=(Path("papers"),)))

    assert args[4] == str((tmp_path / "papers").resolve())


def test_a_tilde_option_is_expanded(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(home))

    args = wli.build_program_arguments(_plan(home, roots=(Path("~/papers"),)))

    assert args[4] == str(home / "papers")


def test_workspace_is_absent_from_the_plist_when_not_given(home: Path) -> None:
    argv = _plist(_plan(home))["ProgramArguments"]

    assert "--workspace" not in argv
    assert "--port" not in argv


# ── Plist keys ───────────────────────────────────────────────────────────


def test_plist_runs_at_load_and_restarts_only_after_a_crash(home: Path) -> None:
    data = _plist(_plan(home))

    assert data["Label"] == "com.omrs.web"
    assert data["RunAtLoad"] is True
    assert data["KeepAlive"] == {"SuccessfulExit": False}
    assert data["ThrottleInterval"] == 60


def test_plist_gives_a_fixed_path(home: Path) -> None:
    data = _plist(_plan(home))

    assert data["EnvironmentVariables"] == {
        "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
    }


def test_plist_names_the_logs(home: Path) -> None:
    plan = _plan(home)
    data = _plist(plan)

    assert data["StandardOutPath"] == str(plan.stdout_log)
    assert data["StandardErrorPath"] == str(plan.stderr_log)


# ── Executable ───────────────────────────────────────────────────────────


def test_relative_command_path_is_refused(home: Path) -> None:
    with pytest.raises(InstallerError, match="absolute"):
        wli.build_plan(home=home, command_path="omrs")


def test_checkout_warning_fires_for_a_venv_in_a_git_checkout(tmp_path: Path) -> None:
    (tmp_path / "proj" / ".git").mkdir(parents=True)

    warning = wli.checkout_warning(str(tmp_path / "proj" / ".venv" / "bin" / "omrs"))

    assert warning is not None
    assert "uv tool install" in warning


def test_checkout_warning_accepts_a_git_file(tmp_path: Path) -> None:
    """A worktree holds a ``.git`` file, not a folder."""
    (tmp_path / "proj").mkdir()
    (tmp_path / "proj" / ".git").write_text("gitdir: elsewhere", encoding="utf-8")

    assert wli.checkout_warning(str(tmp_path / "proj" / ".venv" / "bin" / "omrs")) is not None


def test_checkout_warning_is_silent_without_git(tmp_path: Path) -> None:
    (tmp_path / "proj").mkdir()

    assert wli.checkout_warning(str(tmp_path / "proj" / ".venv" / "bin" / "omrs")) is None


def test_checkout_warning_is_silent_for_an_installed_tool(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()

    assert wli.checkout_warning(str(tmp_path / ".local" / "bin" / "omrs")) is None


# ── Settings file ────────────────────────────────────────────────────────


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    return tmp_path / "home" / ".config" / "omrs" / "omrs.jsonc"


def test_settings_rows_name_the_file_and_the_optional_dotenv(config_file: Path) -> None:
    rows = " ".join(login_settings.plan_rows(config_file, home=config_file.parents[2]))

    assert "~/.config/omrs/omrs.jsonc" in rows
    assert "~/.omrs/.env" in rows
    assert "optional" in rows
    assert "overrides" in rows


def test_missing_settings_file_suggests_config_init(config_file: Path, tmp_path: Path) -> None:
    messages = login_settings.plan_warnings(
        config_file, tmp_path / "cwd", home=config_file.parents[2]
    )

    assert len(messages) == 1
    assert "~/.config/omrs/omrs.jsonc" in messages[0]
    assert "omrs config init" in messages[0]


def test_existing_settings_file_gives_no_warning(config_file: Path, tmp_path: Path) -> None:
    config_file.parent.mkdir(parents=True)
    config_file.write_text("{}\n", encoding="utf-8")

    assert (
        login_settings.plan_warnings(config_file, tmp_path / "cwd", home=config_file.parents[2])
        == []
    )


def test_dotenv_in_the_working_folder_is_reported_as_not_read(
    config_file: Path, tmp_path: Path
) -> None:
    config_file.parent.mkdir(parents=True)
    config_file.write_text("{}\n", encoding="utf-8")
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    (cwd / ".env").write_text("OPENROUTER_API_KEY=sentinel-value\n", encoding="utf-8")

    messages = login_settings.plan_warnings(config_file, cwd, home=config_file.parents[2])

    assert len(messages) == 1
    assert "does not read" in messages[0]
    assert str(cwd / ".env") in messages[0]
    assert "omrs config init" in messages[0]
    assert "sentinel-value" not in messages[0]


def test_settings_text_creates_nothing(config_file: Path, tmp_path: Path) -> None:
    login_settings.plan_rows(config_file, home=config_file.parents[2])
    login_settings.plan_warnings(config_file, tmp_path, home=config_file.parents[2])

    assert not config_file.parent.exists()


# ── Names shared with the server ─────────────────────────────────────────


def test_link_file_name_matches_the_server() -> None:
    pytest.importorskip("fastapi")
    from omrs.transports.api.launch_link import LINK_FILE_NAME

    assert wli.LINK_FILE_NAME == LINK_FILE_NAME


def test_default_workspace_matches_the_core_default(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from omrs.core.workspace import default_workspace

    monkeypatch.setenv("HOME", str(home))

    assert wli.workspace_dir(_plan(home)) == default_workspace()


def test_workspace_dir_prefers_the_option(home: Path, tmp_path: Path) -> None:
    assert wli.workspace_dir(_plan(home, workspace=tmp_path / "ws")) == tmp_path / "ws"
    assert wli.link_file(_plan(home, workspace=tmp_path / "ws")) == tmp_path / "ws" / "launch-link"


# ── Link, health and version helpers ─────────────────────────────────────


def test_parse_link_splits_the_address_from_the_secret() -> None:
    info = wli.parse_link("http://127.0.0.1:8765/#bootstrap=omrs_bs_abc\n")

    assert info is not None
    assert (info.host, info.port) == ("127.0.0.1", 8765)
    assert info.address == "http://127.0.0.1:8765/"
    assert info.url == "http://127.0.0.1:8765/#bootstrap=omrs_bs_abc"
    assert "omrs_bs_abc" not in info.address


def test_parse_link_reads_an_ipv6_host() -> None:
    info = wli.parse_link("http://[::1]:9001/#bootstrap=x")

    assert info is not None
    assert (info.host, info.port) == ("::1", 9001)


@pytest.mark.parametrize(
    "text", ["", "not a link", "ftp://127.0.0.1:1/#bootstrap=x", "http://127.0.0.1/"]
)
def test_parse_link_refuses_anything_else(text: str) -> None:
    assert wli.parse_link(text) is None


def test_fetch_health_returns_the_reported_body() -> None:
    seen: list[tuple[str, int, str]] = []

    def get(host: str, port: int, path: str, timeout: float) -> bytes:
        seen.append((host, port, path))
        return json.dumps({"status": "ok", "ready": True, "version": "3.1.0"}).encode()

    body = wli.fetch_health("127.0.0.1", 8765, get=get)

    assert body == {"status": "ok", "ready": True, "version": "3.1.0"}
    assert seen == [("127.0.0.1", 8765, "/v1/health")]


@pytest.mark.parametrize("failure", [OSError("refused"), TimeoutError()])
def test_fetch_health_returns_none_when_nothing_answers(failure: Exception) -> None:
    def get(host: str, port: int, path: str, timeout: float) -> bytes:
        raise failure

    assert wli.fetch_health("127.0.0.1", 8765, get=get) is None


def test_fetch_health_returns_none_for_a_body_that_is_not_the_app() -> None:
    def get(host: str, port: int, path: str, timeout: float) -> bytes:
        return b"<html>hello</html>"

    assert wli.fetch_health("127.0.0.1", 8765, get=get) is None


def test_installed_version_reads_the_executable_output() -> None:
    calls: list[list[str]] = []

    def run(cmd: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="omrs 3.2.1\n", stderr="")

    assert wli.installed_version("/opt/omrs/bin/omrs", run=run) == "3.2.1"
    assert calls == [["/opt/omrs/bin/omrs", "--version"]]


@pytest.mark.parametrize("outcome", ["missing", "failed", "garbled"])
def test_installed_version_is_none_when_it_cannot_be_read(outcome: str) -> None:
    def run(cmd: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        if outcome == "missing":
            raise FileNotFoundError(cmd[0])
        if outcome == "failed":
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="boom")
        return subprocess.CompletedProcess(cmd, 0, stdout="hello\n", stderr="")

    assert wli.installed_version("/opt/omrs/bin/omrs", run=run) is None


# ── Reading an installed plist back ──────────────────────────────────────


def test_read_installed_returns_what_install_wrote(home: Path, tmp_path: Path) -> None:
    plan = _plan(home, workspace=tmp_path / "ws", port=9000)
    plan.plist_path.parent.mkdir(parents=True)
    plan.plist_path.write_bytes(wli.render_plist(plan))

    item = wli.read_installed(plan.plist_path)

    assert item == wli.InstalledItem(
        command_path="/opt/omrs/bin/omrs", workspace=tmp_path / "ws", port=9000
    )


def test_read_installed_reports_absent_options_as_none(home: Path) -> None:
    plan = _plan(home)
    plan.plist_path.parent.mkdir(parents=True)
    plan.plist_path.write_bytes(wli.render_plist(plan))

    item = wli.read_installed(plan.plist_path)

    assert item is not None
    assert (item.workspace, item.port) == (None, None)


@pytest.mark.parametrize("content", [None, b"not a plist", plistlib.dumps({"Label": "x"})])
def test_read_installed_returns_none_for_a_missing_or_foreign_file(
    tmp_path: Path, content: bytes | None
) -> None:
    path = tmp_path / "x.plist"
    if content is not None:
        path.write_bytes(content)

    assert wli.read_installed(path) is None
