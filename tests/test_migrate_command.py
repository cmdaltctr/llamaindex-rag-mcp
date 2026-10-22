"""``omrs migrate`` (change ``rename-omrg-to-omrs``).

Spec: ``legacy-install-migration``, requirement "The migrate command moves an
old install". Every test runs in a temporary ``HOME`` with a fake keychain and
a fake launchd. The real ``~/.config/omrg`` and the real keychain are never
touched.
"""

from __future__ import annotations

import json
import plistlib
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from omrg.integrations import legacy_migration as lm
from omrg.transports.cli import app

runner = CliRunner()

SECRET_FILE_TEXT = "FILE-SECRET-VALUE"  # noqa: S105
KEYCHAIN_SECRET = "KEYCHAIN-SECRET-VALUE"  # noqa: S105
ENV = {"COLUMNS": "200"}


@pytest.fixture(autouse=True)
def _skip_legacy_install_check() -> None:
    """Override the conftest fixture: ``migrate`` must run with the check active."""


@dataclass
class FakeKeychain:
    entries: dict[tuple[str, str], str] = field(default_factory=dict)
    fail: bool = False

    def read(self, service: str, user: str) -> str | None:
        if self.fail:
            raise lm.MigrationError("keychain is locked")
        return self.entries.get((service, user))

    def write(self, service: str, user: str, secret: str) -> None:
        self.entries[(service, user)] = secret


@dataclass
class FakeLaunchd:
    calls: list[tuple[str, str]] = field(default_factory=list)

    def bootout(self, label: str) -> None:
        self.calls.append(("bootout", label))

    def bootstrap(self, plist: Path) -> None:
        self.calls.append(("bootstrap", plist.name))


@dataclass
class World:
    home: Path
    keychain: FakeKeychain
    launchd: FakeLaunchd
    env: dict[str, str]

    def context(self) -> lm.Context:
        return lm.Context(
            home=self.home,
            env=self.env,
            keychain=self.keychain,
            launchd=self.launchd,
            executable=str(self.home / "bin" / "omrs"),
        )


def _lance_rows(path: Path) -> list[tuple[str, float]]:
    import lancedb

    table = lancedb.connect(str(path)).open_table("docs")
    return sorted((r["text"], r["vector"][0]) for r in table.to_arrow().to_pylist())


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> World:
    """Build an old install under a temporary HOME."""
    import lancedb

    home = tmp_path
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    data = home / ".omrg"
    (data / "workspace").mkdir(parents=True)
    lancedb.connect(str(data / "lancedb")).create_table(
        "docs",
        data=[{"text": t, "vector": [float(i), 0.5]} for i, t in enumerate(["a", "b", "c"])],
    )
    con = sqlite3.connect(data / "workspace" / "workspace.db")
    con.execute("create table runs (id text, inputs_json text)")
    con.execute(
        "insert into runs values ('r1', ?)",
        (json.dumps({"path": f"{home}/.omrg/workspace/uploads/a.pdf"}),),
    )
    con.commit()
    con.close()
    (data / ".env").write_text("OMRG_TOKEN_FILE=/x\nTOP=1\n", encoding="utf-8")

    cfg = home / ".config" / "omrg"
    (cfg / "secrets").mkdir(parents=True)
    (cfg / "omrg.jsonc").write_text(
        '{\n  // keys\n  "deepseek": "file://~/.config/omrg/secrets/deepseek.key",\n'
        '  "openrouter": "keychain://openrouter"\n}\n',
        encoding="utf-8",
    )
    (cfg / "omrg.jsonc.2026-10-20.bak").write_text("{}", encoding="utf-8")
    (cfg / "secrets" / "deepseek.key").write_text(SECRET_FILE_TEXT, encoding="utf-8")

    (home / "bin").mkdir()
    (home / "bin" / "omrs").write_text("#!/bin/sh\n", encoding="utf-8")
    agents = home / "Library" / "LaunchAgents"
    agents.mkdir(parents=True)
    with (agents / "com.omrg.web.plist").open("wb") as fh:
        plistlib.dump(
            {
                "Label": "com.omrg.web",
                "ProgramArguments": [str(home / "bin" / "omrg"), "web", "--login-item"],
                "WorkingDirectory": f"{home}/.omrg",
                "StandardOutPath": f"{home}/Library/Logs/omrg/com.omrg.web.out.log",
                "EnvironmentVariables": {"OMRG_CONFIG_DIR": f"{home}/.config/omrg", "PATH": "/bin"},
            },
            fh,
        )
    return World(
        home=home,
        keychain=FakeKeychain({("omrg", "openrouter"): KEYCHAIN_SECRET}),
        launchd=FakeLaunchd(),
        env={},
    )


