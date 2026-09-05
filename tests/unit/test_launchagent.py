"""Unit tests for ``omrg.transports.cli._launchagent``.

Covers OpenSpec change ``add-login-watcher-installer``:
- Requirement: LaunchAgent plist generation (deterministic label and paths;
  plist contains watcher command)
- Requirement: CLI subcommand support utilities (command resolution,
  path validation)
- Requirement: Existing watcher safety (atomic write, overwrite protection)
- Tasks 1.1-1.4, 2.1, 2.2, 2.4
"""

from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# ── Loaders ────────────────────────────────────────────────────────────


@pytest.fixture
def la():
    """Import the module under test; errors cleanly while unimplemented."""
    from omrg.transports.cli import _launchagent

    return _launchagent


@pytest.fixture
def make_plan(la):
    """Return a factory building a fully-populated LaunchAgentPlan."""

    def _factory(**overrides):
        from omrg.transports.cli._launchagent import LaunchAgentPlan

        base = {
            "label": "com.rag-mcp.watch.docs",
            "watch_path": Path("/docs"),
            "collection": "documents",
            "debounce": 2.0,
            "command_path": "/usr/local/bin/rag-mcp",
            "run_at_load": True,
            "keep_alive": False,
            "plist_path": Path("/Users/t/Library/LaunchAgents/com.rag-mcp.watch.docs.plist"),
            "stdout_log": Path("/Users/t/Library/Logs/rag-mcp/com.rag-mcp.watch.docs.out.log"),
            "stderr_log": Path("/Users/t/Library/Logs/rag-mcp/com.rag-mcp.watch.docs.err.log"),
        }
        base.update(overrides)
        return LaunchAgentPlan(**base)

    return _factory


# ── Label generation (task 1.3, spec: Deterministic label and paths) ──


class TestGenerateLabel:
    """Deterministic label derivation with com.rag-mcp.watch. prefix."""

    def test_same_inputs_same_label(self, la, tmp_path: Path) -> None:
        """Identical watch path and collection produce identical labels."""
        first = la.generate_label(tmp_path, "research")
        second = la.generate_label(tmp_path, "research")
        assert first == second
        assert first.startswith("com.rag-mcp.watch.")

    def test_different_collection_different_label(self, la, tmp_path: Path) -> None:
        """Changing the collection changes the derived label."""
        assert la.generate_label(tmp_path, "research") != la.generate_label(tmp_path, "documents")

    def test_custom_label_is_slugified(self, la) -> None:
        """A custom label is used after slugification."""
        label = la.generate_label(Path("/docs"), "research", custom="My Watcher!")
        assert label.startswith("com.rag-mcp.watch.")
        # Slug characters only: no spaces or punctuation leftovers.
        tail = label.removeprefix("com.rag-mcp.watch.")
        assert tail and all(c.isalnum() or c in "-_" for c in tail)


class TestSlugifyLabelPart:
    """Slug behaviour for unsafe characters and empty input."""

    def test_spaces_and_slashes_become_hyphens(self, la) -> None:
        """Spaces and slashes map to hyphens."""
        slug = la.slugify_label_part("My Docs/Folder Two")
        assert "/" not in slug
        assert " " not in slug
        assert slug

    def test_max_length_truncates(self, la) -> None:
        """Output respects max_length."""
        slug = la.slugify_label_part("a" * 80, max_length=40)
        assert len(slug) <= 40

    def test_empty_input_falls_back(self, la) -> None:
        """An empty slug yields a non-empty safe fallback."""
        slug = la.slugify_label_part("")
        assert slug
        assert "/" not in slug and " " not in slug

    def test_leading_trailing_dashes_stripped(self, la) -> None:
        """Edge dashes cannot smuggle option-like prefixes into labels (audit F7)."""
        assert la.slugify_label_part("-x") == "x"
        assert la.slugify_label_part("--force-") == "force"


# ── Watch path validation (task 1.2) ──────────────────────────────────


