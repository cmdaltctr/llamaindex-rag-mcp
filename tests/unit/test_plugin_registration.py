"""Plugin registration, change detection and probing (task 8.1)."""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from tests.unit.test_plugin_manifest import valid_manifest

from omrs.core.plugins import (
    ManifestError,
    PluginRegistry,
    PluginTrustError,
)
from omrs.integrations.workspace_sqlite import SqliteWorkspaceRepository

HELP = "--host --port --headless --token-password-file --skip-update-check --no-sandbox"


@dataclass
class Output:
    returncode: int
    stdout: str
    stderr: str = ""


@dataclass
class FakeRunner:
    """Records probe argv and answers from a table; never runs a process."""

    version: str = "fakeedit 1.4.2"
    help_text: str = HELP
    returncode: int = 0
    raises: Exception | None = None
    calls: list[tuple[str, ...]] = field(default_factory=list)

    def run(self, argv: Sequence[str], *, timeout: float) -> Output:
        self.calls.append(tuple(argv))
        if self.raises is not None:
            raise self.raises
        text = self.help_text if "--help" in argv else self.version
        return Output(self.returncode, text)


@pytest.fixture
def files(tmp_path: Path) -> tuple[Path, Path]:
    manifest = tmp_path / "plugin" / "manifest.json"
    manifest.parent.mkdir()
    manifest.write_text(json.dumps(valid_manifest()))
    exe = tmp_path / "bin" / "fakeedit"
    exe.parent.mkdir()
    exe.write_text("#!/bin/sh\necho 1\n")
    exe.chmod(0o755)
    return manifest, exe


@pytest.fixture
def repo(tmp_path: Path) -> SqliteWorkspaceRepository:
    return SqliteWorkspaceRepository(tmp_path / "ws" / "workspace.sqlite3")


def registry(repo: SqliteWorkspaceRepository, runner: FakeRunner) -> PluginRegistry:
    return PluginRegistry(repo, runner)


def test_registration_requires_explicit_trust(repo, files) -> None:
    runner = FakeRunner()
    with pytest.raises(PluginTrustError):
        registry(repo, runner).register(*files, approved=False)
    assert repo.list_plugins() == []
    assert runner.calls == []


def test_registration_stores_hash_and_executable_without_probing(repo, files) -> None:
    runner = FakeRunner()
    record = registry(repo, runner).register(*files, approved=True)
    assert record["name"] == "fakeedit"
    assert record["manifest_hash"] and len(record["manifest_hash"]) == 64
    assert record["executable_ref"] == str(files[1])
    assert record["compatibility_status"] == "unchecked"
    assert record["detail"]["executable"]["size"] == files[1].stat().st_size
    assert runner.calls == []  # registration launches nothing


def test_invalid_manifest_is_rejected_without_launch(repo, files) -> None:
    manifest, exe = files
    data = valid_manifest()
    data["recipes"]["launch_notebook"]["args"] = "edit {notebook_path}"
    manifest.write_text(json.dumps(data))
    runner = FakeRunner()
    with pytest.raises(ManifestError):
        registry(repo, runner).register(manifest, exe, approved=True)
    assert repo.list_plugins() == []
    assert runner.calls == []


@pytest.mark.parametrize("kind", ["relative", "missing", "not_executable", "directory"])
def test_bad_executable_is_rejected(repo, files, kind: str, tmp_path: Path) -> None:
    manifest, exe = files
    target = {
        "relative": Path("bin/fakeedit"),
        "missing": tmp_path / "nope",
        "not_executable": exe,
        "directory": tmp_path,
    }[kind]
    if kind == "not_executable":
        exe.chmod(0o644)
    with pytest.raises(PluginTrustError):
        registry(repo, FakeRunner()).register(manifest, target, approved=True)


def test_recheck_records_compatible_version(repo, files) -> None:
    runner = FakeRunner()
    reg = registry(repo, runner)
    reg.register(*files, approved=True)
    state = reg.recheck("fakeedit")
    assert state.status == "compatible" and state.launchable
    assert state.version == "1.4.2"
    assert runner.calls == [(str(files[1]), "--version"), (str(files[1]), "edit", "--help")]
    assert repo.get_plugin("fakeedit")["compatibility_status"] == "compatible"
    assert reg.state("fakeedit").launchable  # state() reads without probing
    assert len(runner.calls) == 2


def test_incompatible_version_is_disabled_with_action(repo, files) -> None:
    reg = registry(repo, FakeRunner(version="fakeedit 2.1.0"))
    reg.register(*files, approved=True)
    state = reg.recheck("fakeedit")
    assert state.status == "incompatible" and not state.launchable
    assert "2.1.0" in state.message and ">=1.2.0,<2.0.0" in state.message
    assert "outside OMRS" in state.message


@pytest.mark.parametrize(
    ("runner", "fragment"),
    [
        (FakeRunner(version="no version here"), "could not read a version"),
        (FakeRunner(returncode=3), "exited with code 3"),
        (FakeRunner(raises=TimeoutError("slow")), "probe failed"),
        (FakeRunner(raises=OSError("exec format error")), "probe failed"),
    ],
)
def test_probe_failures_are_incompatible(repo, files, runner: FakeRunner, fragment: str) -> None:
    reg = registry(repo, runner)
    reg.register(*files, approved=True)
    state = reg.recheck("fakeedit")
    assert state.status == "incompatible" and fragment in state.message