def _snapshot(home: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(home)): p.read_bytes() for p in sorted(home.rglob("*")) if p.is_file()
    }


def _invoke(world: World, *args: str, input: str | None = None):  # noqa: A002
    with patch("omrg.transports.cli.migrate._context", return_value=world.context()):
        return runner.invoke(app, ["migrate", *args], input=input, env=ENV)


def _text(result) -> str:
    return result.stdout + result.stderr


# ── Dry run ───────────────────────────────────────────────────────────


def test_dry_run_lists_every_step_and_changes_nothing(world: World) -> None:
    before = _snapshot(world.home)
    result = _invoke(world, "--dry-run")
    assert result.exit_code == 0, _text(result)
    assert _snapshot(world.home) == before
    assert world.launchd.calls == []
    assert world.keychain.entries == {("omrg", "openrouter"): KEYCHAIN_SECRET}
    out = _text(result)
    for expected in ("~/.omrg", "~/.config/omrg", "openrouter", "com.omrg.web", "workspace"):
        assert expected in out
    assert SECRET_FILE_TEXT not in out and KEYCHAIN_SECRET not in out


def test_dry_run_plan_does_not_read_the_keychain(world: World) -> None:
    world.keychain.fail = True  # any read would raise
    plan = lm.build_plan(world.context())
    assert plan.conflicts == []
    assert any(step.kind == "keychain" for step in plan.steps)


# ── Full migration ────────────────────────────────────────────────────


def test_full_migration(world: World) -> None:
    home = world.home
    rows_before = _lance_rows(home / ".omrg" / "lancedb")

    result = _invoke(world, "--yes")

    assert result.exit_code == 0, _text(result)
    assert not (home / ".omrg").exists() and (home / ".omrs").is_dir()
    assert not (home / ".config" / "omrg").exists()
    cfg = home / ".config" / "omrs"
    text = (cfg / "omrs.jsonc").read_text(encoding="utf-8")
    assert "file://~/.config/omrs/secrets/deepseek.key" in text
    assert "omrg" not in text
    assert (cfg / "secrets" / "deepseek.key").read_text(encoding="utf-8") == SECRET_FILE_TEXT
    assert (cfg / "omrs.jsonc.2026-10-20.bak").exists()
    assert world.keychain.entries[("omrs", "openrouter")] == KEYCHAIN_SECRET
    assert world.keychain.entries[("omrg", "openrouter")] == KEYCHAIN_SECRET  # old entry stays

    agents = home / "Library" / "LaunchAgents"
    assert not (agents / "com.omrg.web.plist").exists()
    plist = plistlib.loads((agents / "com.omrs.web.plist").read_bytes())
    assert plist["Label"] == "com.omrs.web"
    assert plist["ProgramArguments"][0] == str(home / "bin" / "omrs")
    assert plist["WorkingDirectory"] == f"{home}/.omrs"
    assert plist["StandardOutPath"].endswith("Logs/omrs/com.omrs.web.out.log")
    assert plist["EnvironmentVariables"] == {
        "OMRS_CONFIG_DIR": f"{home}/.config/omrs",
        "PATH": "/bin",
    }
    assert world.launchd.calls == [("bootout", "com.omrg.web"), ("bootstrap", "com.omrs.web.plist")]

    con = sqlite3.connect(home / ".omrs" / "workspace" / "workspace.db")
    (stored,) = con.execute("select inputs_json from runs").fetchone()
    con.close()
    assert json.loads(stored)["path"] == f"{home}/.omrs/workspace/uploads/a.pdf"

    assert _lance_rows(home / ".omrs" / "lancedb") == rows_before
    out = _text(result)
    assert SECRET_FILE_TEXT not in out and KEYCHAIN_SECRET not in out