class TestValidateWatchPath:
    """Directory validation with expansion and resolution."""

    def test_missing_path_rejected(self, la) -> None:
        """A non-existent path raises InstallerError."""
        with pytest.raises(la.InstallerError):
            la.validate_watch_path("/nonexistent/definitely-missing")

    def test_file_not_directory_rejected(self, la, tmp_path: Path) -> None:
        """A regular file raises InstallerError."""
        a_file = tmp_path / "notes.txt"
        a_file.write_text("hi")
        with pytest.raises(la.InstallerError):
            la.validate_watch_path(a_file)

    def test_valid_directory_resolves_absolute(self, la, tmp_path: Path) -> None:
        """A valid directory returns its absolute resolved form."""
        watched = tmp_path / "docs"
        watched.mkdir()
        resolved = la.validate_watch_path(str(watched))
        assert resolved.is_absolute()
        assert resolved == watched.resolve()

    def test_symlinked_directory_resolves_to_target(self, la, tmp_path: Path) -> None:
        """A symlink to a directory resolves to the real directory."""
        target = tmp_path / "real"
        target.mkdir()
        link = tmp_path / "link"
        link.symlink_to(target)
        assert la.validate_watch_path(link) == target.resolve()

    def test_tilde_expansion_uses_home(
        self, la, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``~/docs`` expands against the monkeypatched home directory."""
        fake_home = tmp_path / "fake-home"
        docs = fake_home / "docs"
        docs.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        assert la.validate_watch_path("~/docs") == docs.resolve()

    def test_bare_tilde_returns_home(
        self, la, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``~`` alone expands to the home directory."""
        fake_home = tmp_path / "bare-home"
        fake_home.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        assert la.validate_watch_path("~") == fake_home.resolve()

    def test_tilde_user_form_rejected_even_when_target_exists(
        self, la, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``~alice/docs`` is refused, not guessed as ``<home>/alice/docs``."""
        fake_home = tmp_path / "user-home"
        alice_docs = fake_home / "alice" / "docs"
        alice_docs.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        with pytest.raises(la.InstallerError, match="absolute path"):
            la.validate_watch_path("~alice/docs")


# ── Paths and command resolution (tasks 1.4, 1.5) ─────────────────────


class TestComputePaths:
    """Plist and log path layout under a supplied home."""

    def test_layout(self, la) -> None:
        """Returns plist under LaunchAgents and logs under Logs/rag-mcp."""
        plist_path, out_log, err_log = la.compute_paths("com.rag-mcp.watch.x", home=Path("/h"))
        assert plist_path == Path("/h/Library/LaunchAgents/com.rag-mcp.watch.x.plist")
        assert out_log == Path("/h/Library/Logs/rag-mcp/com.rag-mcp.watch.x.out.log")
        assert err_log == Path("/h/Library/Logs/rag-mcp/com.rag-mcp.watch.x.err.log")


class TestResolveCommandPath:
    """Absolute executable resolution with override priority."""

    def test_override_used_verbatim(self, la) -> None:
        """An explicit override wins over discovery."""
        assert la.resolve_command_path("/opt/homebrew/bin/rag-mcp") == "/opt/homebrew/bin/rag-mcp"

    def test_relative_override_rejected(self, la) -> None:
        """A relative override fails loudly — launchd could never start it (audit F2)."""
        with pytest.raises(la.InstallerError) as exc_info:
            la.resolve_command_path("bin/rag-mcp")
        assert "absolute" in str(exc_info.value)

    def test_shutil_which_preferred_when_present(self, la) -> None:
        """shutil.which result is preferred and returned absolute."""
        with patch("shutil.which", return_value="/fake/bin/rag-mcp"):
            assert la.resolve_command_path(None) == str(Path("/fake/bin/rag-mcp"))

    def test_sibling_of_interpreter_as_fallback(self, la) -> None:
        """Without which(), the interpreter's bin sibling is used if present."""
        sibling = Path(sys.executable).parent / "rag-mcp"
        sibling_exists = sibling.exists()

        with patch("shutil.which", return_value=None):
            if sibling_exists:
                assert la.resolve_command_path(None) == str(sibling)
            else:
                with pytest.raises(la.InstallerError) as exc_info:
                    la.resolve_command_path(None)
                assert "--command-path" in str(exc_info.value)


# ── Command argv builders (task 2.4) ─────────────────────────────────


class TestCommandBuilders:
    """launchctl argv construction for GUI domain operations."""

    def test_build_program_arguments(self, la, make_plan) -> None:
        """Program arguments mirror the watch invocation."""
        plan = make_plan(debounce=3.0)
        assert la.build_program_arguments(plan) == [
            plan.command_path,
            "watch",
            str(plan.watch_path),
            "--collection",
            plan.collection,
            "--debounce",
            "3.0",
        ]

    def test_bootstrap_command(self, la) -> None:
        """bootstrap targets gui/<uid> with the plist path."""
        uid = os.getuid()
        cmd = la.bootstrap_command(uid, Path("/p/x.plist"))
        assert cmd[0] == "launchctl"
        assert cmd[1] == "bootstrap"
        assert f"gui/{uid}" in cmd
        assert str(Path("/p/x.plist")) in cmd

    def test_bootout_command(self, la) -> None:
        """bootout targets gui/<uid>/<label>."""
        cmd = la.bootout_command(501, "com.rag-mcp.watch.x")
        assert cmd[1] == "bootout"
        assert cmd[-1] == "gui/501/com.rag-mcp.watch.x"

    def test_kickstart_command(self, la) -> None:
        """kickstart targets gui/<uid>/<label>."""
        cmd = la.kickstart_command(501, "com.rag-mcp.watch.x")
        assert cmd[1] == "kickstart"
        assert cmd[-1] == "gui/501/com.rag-mcp.watch.x"


# ── Plist rendering and writing (tasks 2.1, 2.2) ─────────────────────


class TestRenderAndWritePlist:
    """Plist serialisation plus atomic, protected writes."""

    def test_render_produces_parseable_plist_with_required_keys(self, la, make_plan) -> None:
        """Rendered bytes parse and contain every mandatory key."""
        raw = la.render_plist(make_plan())
        data = plistlib.loads(raw)
        assert isinstance(data, dict)
        for key in (
            "Label",
            "ProgramArguments",
            "RunAtLoad",
            "KeepAlive",
            "StandardOutPath",
            "StandardErrorPath",
        ):
            assert key in data

    def test_write_creates_parents_and_returns_path(self, la, make_plan, tmp_path: Path) -> None:
        """Writing creates the LaunchAgents directory tree."""
        deep_home = tmp_path / "home"
        plan = make_plan(plist_path=deep_home / "Library/LaunchAgents/l.plist")
        written = la.write_plist(plan, b"<plist><dict/></plist>")
        assert written == plan.plist_path
        assert written.read_bytes() == b"<plist><dict/></plist>"

    def test_existing_file_protected_without_overwrite(self, la, make_plan, tmp_path: Path) -> None:
        """An existing plist raises ExistingPlistError and stays unchanged."""
        target = tmp_path / "Library/LaunchAgents/l.plist"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"OLD-CONTENT")
        plan = make_plan(plist_path=target)

        with pytest.raises(la.ExistingPlistError) as exc_info:
            la.write_plist(plan, b"NEW-CONTENT")

        assert exc_info.value.plist_path == target
        assert target.read_bytes() == b"OLD-CONTENT"  # preserved atomically

    def test_overwrite_flag_replaces_content(self, la, make_plan, tmp_path: Path) -> None:
        """overwrite=True replaces an existing plist."""
        target = tmp_path / "Library/LaunchAgents/l.plist"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"OLD")
        plan = make_plan(plist_path=target)
        la.write_plist(plan, b"NEW", overwrite=True)
        assert target.read_bytes() == b"NEW"


