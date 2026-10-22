"""Move an old OMRG install to the OMRS names (change ``rename-omrg-to-omrs``).

``build_plan`` reads the machine and returns the steps; it never calls the
keychain or launchd. ``apply_plan`` runs the steps in order and stops at the
first failure. Each step is safe to run again, so a rerun resumes.

Order: keychain, data folder, stored paths in ``workspace.db``, config
folders, login items. The keychain goes first because it is the step most
likely to fail (locked keychain, permission prompt) and nothing has moved
yet when it does. The login items go last so a new job never starts before
the folders it needs exist.

Nothing here prints or logs a secret value. The keychain and launchd sit
behind two small ports so tests inject fakes (ADR-024: ``keyring`` loads
inside functions only).
"""

from __future__ import annotations

import plistlib
import re
import sqlite3
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from ..config.legacy_install import config_roots

_OLD, _NEW = "omrg", "omrs"
_OLD_SERVICE, _NEW_SERVICE = "omrg", "omrs"
_OLD_LABEL, _NEW_LABEL = "com.omrg.", "com.omrs."
#: ``workspace.db`` columns that hold absolute paths into the data folder.
_PATH_COLUMNS = (("runs", "inputs_json"),)
_KEYCHAIN_REF = re.compile(r"keychain://([A-Za-z0-9_-]+)")
_SECRET_REF = re.compile(r"(file://[^\"'\s]*?)/omrg/secrets/")
_SEGMENT = re.compile(r"(?<=/)\.?omrg(?=/|$)")


class MigrationError(RuntimeError):
    """A step failed. The message never holds a secret value."""


class KeychainPort(Protocol):
    """Reads and writes keychain entries."""

    def read(self, service: str, user: str) -> str | None:
        """Return the entry, or ``None`` when absent."""

    def write(self, service: str, user: str, secret: str) -> None:
        """Save the entry."""


class LaunchdPort(Protocol):
    """Unloads and loads login items."""

    def bootout(self, label: str) -> None:
        """Unload *label*. A job that is not loaded is not an error."""

    def bootstrap(self, plist: Path) -> None:
        """Load the job described by *plist*."""


@dataclass(frozen=True)
class Context:
    """Everything a migration touches, passed in so tests can fake it."""

    home: Path
    env: Mapping[str, str]
    keychain: KeychainPort | None
    launchd: LaunchdPort | None
    executable: str | None = None


@dataclass(frozen=True)
class Step:
    """One action. ``run`` returns a short detail line."""

    kind: str
    description: str
    run: Callable[[], str]


@dataclass(frozen=True)
class StepResult:
    """Outcome of one step: ``done`` or ``failed``, with a detail line."""

    step: Step
    status: str
    detail: str


@dataclass
class Plan:
    """What a migration would do."""

    steps: list[Step] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    #: ``(old name, new name, where it was found)``.
    variables: list[tuple[str, str, str]] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """True when no step and no conflict is left."""
        return not self.steps and not self.conflicts


# ── Plan ──────────────────────────────────────────────────────────────


def _tilde(path: Path, home: Path) -> str:
    try:
        return "~/" + path.relative_to(home).as_posix()
    except ValueError:
        return str(path)


def build_plan(ctx: Context) -> Plan:
    """Read the machine and return the steps, conflicts and remaining variables."""
    plan = Plan()
    home = ctx.home
    old_data, new_data = home / f".{_OLD}", home / f".{_NEW}"
    old_cfgs = [r / _OLD for r in config_roots(ctx.env, home) if (r / _OLD).is_dir()]

    plan.steps.extend(_keychain_steps(ctx, old_cfgs))
    if old_data.exists():
        if new_data.exists():
            plan.conflicts.append(
                f"Both {_tilde(old_data, home)} and {_tilde(new_data, home)} exist."
            )
        else:
            plan.steps.append(
                Step(
                    "folder",
                    f"Rename {_tilde(old_data, home)} to {_tilde(new_data, home)}",
                    lambda: _rename(old_data, new_data),
                )
            )
    db_dir = new_data if new_data.exists() else old_data
    db_file = db_dir / "workspace" / "workspace.db"
    if _has_old_paths(db_file, old_data):
        plan.steps.append(
            Step(
                "workspace",
                "Rewrite stored paths in workspace.db (runs.inputs_json)",
                lambda: _rewrite_db_paths(
                    new_data / "workspace" / "workspace.db", old_data, new_data
                ),
            )
        )

    for old_cfg in old_cfgs:
        new_cfg = old_cfg.with_name(_NEW)
        if new_cfg.exists():
            plan.conflicts.append(
                f"Both {_tilde(old_cfg, home)} and {_tilde(new_cfg, home)} exist."
            )
            continue
        plan.steps.append(
            Step(
                "folder",
                f"Rename {_tilde(old_cfg, home)} to {_tilde(new_cfg, home)}, "
                f"{_OLD}.jsonc to {_NEW}.jsonc, and update secret references",
                lambda old=old_cfg, new=new_cfg: _move_config(old, new),
            )
        )

    plan.steps.extend(_launchd_steps(ctx, plan.conflicts))
    plan.variables = _variables(ctx, new_data if new_data.exists() else old_data)
    return plan