def test_missing_help_flag_names_the_capability(repo, files) -> None:
    reg = registry(repo, FakeRunner(help_text=HELP.replace("--token-password-file", "")))
    reg.register(*files, approved=True)
    state = reg.recheck("fakeedit")
    assert state.status == "incompatible"
    assert "token_auth" in state.message and "--token-password-file" in state.message


def test_undeclared_required_capability_blocks_launch(repo, files) -> None:
    manifest, exe = files
    data = valid_manifest()
    del data["capabilities"]["startup_execution_disabled"]
    manifest.write_text(json.dumps(data))
    reg = registry(repo, FakeRunner())
    reg.register(manifest, exe, approved=True)
    state = reg.recheck("fakeedit")
    assert state.status == "incompatible"
    assert "startup_execution_disabled" in state.message


def test_changed_manifest_requires_new_approval(repo, files) -> None:
    manifest, exe = files
    runner = FakeRunner()
    reg = registry(repo, runner)
    reg.register(manifest, exe, approved=True)
    reg.recheck("fakeedit")
    data = valid_manifest()
    data["description"] = "edited after approval"
    manifest.write_text(json.dumps(data))
    calls = len(runner.calls)
    state = reg.recheck("fakeedit")
    assert state.status == "needs_approval" and not state.launchable
    assert "register" in state.message
    assert len(runner.calls) == calls  # no probe of an unapproved manifest
    reg.register(manifest, exe, approved=True)
    assert reg.recheck("fakeedit").status == "compatible"


def test_deleted_manifest_requires_new_approval(repo, files) -> None:
    reg = registry(repo, FakeRunner())
    reg.register(*files, approved=True)
    files[0].unlink()
    assert reg.state("fakeedit").status == "needs_approval"


def test_changed_executable_invalidates_until_recheck(repo, files) -> None:
    manifest, exe = files
    runner = FakeRunner()
    reg = registry(repo, runner)
    reg.register(manifest, exe, approved=True)
    assert reg.recheck("fakeedit").launchable
    exe.write_text("#!/bin/sh\necho 'upgraded build'\n")
    os.utime(exe, ns=(1, 1))
    state = reg.state("fakeedit")
    assert state.status == "unchecked" and not state.launchable
    assert "changed" in state.message and "recheck" in state.message
    runner.version = "fakeedit 1.5.0"
    rechecked = reg.recheck("fakeedit")
    assert rechecked.launchable and rechecked.version == "1.5.0"
    assert reg.state("fakeedit").launchable


def test_missing_executable_never_installs(repo, files) -> None:
    runner = FakeRunner()
    reg = registry(repo, runner)
    reg.register(*files, approved=True)
    files[1].unlink()
    state = reg.recheck("fakeedit")
    assert state.status == "unavailable" and not state.launchable
    assert "outside OMRS" in state.message
    assert runner.calls == []  # nothing is run, so nothing can install


def test_probe_argv_never_contains_install_actions(repo, files) -> None:
    runner = FakeRunner(version="fakeedit 0.1.0")  # too old
    reg = registry(repo, runner)
    reg.register(*files, approved=True)
    reg.recheck("fakeedit")
    flat = [arg for call in runner.calls for arg in call]
    for word in ("install", "upgrade", "uv", "uvx", "pip", "pipx"):
        assert word not in flat


def test_unknown_plugin_raises_key_error(repo) -> None:
    with pytest.raises(KeyError):
        registry(repo, FakeRunner()).state("nothing")


def test_list_states_reports_every_registration(repo, files) -> None:
    reg = registry(repo, FakeRunner())
    reg.register(*files, approved=True)
    assert [s.name for s in reg.list_states()] == ["fakeedit"]


def test_world_writable_executable_is_rejected(repo, files) -> None:
    manifest, exe = files
    exe.chmod(0o777)
    with pytest.raises(PluginTrustError, match="writable by other users"):
        registry(repo, FakeRunner()).register(manifest, exe, approved=True)


class HelpFails(FakeRunner):
    def run(self, argv: Sequence[str], *, timeout: float) -> Output:
        if "--help" in argv:
            self.calls.append(tuple(argv))
            return Output(2, "", "no such option")
        return super().run(argv, timeout=timeout)


def test_help_probe_failure_is_incompatible(repo, files) -> None:
    reg = registry(repo, HelpFails())
    reg.register(*files, approved=True)
    state = reg.recheck("fakeedit")
    assert state.status == "incompatible" and "exited with code 2" in state.message


def test_manifest_without_help_probe_skips_flag_check(repo, files) -> None:
    manifest, exe = files
    data = valid_manifest()
    del data["recipes"]["probe"]["help_args"]
    manifest.write_text(json.dumps(data))
    runner = FakeRunner(help_text="")
    reg = registry(repo, runner)
    reg.register(manifest, exe, approved=True)
    assert reg.recheck("fakeedit").launchable
    assert runner.calls == [(str(exe), "--version")]