# ── Existing-watcher detection (exact watch-path matching) ──────────


class TestFindExistingPlist:
    """Slug glob is a shortlist; the persisted watch path is the verdict."""

    @staticmethod
    def _seed(plist_path: Path, watch_path: Path, label: str | None = None) -> Path:
        """Write a parseable installer-style plist; return its path."""
        plist_path.parent.mkdir(parents=True, exist_ok=True)
        plist_path.write_bytes(
            plistlib.dumps(
                {
                    "Label": label or plist_path.stem,
                    "ProgramArguments": [
                        "/fake/bin/rag-mcp",
                        "watch",
                        str(watch_path),
                        "--collection",
                        "other",
                        "--debounce",
                        "2.0",
                    ],
                }
            )
        )
        return plist_path

    def test_exact_planned_path_returned_first(self, la, make_plan, tmp_path: Path) -> None:
        """The exact planned path short-circuits — no parsing needed."""
        agents = tmp_path / "Library/LaunchAgents"
        planned = agents / "com.rag-mcp.watch.docs-1a2b3c4d.plist"
        planned.parent.mkdir(parents=True)
        planned.write_bytes(b"junk-but-exact-path")
        watched = tmp_path / "docs"
        watched.mkdir()
        plan = make_plan(watch_path=watched, plist_path=planned)
        assert la.find_existing_plist(plan) == planned

    def test_slug_candidate_matching_watch_path_returned(
        self, la, make_plan, tmp_path: Path
    ) -> None:
        """A different label watching the same folder is detected."""
        agents = tmp_path / "Library/LaunchAgents"
        watched = tmp_path / "docs"
        watched.mkdir()
        other = self._seed(agents / "com.rag-mcp.watch.docs-00000000.plist", watched.resolve())
        plan = make_plan(
            watch_path=watched.resolve(),
            plist_path=agents / "com.rag-mcp.watch.docs-1a2b3c4d.plist",
        )
        assert la.find_existing_plist(plan) == other

    def test_slug_prefix_of_unrelated_folder_not_matched(
        self, la, make_plan, tmp_path: Path
    ) -> None:
        """``docs`` must not match a ``docs-backup`` watcher (CodeRabbit)."""
        agents = tmp_path / "Library/LaunchAgents"
        watched = tmp_path / "docs"
        watched.mkdir()
        backup = tmp_path / "docs-backup"
        backup.mkdir()
        self._seed(agents / "com.rag-mcp.watch.docs-backup-00000000.plist", backup.resolve())
        plan = make_plan(
            watch_path=watched.resolve(),
            plist_path=agents / "com.rag-mcp.watch.docs-1a2b3c4d.plist",
        )
        assert la.find_existing_plist(plan) is None

    def test_unparseable_slug_candidate_skipped(self, la, make_plan, tmp_path: Path) -> None:
        """Corrupt candidate files are ignored, never block an install."""
        agents = tmp_path / "Library/LaunchAgents"
        agents.mkdir(parents=True)
        watched = tmp_path / "docs"
        watched.mkdir()
        (agents / "com.rag-mcp.watch.docs-00000000.plist").write_bytes(b"not-a-plist")
        plan = make_plan(
            watch_path=watched.resolve(),
            plist_path=agents / "com.rag-mcp.watch.docs-1a2b3c4d.plist",
        )
        assert la.find_existing_plist(plan) is None

    def test_xml_shaped_malformed_plist_skipped(self, la, make_plan, tmp_path: Path) -> None:
        """XML-declared but broken plists raise ExpatError and are skipped.

        ``ExpatError`` subclasses ``Exception``, not ``ValueError`` — an
        uncaught one would crash the installer instead of skipping the
        corrupt candidate (CodeRabbit).
        """
        agents = tmp_path / "Library/LaunchAgents"
        agents.mkdir(parents=True)
        watched = tmp_path / "docs"
        watched.mkdir()
        (agents / "com.rag-mcp.watch.docs-00000000.plist").write_bytes(
            b'<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict><key>Label</key>'
        )
        plan = make_plan(
            watch_path=watched.resolve(),
            plist_path=agents / "com.rag-mcp.watch.docs-1a2b3c4d.plist",
        )
        assert la.find_existing_plist(plan) is None

    def test_no_candidates_returns_none(self, la, make_plan, tmp_path: Path) -> None:
        """A clean LaunchAgents directory yields None."""
        agents = tmp_path / "Library/LaunchAgents"
        agents.mkdir(parents=True)
        watched = tmp_path / "docs"
        watched.mkdir()
        plan = make_plan(
            watch_path=watched.resolve(),
            plist_path=agents / "com.rag-mcp.watch.docs-1a2b3c4d.plist",
        )
        assert la.find_existing_plist(plan) is None


# ── launchctl wrapper (task 2.4/2.5) ────────────────────────────────


class TestRunLaunchctl:
    """Platform gate and pass-through behaviour of run_launchctl."""

    def test_raises_off_macos(self, la, monkeypatch: pytest.MonkeyPatch) -> None:
        """On non-darwin platforms InstallerError is raised."""
        monkeypatch.setattr(sys, "platform", "linux")
        with pytest.raises(la.InstallerError):
            la.run_launchctl(["launchctl", "bootstrap", "gui/0", "/x.plist"])

    def test_delegates_to_subprocess_on_darwin(self, la, monkeypatch: pytest.MonkeyPatch) -> None:
        """On darwin the command is passed to subprocess.run."""
        done = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        monkeypatch.setattr(sys, "platform", "darwin")
        with patch(
            "omrg.transports.cli._launchagent.subprocess.run",
            return_value=done,
        ) as mock_run:
            result = la.run_launchctl(["launchctl", "print"])
        mock_run.assert_called_once()
        assert result.returncode == 0