def _variables(ctx: Context, data_dir: Path) -> list[tuple[str, str, str]]:
    found: list[tuple[str, str, str]] = []
    for name in sorted(ctx.env):
        if name.startswith("OMRG_"):
            found.append((name, "OMRS_" + name[5:], "the environment"))
    env_file = data_dir / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            name = line.split("=", 1)[0].strip()
            if name.startswith("OMRG_") and "=" in line:
                found.append((name, "OMRS_" + name[5:], _tilde(env_file, ctx.home)))
    return found


def _keychain_steps(ctx: Context, old_cfgs: list[Path]) -> list[Step]:
    """Plan one copy per ``keychain://<provider>`` reference in an old config file.

    Only while the old config folder exists: once it has moved, the keychain
    step has run (or the user never used it), so a second run plans nothing.
    """
    if ctx.keychain is None:
        return []
    keychain = ctx.keychain
    text = "\n".join(
        (cfg / f"{_OLD}.jsonc").read_text(encoding="utf-8", errors="replace")
        for cfg in old_cfgs
        if (cfg / f"{_OLD}.jsonc").is_file()
    )
    return [
        Step(
            "keychain",
            f"Copy keychain entry '{provider}' from service {_OLD_SERVICE} to {_NEW_SERVICE}",
            lambda provider=provider: _copy_keychain(keychain, provider),
        )
        for provider in dict.fromkeys(_KEYCHAIN_REF.findall(text))
    ]


def _launchd_steps(ctx: Context, conflicts: list[str]) -> list[Step]:
    agents = ctx.home / "Library" / "LaunchAgents"
    if ctx.launchd is None or not agents.is_dir():
        return []
    steps: list[Step] = []
    launchd = ctx.launchd
    for old in sorted(agents.glob(f"{_OLD_LABEL}*.plist")):
        new = agents / (_NEW_LABEL + old.name[len(_OLD_LABEL) :])
        if new.exists():
            conflicts.append(f"Both {old.stem} and {new.stem} exist.")
            continue
        steps.append(
            Step(
                "launchd",
                f"Replace login item {old.stem} with {new.stem}",
                lambda old=old, new=new: _replace_login_item(old, new, launchd, ctx),
            )
        )
    return steps


# ── Steps ─────────────────────────────────────────────────────────────


def _rename(old: Path, new: Path) -> str:
    old.rename(new)
    return "renamed"


def _has_old_paths(db_file: Path, old_data: Path) -> bool:
    if not db_file.is_file():
        return False
    try:
        con = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True)
        try:
            for table, column in _PATH_COLUMNS:
                query = f'select 1 from "{table}" where "{column}" like ? limit 1'  # noqa: S608
                if con.execute(query, (f"%{old_data}/%",)).fetchone():
                    return True
        finally:
            con.close()
    except sqlite3.Error:
        return False
    return False


def _rewrite_db_paths(db_file: Path, old_data: Path, new_data: Path) -> str:
    con = sqlite3.connect(db_file)
    changed = 0
    try:
        for table, column in _PATH_COLUMNS:
            cursor = con.execute(
                f'update "{table}" set "{column}" = replace("{column}", ?, ?) '  # noqa: S608
                f'where "{column}" like ?',
                (f"{old_data}/", f"{new_data}/", f"%{old_data}/%"),
            )
            changed += cursor.rowcount
        con.commit()
    finally:
        con.close()
    return f"{changed} row(s) updated"


def _move_config(old: Path, new: Path) -> str:
    old.rename(new)
    for path in sorted(new.glob(f"{_OLD}.jsonc*")):
        path.rename(path.with_name(_NEW + path.name[len(_OLD) :]))
    settings = new / f"{_NEW}.jsonc"
    if settings.is_file():
        text = settings.read_text(encoding="utf-8")
        settings.write_text(_SECRET_REF.sub(r"\1/omrs/secrets/", text), encoding="utf-8")
    return "renamed"