def test_without_yes_the_command_asks_and_a_no_changes_nothing(world: World) -> None:
    before = _snapshot(world.home)
    result = _invoke(world, input="n\n")
    assert result.exit_code != 0
    assert _snapshot(world.home) == before
    assert world.launchd.calls == []


# ── Conflicts ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("existing", "named"),
    [
        (".omrs", ("~/.omrg", "~/.omrs")),
        (".config/omrs", ("~/.config/omrg", "~/.config/omrs")),
        ("Library/LaunchAgents/com.omrs.web.plist", ("com.omrg.web", "com.omrs.web")),
    ],
)
def test_existing_target_blocks_every_step(
    world: World, existing: str, named: tuple[str, str]
) -> None:
    target = world.home / existing
    if target.suffix:
        target.write_bytes(plistlib.dumps({"Label": "com.omrs.web"}))
    else:
        target.mkdir(parents=True)
    before = _snapshot(world.home)

    result = _invoke(world, "--yes")

    assert result.exit_code != 0
    assert all(name in _text(result) for name in named)
    assert _snapshot(world.home) == before
    assert world.launchd.calls == []
    assert ("omrs", "openrouter") not in world.keychain.entries


# ── Second run and resume ─────────────────────────────────────────────


def test_second_run_is_a_no_op(world: World) -> None:
    assert _invoke(world, "--yes").exit_code == 0
    before = _snapshot(world.home)
    calls = list(world.launchd.calls)

    result = _invoke(world, "--yes")

    assert result.exit_code == 0
    assert "Nothing left to migrate" in _text(result)
    assert _snapshot(world.home) == before
    assert world.launchd.calls == calls
    assert lm.build_plan(world.context()).is_empty


def test_a_keychain_failure_stops_before_anything_moves_and_a_rerun_resumes(
    world: World,
) -> None:
    world.keychain.fail = True
    result = _invoke(world, "--yes")
    assert result.exit_code != 0
    assert "keychain is locked" in _text(result)
    assert world.launchd.calls == []
    assert (world.home / ".omrg").exists()  # nothing moved
    assert (world.home / "Library" / "LaunchAgents" / "com.omrg.web.plist").exists()

    world.keychain.fail = False
    assert _invoke(world, "--yes").exit_code == 0
    assert world.keychain.entries[("omrs", "openrouter")] == KEYCHAIN_SECRET
    assert (world.home / "Library" / "LaunchAgents" / "com.omrs.web.plist").exists()


def test_a_missing_old_keychain_entry_is_skipped(world: World) -> None:
    world.keychain.entries.clear()
    result = _invoke(world, "--yes")
    assert result.exit_code == 0
    assert "no entry" in _text(result).lower()


def test_a_missing_executable_leaves_the_old_login_item_alone(world: World) -> None:
    (world.home / "bin" / "omrs").unlink()
    context = world.context()
    context = lm.Context(
        home=context.home,
        env=context.env,
        keychain=context.keychain,
        launchd=context.launchd,
        executable=None,
    )
    plan = lm.build_plan(context)
    results = lm.apply_plan(plan)
    assert any(r.status == "failed" for r in results)
    assert world.launchd.calls == []
    assert (world.home / "Library" / "LaunchAgents" / "com.omrg.web.plist").exists()


# ── Remaining variables ───────────────────────────────────────────────


def test_remaining_variables_are_reported_and_profiles_stay_untouched(world: World) -> None:
    world.env["OMRG_CONFIG_DIR"] = "/somewhere"
    profile = world.home / ".zshrc"
    profile.write_text("export OMRG_CONFIG_DIR=/somewhere\n", encoding="utf-8")

    result = _invoke(world, "--yes")

    out = _text(result)
    assert "OMRG_CONFIG_DIR" in out and "OMRS_CONFIG_DIR" in out
    assert "OMRG_TOKEN_FILE" in out and "OMRS_TOKEN_FILE" in out  # from ~/.omrs/.env
    assert profile.read_text(encoding="utf-8") == "export OMRG_CONFIG_DIR=/somewhere\n"


def test_migrate_runs_when_an_old_install_exists(world: World) -> None:
    """The startup check skips ``migrate`` (spec scenario 'not blocked')."""
    assert (world.home / ".omrg").exists()
    result = _invoke(world, "--dry-run")
    assert result.exit_code == 0, _text(result)
