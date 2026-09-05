"""CLI-level tests for ``rag-mcp install-login-watcher``.

Covers OpenSpec change ``add-login-watcher-installer``:
- Requirement: CLI subcommand ``rag-mcp install-login-watcher``
- Requirement: Guided interactive setup
- Requirement: Non-interactive installation
- Requirement: LaunchAgent plist generation
- Requirement: Existing watcher safety
- Requirement: Optional initial catch-up ingest
- Requirement: LaunchAgent loading and immediate start
- Task 3.6 word regression: ``watch`` help uses vector-store wording
"""

from __future__ import annotations

import os
import plistlib
import re
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from llama_index.core.embeddings import MockEmbedding
from typer.testing import CliRunner

from omrg.transports.cli import app

runner = CliRunner()

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from Rich-formatted help output."""
    return _ANSI_RE.sub("", text)


def _installer():
    """Return the command module; ModuleNotFoundError until implemented."""
    from omrg.transports.cli import install_login_watcher

    return install_login_watcher


@pytest.fixture
def invoke_happy(tmp_path):
    """Return a callable performing the canonical non-interactive run.

    Catch-up ingest stays off; the ingest and profile patches exist only
    to guarantee no composition-root side effects leak into this flow.
    """

    def _run(watch_dir: Path, home: Path, extra_args: list[str] | None = None):
        fake_bin = tmp_path / "fakebin"
        fake_bin.mkdir(exist_ok=True)
        stub_cmd = str(fake_bin / "rag-mcp")
        with (
            patch("shutil.which", return_value=stub_cmd),
            patch("omrg.core.ingestion.ingest_path_async", new=AsyncMock()),
            patch("omrg.compose.build_profile_resolver"),
        ):
            result = runner.invoke(
                app,
                [
                    "install-login-watcher",
                    "--path",
                    str(watch_dir),
                    "--collection",
                    "research",
                    *(extra_args or []),
                ],
            )
        return result, {"stub_cmd": stub_cmd}

    return _run


@pytest.fixture
def macos_home(monkeypatch: pytest.MonkeyPatch):
    """Force macOS detection and redirect home into tmp space.

    Returns ``_apply(home_dir)`` which monkeypatches ``Path.home`` plus the
    command helpers so no test can ever touch the real ``~/Library``.
    """

    def _apply(home: Path) -> Path:
        from omrg.transports.cli import install_login_watcher

        home.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(Path, "home", lambda: home)
        monkeypatch.setattr(install_login_watcher, "_is_macos", lambda: True)
        monkeypatch.setattr(install_login_watcher, "_stdin_is_interactive", lambda: False)
        return home

    return _apply


# ── Help text ─────────────────────────────────────────────────────────


class TestHelpText:
    """Scenario: Help describes guided and scriptable usage."""

    def test_ansi_stripping_reassembles_styled_option_token(self) -> None:
        """A Rich style boundary inside an option name does not hide the token."""
        assert _strip_ansi("-\x1b[1;36m-path\x1b[0m") == "--path"

    def test_help_lists_all_options(self) -> None:
        """--help shows purpose plus every scriptable option group."""
        result = runner.invoke(app, ["install-login-watcher", "--help"])
        assert result.exit_code == 0
        output = _strip_ansi(result.output)
        for token in (
            "--path",
            "--collection",
            "--debounce",
            "--label",
            "--command-path",
            "--dry-run",
            "--force",
            "--initial-ingest",
            "--load",
            "--start",
            "--yes",
        ):
            assert token in output, f"--help missing {token}"

    def test_watch_help_word_regression_no_chromadb(self) -> None:
        """Task 3.6: watch help must use vector-store, not ChromaDB, terms."""
        result = runner.invoke(app, ["watch", "--help"])
        assert result.exit_code == 0
        assert "ChromaDB" not in result.output


# ── Platform gate and basic validation failures ───────────────────────


class TestPlatformAndInputGates:
    """Scenarios: Non-macOS rejected; Missing path; Invalid folder."""

    def test_non_macos_rejected_without_dry_run(self, monkeypatch) -> None:
        """Linux platforms fail fast unless --dry-run is passed."""
        monkeypatch.setattr(_installer(), "_is_macos", lambda: False)
        result = runner.invoke(app, ["install-login-watcher"])
        assert result.exit_code != 0
        assert "macos" in result.output.lower()
        assert "Traceback" not in result.output

    def test_missing_path_non_interactive_errors(self, monkeypatch) -> None:
        """Non-interactive stdin without --path names the missing option."""
        monkeypatch.setattr(_installer(), "_is_macos", lambda: True)
        monkeypatch.setattr(_installer(), "_stdin_is_interactive", lambda: False)
        result = runner.invoke(app, ["install-login-watcher"])
        assert result.exit_code != 0
        assert "--path" in result.output

    def test_invalid_path_missing_dir_errors(self, monkeypatch) -> None:
        """A non-existent directory fails validation."""
        monkeypatch.setattr(_installer(), "_is_macos", lambda: True)
        monkeypatch.setattr(_installer(), "_stdin_is_interactive", lambda: False)
        result = runner.invoke(
            app,
            ["install-login-watcher", "--path", "/nope/missing/dir"],
        )
        assert result.exit_code != 0
        assert "Traceback" not in result.output

    def test_invalid_path_file_not_dir_errors(self, monkeypatch, tmp_path) -> None:
        """A regular file fails the directory check."""
        plain_file = tmp_path / "f.txt"
        plain_file.write_text("x")
        monkeypatch.setattr(_installer(), "_is_macos", lambda: True)
        monkeypatch.setattr(_installer(), "_stdin_is_interactive", lambda: False)
        result = runner.invoke(app, ["install-login-watcher", "-p", str(plain_file)])
        assert result.exit_code != 0


# ── Happy-path generation ────────────────────────────────────────────


class TestPlistGeneration:
    """Scenario: Scriptable install; Plist contains watcher command."""

    def test_scriptable_install_writes_valid_plist(
        self, macos_home, invoke_happy, tmp_path
    ) -> None:
        """Explicit options generate a parseable LaunchAgent plist."""
        home = macos_home(tmp_path / "h")
        watched = tmp_path / "docs"
        watched.mkdir()
        result, meta = invoke_happy(watched, home)
        assert result.exit_code == 0, result.output

        # Scenarios: Install without immediate start; Log paths are reported.
        output_lower = result.output.lower()
        assert "next login" in output_lower or "load" in output_lower
        assert ".out.log" in output_lower and ".err.log" in output_lower

        launchagents = home / "Library/LaunchAgents"
        plists = list(launchagents.glob("*.plist"))
        assert len(plists) == 1
        data = plistlib.loads(plists[0].read_bytes())

        label = data["Label"]
        assert isinstance(label, str) and label.startswith("com.rag-mcp.watch.")
        args = data["ProgramArguments"]
        assert Path(args[0]) in {
            Path(meta["stub_cmd"]),
            Path(os.path.realpath(meta["stub_cmd"])),
        }
        assert args[1:] == [
            "watch",
            str(watched.resolve()),
            "--collection",
            "research",
            "--debounce",
            "2.0",
        ]
        assert data["RunAtLoad"] is True
        assert data["KeepAlive"] is False
        logs_root = home / "Library/Logs/rag-mcp"
        assert Path(data["StandardOutPath"]).parent == logs_root
        assert Path(data["StandardErrorPath"]).parent == logs_root

    def test_command_path_override_used_exactly(self, macos_home, tmp_path) -> None:
        """--command-path becomes ProgramArguments[0] verbatim."""
        home = macos_home(tmp_path / "h")
        watched = tmp_path / "docs2"
        watched.mkdir()
        override = "/opt/homebrew/bin/rag-mcp"
        with (
            patch("omrg.core.ingestion.ingest_path_async", new=AsyncMock()),
            patch("omrg.compose.build_profile_resolver"),
        ):
            result = runner.invoke(
                app,
                [
                    "install-login-watcher",
                    "--path",
                    str(watched),
                    "--yes",
                    "--command-path",
                    override,
                ],
            )
        assert result.exit_code == 0, result.output
        plist_path = next((home / "Library/LaunchAgents").glob("*.plist"))
        data = plistlib.loads(plist_path.read_bytes())
        assert data["ProgramArguments"][0] == override


class TestExistingWatcherSafety:
    """Scenario: Existing plist protection with --force update."""

    def test_existing_plist_protected_without_force(
        self, macos_home, invoke_happy, tmp_path
    ) -> None:
        """Without --force a same-label re-run leaves the plist untouched."""
        home = macos_home(tmp_path / "h")
        watched = tmp_path / "docs3"
        watched.mkdir()
        first_run, _meta = invoke_happy(watched, home)
        assert first_run.exit_code == 0
        plist_path = next((home / "Library/LaunchAgents").glob("*.plist"))
        original_bytes = plist_path.read_bytes()

        second_run, _m2 = invoke_happy(watched, home)  # same plan → same label
        assert second_run.exit_code != 0
        assert "--force" in second_run.output
        assert plist_path.read_bytes() == original_bytes

    def test_existing_plist_replaced_with_force(self, macos_home, invoke_happy, tmp_path) -> None:
        """--force allows replacement and reports success."""
        home = macos_home(tmp_path / "h")
        watched = tmp_path / "docs4"
        watched.mkdir()
        first_run, _m = invoke_happy(watched, home)
        assert first_run.exit_code == 0
        second_run, _m2 = invoke_happy(watched, home, extra_args=["--force"])
        assert second_run.exit_code == 0, second_run.output


# ── Different-label replacement: refuse, instruct, or consent ────────


class TestDifferentLabelReplacement:
    """A different label watching the same folder is a live duplicate.

    Non-consented runs refuse with exact removal instructions; --force or
    an interactive confirmation removes the old watcher (bootout + plist
    delete) before installing the new one (CodeRabbit major finding).
    """

    @staticmethod
    def _seed_other_label(home: Path, watched: Path) -> Path:
        """Seed a generated-style plist with a different label; return it."""
        label = f"com.rag-mcp.watch.{watched.name}-deadbeef"
        plist_path = home / "Library/LaunchAgents" / f"{label}.plist"
        plist_path.parent.mkdir(parents=True, exist_ok=True)
        plist_path.write_bytes(
            plistlib.dumps(
                {
                    "Label": label,
                    "ProgramArguments": [
                        "/fake/bin/rag-mcp",
                        "watch",
                        str(watched.resolve()),
                        "--collection",
                        "old-collection",
                        "--debounce",
                        "2.0",
                    ],
                }
            )
        )
        return plist_path

    def test_refuses_and_instructs_without_force(self, macos_home, tmp_path) -> None:
        """Non-interactive, no --force: refuse, print removal commands, exit 1."""
        home = macos_home(tmp_path / "hr")
        watched = tmp_path / "dl-docs"
        watched.mkdir()
        old_plist = self._seed_other_label(home, watched)
        old_bytes = old_plist.read_bytes()
        with (
            patch("shutil.which", return_value="/fake/bin/rag-mcp"),
            patch("omrg.core.ingestion.ingest_path_async", new=AsyncMock()),
            patch("omrg.compose.build_profile_resolver"),
            patch("omrg.transports.cli._launchagent.run_launchctl", new=MagicMock()) as mock_lc,
        ):
            result = runner.invoke(
                app,
                ["install-login-watcher", "--path", str(watched), "--yes"],
            )
        assert result.exit_code != 0
        output = result.output
        assert "different watcher label" in output
        assert (
            f"launchctl bootout gui/{os.getuid()} com.rag-mcp.watch.{watched.name}-deadbeef"
            in output
        )
        # Rich hard-wraps long tokens at the console width, so flatten
        # before matching the rm command and the plist name.
        flat = output.replace("\n", "").replace(" ", "")
        assert "rm'" in flat and old_plist.name in flat
        assert "--force" in output
        mock_lc.assert_not_called()
        assert old_plist.read_bytes() == old_bytes
        agents = home / "Library/LaunchAgents"
        assert [p.name for p in agents.glob("*.plist")] == [old_plist.name]

    def test_force_removes_old_and_installs_new(self, macos_home, tmp_path) -> None:
        """--force: bootout the old label, delete its plist, install one new."""
        home = macos_home(tmp_path / "hq")
        watched = tmp_path / "df-docs"
        watched.mkdir()
        old_plist = self._seed_other_label(home, watched)
        ok = subprocess.CompletedProcess(args=[], returncode=0)
        with (
            patch("shutil.which", return_value="/fake/bin/rag-mcp"),
            patch("omrg.core.ingestion.ingest_path_async", new=AsyncMock()),
            patch("omrg.compose.build_profile_resolver"),
            patch(
                "omrg.transports.cli._launchagent.run_launchctl",
                new=MagicMock(return_value=ok),
            ) as mock_lc,
        ):
            result = runner.invoke(
                app,
                [
                    "install-login-watcher",
                    "--path",
                    str(watched),
                    "--yes",
                    "--force",
                ],
            )
        assert result.exit_code == 0, result.output
        assert not old_plist.exists()
        plists = list((home / "Library/LaunchAgents").glob("*.plist"))
        assert len(plists) == 1  # exactly one watcher remains
        assert plists[0].stem != old_plist.stem
        bootouts = [
            c
            for c in mock_lc.call_args_list
            if c.args and c.args[0][:2] == ["launchctl", "bootout"]
        ]
        assert any(c.args[0][2] == f"gui/{os.getuid()}/{old_plist.stem}" for c in bootouts), (
            f"old label not booted out: {mock_lc.call_args_list}"
        )

    def test_interactive_confirmation_removes_old(self, macos_home, monkeypatch, tmp_path) -> None:
        """Interactive 'y' at the removal prompt consents to the delete."""
        home = macos_home(tmp_path / "hy")
        monkeypatch.setattr(_installer(), "_stdin_is_interactive", lambda: True)
        watched = tmp_path / "di-docs"
        watched.mkdir()
        old_plist = self._seed_other_label(home, watched)
        ok = subprocess.CompletedProcess(args=[], returncode=0)
        with (
            patch("shutil.which", return_value="/fake/bin/rag-mcp"),
            patch("omrg.core.ingestion.ingest_path_async", new=AsyncMock()),
            patch("omrg.compose.build_profile_resolver"),
            patch(
                "omrg.transports.cli._launchagent.run_launchctl",
                new=MagicMock(return_value=ok),
            ),
        ):
            result = runner.invoke(
                app,
                ["install-login-watcher", "--path", str(watched), "--collection", "research"],
                input="n\ny\ny\n",  # catch-up, removal prompt, wizard summary
            )
        assert result.exit_code == 0, result.output
        assert not old_plist.exists()
        plists = list((home / "Library/LaunchAgents").glob("*.plist"))
        assert len(plists) == 1
        assert "Removing existing watcher" in result.output

    def test_interactive_decline_leaves_everything_unchanged(
        self, macos_home, monkeypatch, tmp_path
    ) -> None:
        """Interactive 'n' aborts with instructions and writes nothing."""
        home = macos_home(tmp_path / "hn2")
        monkeypatch.setattr(_installer(), "_stdin_is_interactive", lambda: True)
        watched = tmp_path / "dn-docs"
        watched.mkdir()
        old_plist = self._seed_other_label(home, watched)
        old_bytes = old_plist.read_bytes()
        with (
            patch("shutil.which", return_value="/fake/bin/rag-mcp"),
            patch("omrg.core.ingestion.ingest_path_async", new=AsyncMock()),
            patch("omrg.compose.build_profile_resolver"),
            patch("omrg.transports.cli._launchagent.run_launchctl", new=MagicMock()) as mock_lc,
        ):
            result = runner.invoke(
                app,
                ["install-login-watcher", "--path", str(watched), "--collection", "research"],
                input="n\nn\n",  # catch-up decline, removal decline
            )
        assert result.exit_code != 0
        assert "launchctl bootout" in result.output  # instructions shown
        mock_lc.assert_not_called()
        assert old_plist.read_bytes() == old_bytes
        agents = home / "Library/LaunchAgents"
        assert [p.name for p in agents.glob("*.plist")] == [old_plist.name]

    def test_summary_decline_after_removal_consent_keeps_old(
        self, macos_home, monkeypatch, tmp_path
    ) -> None:
        """Consent to removal, then decline the summary: old watcher stays.

        The removal is deferred until after every abort gate, so an
        abort can never strand the user with no watcher (CodeRabbit).
        """
        home = macos_home(tmp_path / "hs2")
        monkeypatch.setattr(_installer(), "_stdin_is_interactive", lambda: True)
        watched = tmp_path / "sd2-docs"
        watched.mkdir()
        old_plist = self._seed_other_label(home, watched)
        old_bytes = old_plist.read_bytes()
        with (
            patch("shutil.which", return_value="/fake/bin/rag-mcp"),
            patch("omrg.core.ingestion.ingest_path_async", new=AsyncMock()),
            patch("omrg.compose.build_profile_resolver"),
            patch("omrg.transports.cli._launchagent.run_launchctl", new=MagicMock()) as mock_lc,
        ):
            result = runner.invoke(
                app,
                ["install-login-watcher", "--path", str(watched), "--collection", "research"],
                input="n\ny\nn\n",  # catch-up, removal consent, summary decline
            )
        assert result.exit_code != 0
        assert "nothing was written" in result.output.lower()
        mock_lc.assert_not_called()  # removal never executed
        assert old_plist.read_bytes() == old_bytes
        agents = home / "Library/LaunchAgents"
        assert [p.name for p in agents.glob("*.plist")] == [old_plist.name]

    def test_ingest_gate_abort_after_removal_consent_keeps_old(
        self, macos_home, monkeypatch, tmp_path
    ) -> None:
        """Consent, confirm summary, then decline after ingest failure."""
        home = macos_home(tmp_path / "hi2")
        monkeypatch.setattr(_installer(), "_stdin_is_interactive", lambda: True)
        watched = tmp_path / "ig2-docs"
        watched.mkdir()
        old_plist = self._seed_other_label(home, watched)
        old_bytes = old_plist.read_bytes()
        with (
            patch("shutil.which", return_value="/fake/bin/rag-mcp"),
            patch(
                "omrg.core.ingestion.ingest_path_async",
                new=AsyncMock(return_value={"status": "error", "message": "boom"}),
            ),
            patch("omrg.compose.build_profile_resolver"),
            patch("omrg.transports.cli._launchagent.run_launchctl", new=MagicMock()) as mock_lc,
        ):
            result = runner.invoke(
                app,
                [
                    "install-login-watcher",
                    "--path",
                    str(watched),
                    "--collection",
                    "research",
                    "--initial-ingest",
                ],
                input="y\ny\nn\n",  # removal consent, summary, continue-anyway decline
            )
        assert result.exit_code != 0
        assert "no launchagent was installed" in result.output.lower()
        assert "partial results" in result.output.lower()
        mock_lc.assert_not_called()
        assert old_plist.read_bytes() == old_bytes
        agents = home / "Library/LaunchAgents"
        assert [p.name for p in agents.glob("*.plist")] == [old_plist.name]

    def test_force_stops_when_bootout_fails_and_agent_loaded(self, macos_home, tmp_path) -> None:
        """A still-loaded old agent stops the install; plist is kept."""
        home = macos_home(tmp_path / "hb")
        watched = tmp_path / "bl-docs"
        watched.mkdir()
        old_plist = self._seed_other_label(home, watched)
        old_bytes = old_plist.read_bytes()

        def _launchctl(cmd: list[str]) -> subprocess.CompletedProcess:
            op = cmd[1] if len(cmd) > 1 else ""
            rc = 0 if op == "print" else 1  # bootout fails, probe says loaded
            return subprocess.CompletedProcess(args=cmd, returncode=rc)

        with (
            patch("shutil.which", return_value="/fake/bin/rag-mcp"),
            patch("omrg.core.ingestion.ingest_path_async", new=AsyncMock()),
            patch("omrg.compose.build_profile_resolver"),
            patch(
                "omrg.transports.cli._launchagent.run_launchctl",
                side_effect=_launchctl,
            ),
        ):
            result = runner.invoke(
                app,
                ["install-login-watcher", "--path", str(watched), "--yes", "--force"],
            )
        assert result.exit_code != 0
        assert "still loaded" in result.output
        assert "launchctl bootout" in result.output  # manual instructions
        assert old_plist.read_bytes() == old_bytes  # old watcher unchanged
        agents = home / "Library/LaunchAgents"
        assert [p.name for p in agents.glob("*.plist")] == [old_plist.name]

    def test_force_proceeds_when_bootout_fails_not_loaded(self, macos_home, tmp_path) -> None:
        """Bootout failing because the label never loaded is benign."""
        home = macos_home(tmp_path / "hu2")
        watched = tmp_path / "nl-docs"
        watched.mkdir()
        old_plist = self._seed_other_label(home, watched)

        def _launchctl(cmd: list[str]) -> subprocess.CompletedProcess:
            return subprocess.CompletedProcess(args=cmd, returncode=1)

        with (
            patch("shutil.which", return_value="/fake/bin/rag-mcp"),
            patch("omrg.core.ingestion.ingest_path_async", new=AsyncMock()),
            patch("omrg.compose.build_profile_resolver"),
            patch(
                "omrg.transports.cli._launchagent.run_launchctl",
                side_effect=_launchctl,
            ),
        ):
            result = runner.invoke(
                app,
                ["install-login-watcher", "--path", str(watched), "--yes", "--force"],
            )
        assert result.exit_code == 0, result.output
        assert "was not loaded" in result.output
        assert not old_plist.exists()
        plists = list((home / "Library/LaunchAgents").glob("*.plist"))
        assert len(plists) == 1


class TestDryRun:
    """Scenario: Dry run previews without writing."""

    def test_dry_run_prints_plan_and_writes_nothing(self, macos_home, tmp_path) -> None:
        """Dry-run surfaces the plan but performs zero mutations."""
        home = macos_home(tmp_path / "h")
        watched = tmp_path / "docs5"
        watched.mkdir()
        with (
            patch("omrg.core.ingestion.ingest_path_async", new=AsyncMock()),
            patch("omrg.compose.build_profile_resolver"),
            patch(
                "omrg.transports.cli._launchagent.run_launchctl",
                new=MagicMock(return_value=subprocess.CompletedProcess(args=[], returncode=0)),
            ) as mock_launchctl,
        ):
            result = runner.invoke(
                app,
                [
                    "install-login-watcher",
                    "--path",
                    str(watched),
                    "--collection",
                    "research",
                    "--dry-run",
                ],
            )
        assert result.exit_code == 0, result.output
        assert "plist" in result.output.lower()
        assert (home / "Library/LaunchAgents").exists() is False
        mock_launchctl.assert_not_called()


# ── Interactive wizard ───────────────────────────────────────────────


class TestInteractiveWizard:
    """Scenarios: Wizard collects missing values; invalid folder re-prompt.

    The input sequences below are contractual: folder prompt accepts the
    invalid entry, explains it, asks again, then collection (default),
    initial-ingest confirm, and final summary confirmation follow.
    """

    def test_wizard_collects_values_with_default_collection(
        self, macos_home, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """Prompts collect folder, collection default, ingest choice, summary."""
        home = macos_home(tmp_path / "hw")
        monkeypatch.setattr(_installer(), "_stdin_is_interactive", lambda: True)
        watched = tmp_path / "wizard-docs"
        watched.mkdir()
        text_input = f"{watched}\n\nn\ny\n\n\n\n"
        with (
            patch("omrg.core.ingestion.ingest_path_async", new=AsyncMock()),
            patch("omrg.compose.build_profile_resolver"),
            patch(
                "omrg.transports.cli._launchagent.run_launchctl",
                new=MagicMock(return_value=subprocess.CompletedProcess(args=[], returncode=0)),
            ),
        ):
            result = runner.invoke(
                app,
                ["install-login-watcher"],
                input=text_input,
            )
        assert result.exit_code == 0, result.output
        output_lower = result.output.lower()
        assert "collection" in output_lower
        assert "ingest" in output_lower
        plists = list((home / "Library/LaunchAgents").glob("*.plist"))
        assert len(plists) >= 1

    def test_invalid_folder_reprompted(
        self, macos_home, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """A bad folder answer explains the failure and prompts again."""
        home = macos_home(tmp_path / "hw")
        monkeypatch.setattr(_installer(), "_stdin_is_interactive", lambda: True)
        watched = tmp_path / "wizard-valid"
        watched.mkdir()
        bad = tmp_path / "not-a-dir.txt"
        bad.write_text("x")
        text_input = f"{bad}\n{watched}\n\nn\ny\n\n\n\n"
        with (
            patch("omrg.core.ingestion.ingest_path_async", new=AsyncMock()),
            patch("omrg.compose.build_profile_resolver"),
            patch(
                "omrg.transports.cli._launchagent.run_launchctl",
                new=MagicMock(return_value=subprocess.CompletedProcess(args=[], returncode=0)),
            ),
        ):
            result = runner.invoke(
                app,
                ["install-login-watcher"],
                input=text_input,
            )
        assert result.exit_code == 0, result.output
        assert "exist" in result.output.lower() or "directory" in result.output.lower()
        plists = list((home / "Library/LaunchAgents").glob("*.plist"))
        assert len(plists) >= 1


# ── Optional catch-up ingestion ──────────────────────────────────────


class TestInitialIngest:
    """Scenarios: Initial ingest before load; failure stops installation."""

    @staticmethod
    def _invoke(watched: Path, extra: list[str]):
        """Shared invocation helper for ingest-related runs."""
        return runner.invoke(
            app,
            ["install-login-watcher", "--path", str(watched), *extra],
        )

    def test_ingest_runs_before_load_with_injected_settings(
        self, effective_settings, macos_home, tmp_path
    ) -> None:
        """Catch-up ingest precedes bootstrap and receives the profile settings."""
        home = macos_home(tmp_path / "hi")
        watched = tmp_path / "ing-docs"
        watched.mkdir()
        _ = home  # patched home guarantees no write outside tmp space
        sentinel_settings = effective_settings(collection_name="research")
        resolver = MagicMock()
        resolver.resolve.return_value = sentinel_settings

        parent = MagicMock()
        with (
            patch("omrg.compose.build_profile_resolver", return_value=resolver),
            patch(
                "omrg.core.ingestion.ingest_path_async",
                new=AsyncMock(
                    return_value={"status": "success", "files_indexed": 3, "chunks_created": 7}
                ),
            ) as mock_ing,
            patch(
                "omrg.transports.cli._launchagent.run_launchctl",
                new=MagicMock(return_value=subprocess.CompletedProcess(args=[], returncode=0)),
            ) as mock_lc,
        ):
            parent.attach_mock(mock_ing, "ingest")
            parent.attach_mock(mock_lc, "launchctl")
            result = self._invoke(
                watched,
                ["--collection", "research", "--initial-ingest", "--load", "--yes"],
            )

        assert result.exit_code == 0, result.output
        kinds = [c[0] for c in parent.mock_calls]
        first_ingest = next(i for i, k in enumerate(kinds) if k.startswith("ingest"))
        first_launch = next(i for i, k in enumerate(kinds) if k.startswith("launchctl"))
        assert first_ingest < first_launch

        call_kwargs = mock_ing.call_args.kwargs
        assert call_kwargs["collection_name"] == "research"
        assert call_kwargs["effective_settings"] is sentinel_settings
        positional = mock_ing.call_args.args
        assert Path(positional[0]).resolve() == watched.resolve()

    def test_profile_resolution_failure_is_fail_closed(
        self, effective_settings, macos_home, tmp_path
    ) -> None:
        """A resolver error aborts before any file write or launchctl call."""
        home = macos_home(tmp_path / "hf")
        watched = tmp_path / "pf-docs"
        watched.mkdir()
        resolver = MagicMock()
        resolver.resolve.side_effect = ValueError("No profile registered for collection 'research'")
        with (
            patch("omrg.compose.build_profile_resolver", return_value=resolver),
            patch("omrg.core.ingestion.ingest_path_async", new=AsyncMock()) as mock_ing,
            patch("omrg.transports.cli._launchagent.run_launchctl", new=MagicMock()) as mock_lc,
        ):
            result = self._invoke(
                watched,
                ["--collection", "research", "--initial-ingest", "--load", "--yes"],
            )
        assert result.exit_code != 0
        assert "profile" in result.output.lower() or "research" in result.output
        mock_ing.assert_not_called()
        mock_lc.assert_not_called()
        assert not (home / "Library/LaunchAgents").exists() or not any(
            (home / "Library/LaunchAgents").iterdir()
        )

    def test_ingest_error_stops_install_without_force(
        self, effective_settings, macos_home, tmp_path
    ) -> None:
        """An errored catch-up ingest prevents plist write and load."""
        home = macos_home(tmp_path / "he")
        watched = tmp_path / "ie-docs"
        watched.mkdir()
        with (
            patch("omrg.compose.build_profile_resolver"),
            patch(
                "omrg.core.ingestion.ingest_path_async",
                new=AsyncMock(return_value={"status": "error", "message": "boom"}),
            ),
            patch("omrg.transports.cli._launchagent.run_launchctl", new=MagicMock()) as mock_lc,
        ):
            result = self._invoke(
                watched,
                ["--collection", "research", "--initial-ingest", "--load", "--yes"],
            )
        assert result.exit_code != 0
        assert "boom" in result.output
        mock_lc.assert_not_called()
        agents = home / "Library/LaunchAgents"
        assert not agents.exists() or not any(agents.iterdir())

    def test_ingest_error_proceeds_when_forced(
        self, effective_settings, macos_home, tmp_path
    ) -> None:
        """--force lets installation continue after an errored ingest."""
        home = macos_home(tmp_path / "hg")
        watched = tmp_path / "if-docs"
        watched.mkdir()
        with (
            patch("omrg.compose.build_profile_resolver"),
            patch(
                "omrg.core.ingestion.ingest_path_async",
                new=AsyncMock(return_value={"status": "error", "message": "boom"}),
            ),
            patch(
                "omrg.transports.cli._launchagent.run_launchctl",
                new=MagicMock(return_value=subprocess.CompletedProcess(args=[], returncode=0)),
            ) as mock_lc,
        ):
            result = self._invoke(
                watched,
                [
                    "--collection",
                    "research",
                    "--initial-ingest",
                    "--load",
                    "--yes",
                    "--force",
                ],
            )
        assert result.exit_code == 0, result.output
        plists = list((home / "Library/LaunchAgents").glob("*.plist"))
        assert len(plists) == 1
        assert mock_lc.called

    def test_profile_resolution_failure_not_bypassed_by_force(
        self, effective_settings, macos_home, tmp_path
    ) -> None:
        """--force never bypasses the fail-closed profile gate (audit F7, design D8)."""
        home = macos_home(tmp_path / "hn")
        watched = tmp_path / "nf-docs"
        watched.mkdir()
        resolver = MagicMock()
        resolver.resolve.side_effect = ValueError("No profile registered")
        with (
            patch("omrg.compose.build_profile_resolver", return_value=resolver),
            patch("omrg.core.ingestion.ingest_path_async", new=AsyncMock()),
            patch("omrg.transports.cli._launchagent.run_launchctl", new=MagicMock()) as mock_lc,
        ):
            result = self._invoke(
                watched,
                [
                    "--collection",
                    "research",
                    "--initial-ingest",
                    "--load",
                    "--yes",
                    "--force",
                ],
            )
        assert result.exit_code != 0
        mock_lc.assert_not_called()
        agents = home / "Library/LaunchAgents"
        assert not agents.exists() or not any(agents.iterdir())

    def test_dash_prefixed_collection_rejected(self, macos_home, tmp_path) -> None:
        """A collection starting with '-' is refused (audit F4)."""
        macos_home(tmp_path / "hd")
        watched = tmp_path / "dp-docs"
        watched.mkdir()
        with (
            patch("omrg.core.ingestion.ingest_path_async", new=AsyncMock()),
            patch("omrg.compose.build_profile_resolver"),
        ):
            result = self._invoke(watched, ["--collection", "-evil", "--yes"])
        assert result.exit_code != 0
        assert "must not start with" in result.output

    def test_catchup_exception_treated_as_ingest_error(
        self, effective_settings, macos_home, tmp_path
    ) -> None:
        """A raised ingest error stops the install exactly like an error dict."""
        home = macos_home(tmp_path / "hx")
        watched = tmp_path / "ex-docs"
        watched.mkdir()
        with (
            patch("omrg.compose.build_profile_resolver"),
            patch(
                "omrg.core.ingestion.ingest_path_async",
                new=AsyncMock(side_effect=RuntimeError("kaboom")),
            ),
            patch("omrg.transports.cli._launchagent.run_launchctl", new=MagicMock()) as mock_lc,
        ):
            result = self._invoke(
                watched, ["--collection", "research", "--initial-ingest", "--yes"]
            )
        assert result.exit_code != 0
        assert "kaboom" in result.output
        mock_lc.assert_not_called()
        agents = home / "Library/LaunchAgents"
        assert not agents.exists() or not any(agents.iterdir())


# ── Loading and starting ────────────────────────────────────────────


class TestLoadAndStart:
    """Scenarios: load bootstrap, kickstart on start, failure surfacing."""

    def test_load_invokes_bootstrap_for_gui_domain(self, macos_home, tmp_path) -> None:
        """--load bootstraps the agent into gui/<uid> with the plist path."""
        home = macos_home(tmp_path / "hl")
        watched = tmp_path / "ld-docs"
        watched.mkdir()
        uid = os.getuid()
        with (
            patch("omrg.core.ingestion.ingest_path_async", new=AsyncMock()),
            patch("omrg.compose.build_profile_resolver"),
            patch(
                "omrg.transports.cli._launchagent.run_launchctl",
                new=MagicMock(return_value=subprocess.CompletedProcess(args=[], returncode=0)),
            ) as mock_lc,
        ):
            result = self.invoke(watched, ["--load", "--yes"])
        assert result.exit_code == 0, result.output
        bootstrap_calls = [
            c
            for c in mock_lc.call_args_list
            if c.args and c.args[0][:2] == ["launchctl", "bootstrap"]
        ]
        assert bootstrap_calls, f"expected bootstrap among {mock_lc.call_args_list}"
        argv = bootstrap_calls[0].args[0]
        assert f"gui/{uid}" in argv
        assert Path(argv[-1]).parent == home / "Library/LaunchAgents"

    def test_start_adds_kickstart(self, macos_home, tmp_path) -> None:
        """--start implies load and additionally kicks the agent."""
        macos_home(tmp_path / "hs")
        watched = tmp_path / "st-docs"
        watched.mkdir()
        with (
            patch("omrg.core.ingestion.ingest_path_async", new=AsyncMock()),
            patch("omrg.compose.build_profile_resolver"),
            patch(
                "omrg.transports.cli._launchagent.run_launchctl",
                new=MagicMock(return_value=subprocess.CompletedProcess(args=[], returncode=0)),
            ) as mock_lc,
        ):
            result = self.invoke(watched, ["--start", "--yes"])
        assert result.exit_code == 0, result.output
        kinds = [c.args[0][1] for c in mock_lc.call_args_list if c.args]
        assert "bootstrap" in kinds
        assert "kickstart" in kinds

    def test_launchctl_failure_surfaces_stderr(self, macos_home, tmp_path) -> None:
        """A failing bootstrap shows stderr and exits non-zero."""
        macos_home(tmp_path / "hu")
        watched = tmp_path / "fl-docs"
        watched.mkdir()
        failed = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="launchctl boom"
        )
        with (
            patch("omrg.core.ingestion.ingest_path_async", new=AsyncMock()),
            patch("omrg.compose.build_profile_resolver"),
            patch(
                "omrg.transports.cli._launchagent.run_launchctl",
                new=MagicMock(return_value=failed),
            ),
        ):
            result = self.invoke(watched, ["--load", "--yes"])
        assert result.exit_code != 0
        assert "launchctl boom" in result.output

    @staticmethod
    def invoke(watched: Path, extra: list[str]):
        """Invoke install-login-watcher with common baseline arguments."""
        return runner.invoke(
            app,
            ["install-login-watcher", "--path", str(watched), *extra],
        )


# ── Adapter-conditional contention warning (design risk) ────────────


class TestContentionWarning:
    """The duplicate-watcher warning is conditional on the store adapter."""

    @staticmethod
    def _seed_existing(home: Path, watched: Path) -> Path:
        """Create a different-label plist watching the same folder; return it."""
        label = f"com.rag-mcp.watch.{watched.name}"
        existing = home / "Library/LaunchAgents" / f"{label}.plist"
        existing.parent.mkdir(parents=True, exist_ok=True)
        existing.write_bytes(
            plistlib.dumps(
                {
                    "Label": label,
                    "ProgramArguments": [
                        "/fake/bin/rag-mcp",
                        "watch",
                        str(watched.resolve()),
                        "--collection",
                        "other",
                        "--debounce",
                        "2.0",
                    ],
                }
            )
        )
        return existing

    def test_warning_shown_when_adapter_lacks_write_isolation(self, macos_home, tmp_path) -> None:
        """Chroma-style adapters get the vector-store contention warning."""
        home = macos_home(tmp_path / "hc")
        watched = tmp_path / "cw-docs"
        watched.mkdir()
        self._seed_existing(home, watched)
        with (
            patch("shutil.which", return_value="/fake/bin/rag-mcp"),
            patch("omrg.core.ingestion.ingest_path_async", new=AsyncMock()),
            patch("omrg.compose.build_profile_resolver"),
            patch("omrg.compose._resolve_active_strategies"),
            patch(
                "omrg.compose.build_embed_model",
                return_value=MockEmbedding(embed_dim=8),
            ),
            patch("omrg.compose.build_vector_store", return_value=MagicMock()),
            patch("omrg.compose.settings_to_effective", return_value=MagicMock()),
            patch("omrg.config.get_settings") as mock_settings,
            patch("omrg.core.vectordb.registry.describe") as mock_describe,
        ):
            mock_settings.return_value = MagicMock(vector_store="fakestore")
            mock_describe.return_value = {"cross_process_writes_safe": False}
            result = runner.invoke(
                app,
                [
                    "install-login-watcher",
                    "--path",
                    str(watched),
                    "--collection",
                    "research",
                    "--yes",
                ],
            )
        assert result.exit_code != 0  # no --force: protected
        output_lower = result.output.lower()
        assert "fakestore" in output_lower
        assert "concurrent" in output_lower
        assert "chromadb" not in output_lower  # vector-store wording only

    def test_warning_names_the_process_local_write_lock(self, macos_home, tmp_path) -> None:
        """The warning keeps the point that separate processes do not
        share the internal write lock."""
        home = macos_home(tmp_path / "hw")
        watched = tmp_path / "wl-docs"
        watched.mkdir()
        self._seed_existing(home, watched)
        with (
            patch("shutil.which", return_value="/fake/bin/rag-mcp"),
            patch("omrg.core.ingestion.ingest_path_async", new=AsyncMock()),
            patch("omrg.compose.build_profile_resolver"),
            patch("omrg.compose._resolve_active_strategies"),
            patch(
                "omrg.compose.build_embed_model",
                return_value=MockEmbedding(embed_dim=8),
            ),
            patch("omrg.compose.build_vector_store", return_value=MagicMock()),
            patch("omrg.compose.settings_to_effective", return_value=MagicMock()),
            patch("omrg.config.get_settings") as mock_settings,
            patch("omrg.core.vectordb.registry.describe") as mock_describe,
        ):
            mock_settings.return_value = MagicMock(vector_store="fakestore")
            mock_describe.return_value = {"cross_process_writes_safe": False}
            result = runner.invoke(
                app,
                [
                    "install-login-watcher",
                    "--path",
                    str(watched),
                    "--collection",
                    "research",
                    "--yes",
                ],
            )
        assert result.exit_code != 0  # no --force: protected
        assert "write lock" in result.output.lower()

    def test_no_warning_when_adapter_isolates_writers(self, macos_home, tmp_path) -> None:
        """LanceDB-style adapters emit no contention warning."""
        home = macos_home(tmp_path / "hk")
        watched = tmp_path / "cw2-docs"
        watched.mkdir()
        self._seed_existing(home, watched)
        with (
            patch("shutil.which", return_value="/fake/bin/rag-mcp"),
            patch("omrg.core.ingestion.ingest_path_async", new=AsyncMock()),
            patch("omrg.compose.build_profile_resolver"),
            patch("omrg.compose._resolve_active_strategies"),
            patch(
                "omrg.compose.build_embed_model",
                return_value=MockEmbedding(embed_dim=8),
            ),
            patch("omrg.compose.build_vector_store", return_value=MagicMock()),
            patch("omrg.compose.settings_to_effective", return_value=MagicMock()),
            patch("omrg.config.get_settings") as mock_settings,
            patch("omrg.core.vectordb.registry.describe") as mock_describe,
        ):
            mock_settings.return_value = MagicMock(vector_store="fakestore")
            mock_describe.return_value = {"cross_process_writes_safe": True}
            result = runner.invoke(
                app,
                [
                    "install-login-watcher",
                    "--path",
                    str(watched),
                    "--collection",
                    "research",
                    "--yes",
                ],
            )
        assert result.exit_code != 0  # still protected without --force
        assert "concurrent" not in result.output.lower()


# ── Wizard summary decline ───────────────────────────────────────────


class TestWizardSummaryDecline:
    """The final summary confirmation can abort before any write."""

    def test_summary_decline_writes_nothing(self, macos_home, monkeypatch, tmp_path) -> None:
        """Answering 'n' at the summary exits non-zero with no plist."""
        home = macos_home(tmp_path / "hj")
        monkeypatch.setattr(_installer(), "_stdin_is_interactive", lambda: True)
        watched = tmp_path / "sd-docs"
        watched.mkdir()
        text_input = f"{watched}\n\nn\nn\n"
        with (
            patch("omrg.core.ingestion.ingest_path_async", new=AsyncMock()),
            patch("omrg.compose.build_profile_resolver"),
            patch("omrg.transports.cli._launchagent.run_launchctl", new=MagicMock()),
        ):
            result = runner.invoke(app, ["install-login-watcher"], input=text_input)
        assert result.exit_code != 0
        assert "nothing was written" in result.output.lower()
        agents = home / "Library/LaunchAgents"
        assert not agents.exists() or not any(agents.iterdir())