def _copy_keychain(keychain: KeychainPort, provider: str) -> str:
    secret = keychain.read(_OLD_SERVICE, provider)
    if secret is None:
        return "no entry under the old service; skipped"
    if keychain.read(_NEW_SERVICE, provider) is not None:
        return "already present under the new service; skipped"
    keychain.write(_NEW_SERVICE, provider, secret)
    return "copied; the old entry stays in place"


def _rewrite(value: Any) -> Any:
    """Rewrite names inside a plist value. Dict keys of ``OMRG_*`` variables move too."""
    if isinstance(value, str):
        return _SEGMENT.sub(lambda m: m.group(0).replace(_OLD, _NEW), value).replace(
            _OLD_LABEL, _NEW_LABEL
        )
    if isinstance(value, list):
        return [_rewrite(item) for item in value]
    if isinstance(value, dict):
        return {
            ("OMRS_" + k[5:] if k.startswith("OMRG_") else k): _rewrite(v) for k, v in value.items()
        }
    return value


def _replace_login_item(old: Path, new: Path, launchd: LaunchdPort, ctx: Context) -> str:
    plist = _rewrite(plistlib.loads(old.read_bytes()))
    args = plist.get("ProgramArguments") or []
    if args and not Path(args[0]).exists():
        if ctx.executable and Path(ctx.executable).exists():
            args[0] = ctx.executable
        else:
            raise MigrationError(
                f"The 'omrs' command was not found at {args[0]}. Install omrs first. "
                f"{old.stem} stays in place."
            )
    log_dir = ctx.home / "Library" / "Logs" / _NEW
    log_dir.mkdir(parents=True, exist_ok=True)
    tmp = new.with_suffix(".plist.tmp")
    tmp.write_bytes(plistlib.dumps(plist))
    tmp.replace(new)
    launchd.bootout(old.stem)
    old.unlink()
    launchd.bootstrap(new)
    return f"{new.stem} loaded"


# ── Apply ─────────────────────────────────────────────────────────────


def apply_plan(plan: Plan) -> list[StepResult]:
    """Run the steps in order. Stop at the first failure.

    Returns:
        One result per step that ran. Nothing runs when the plan has conflicts.
    """
    if plan.conflicts:
        return []
    results: list[StepResult] = []
    for step in plan.steps:
        try:
            results.append(StepResult(step, "done", step.run()))
        except (MigrationError, OSError, sqlite3.Error, plistlib.InvalidFileException) as exc:
            results.append(StepResult(step, "failed", str(exc)))
            break
    return results


# ── Real ports ────────────────────────────────────────────────────────


class SystemKeychain:
    """The system keychain through ``keyring`` (imported inside the functions)."""

    def read(self, service: str, user: str) -> str | None:
        """Return the entry, or ``None``. A locked or missing keychain raises."""
        from . import keychain

        def call() -> str | None:
            import keyring

            if not keychain.is_usable_backend(keychain._current_backend()):  # noqa: SLF001
                raise MigrationError("No usable system keychain.")
            return keyring.get_password(service, user)

        try:
            return keychain._run_with_limit(call, keychain.DEFAULT_TIMEOUT)  # noqa: SLF001
        except keychain.KeychainUnavailableError as exc:
            raise MigrationError(str(exc)) from None

    def write(self, service: str, user: str, secret: str) -> None:
        """Save the entry."""
        from . import keychain

        def call() -> None:
            import keyring

            keyring.set_password(service, user, secret)

        try:
            keychain._run_with_limit(call, keychain.DEFAULT_TIMEOUT)  # noqa: SLF001
        except keychain.KeychainUnavailableError as exc:
            raise MigrationError(str(exc)) from None


class SystemLaunchd:
    """``launchctl`` in the user's GUI domain (macOS only)."""

    def __init__(self, uid: int) -> None:
        """Remember the user id."""
        self._uid = uid

    def bootout(self, label: str) -> None:
        """Unload *label*; the exit code is ignored (a job may not be loaded)."""
        subprocess.run(  # noqa: S603
            ["launchctl", "bootout", f"gui/{self._uid}/{label}"],  # noqa: S607
            capture_output=True,
            check=False,
        )

    def bootstrap(self, plist: Path) -> None:
        """Load *plist*."""
        done = subprocess.run(  # noqa: S603
            ["launchctl", "bootstrap", f"gui/{self._uid}", str(plist)],  # noqa: S607
            capture_output=True,
            text=True,
            check=False,
        )
        if done.returncode != 0:
            raise MigrationError(f"launchctl bootstrap failed: {done.stderr.strip()[:200]}")


def is_macos() -> bool:
    """True on macOS, where login items and the system keychain exist."""
    return sys.platform == "darwin"
