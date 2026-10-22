"""Detection of an old OMRG install (change ``rename-omrg-to-omrs``).

The project was named OMRG until ADR-092. Settings, data folders and login
items written under that name are no longer read. This check finds them at
startup and stops, naming the replacement and the ``omrs migrate`` command.

The check only reads: environment variables, folder existence and the file
names in ``~/Library/LaunchAgents``. It never opens a file, never calls the
keychain (design D2a: a keychain read can show a system prompt on every start,
and ``omrs migrate`` leaves the old entry in place) and never uses an old
value as a fallback.

Retirement follows the shape-aware rule in :mod:`.legacy`: flat ``OMRG_*``
names cannot be detected by settings validation, so they stay here while an
upgrade path exists.

This module is a leaf: it imports no OMRS code.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

#: Command that moves an old install.
MIGRATE_COMMAND = "omrs migrate"

_OLD_VARIABLE_PREFIX = "OMRG_"
_NEW_VARIABLE_PREFIX = "OMRS_"
_OLD_LABEL_PREFIX = "com.omrg."
_NEW_LABEL_PREFIX = "com.omrs."


class LegacyInstallError(RuntimeError):
    """An old OMRG install was found. The message names every sign and its replacement."""


@dataclass(frozen=True)
class LegacySign:
    """One sign of an old install.

    Attributes:
        kind: ``"variable"``, ``"data folder"``, ``"config folder"`` or ``"login item"``.
        found: The old name as the user sees it.
        replacement: The ``omrs`` name that replaces it.
    """

    kind: str
    found: str
    replacement: str


def _display(path: Path, home: Path) -> str:
    """Return *path* with the home folder written as ``~``."""
    try:
        return "~/" + path.relative_to(home).as_posix()
    except ValueError:
        return str(path)


def config_roots(env: Mapping[str, str], home: Path) -> list[Path]:
    """Return the parents that can hold an old ``omrg`` config folder."""
    roots = [home / ".config"]
    xdg = env.get("XDG_CONFIG_HOME", "").strip()
    if xdg:
        roots.append(Path(xdg).expanduser())
    return roots


def find_legacy_signs(
    env: Mapping[str, str] | None = None, home: Path | None = None
) -> list[LegacySign]:
    """Return every sign of an old OMRG install, in a stable order.

    Args:
        env: Environment to scan (default ``os.environ``).
        home: Home folder (default ``Path.home()``).

    Returns:
        The signs found. An empty list means a clean install.
    """
    source = os.environ if env is None else env
    base = Path.home() if home is None else home
    signs: list[LegacySign] = []

    for name in sorted(source):
        if name.startswith(_OLD_VARIABLE_PREFIX):
            signs.append(
                LegacySign(
                    "variable", name, _NEW_VARIABLE_PREFIX + name[len(_OLD_VARIABLE_PREFIX) :]
                )
            )

    data = base / ".omrg"
    if data.exists():
        signs.append(
            LegacySign("data folder", _display(data, base), _display(base / ".omrs", base))
        )

    seen: set[Path] = set()
    for root in config_roots(source, base):
        old = root / "omrg"
        if old in seen or not old.exists():
            continue
        seen.add(old)
        signs.append(
            LegacySign("config folder", _display(old, base), _display(root / "omrs", base))
        )

    agents = base / "Library" / "LaunchAgents"
    if agents.is_dir():
        for plist in sorted(agents.glob(f"{_OLD_LABEL_PREFIX}*.plist")):
            label = plist.stem
            signs.append(
                LegacySign("login item", label, _NEW_LABEL_PREFIX + label[len(_OLD_LABEL_PREFIX) :])
            )
    return signs


def refusal_message(signs: list[LegacySign]) -> str:
    """Return the text that names each sign, its replacement and the migrate command."""
    lines = [
        "An old OMRG install was found. The project is now named OMRS "
        "and no longer reads the old names:"
    ]
    lines.extend(f"  {sign.kind}: {sign.found}  ->  {sign.replacement}" for sign in signs)
    lines.append(f"Run '{MIGRATE_COMMAND} --dry-run' to see the plan, then '{MIGRATE_COMMAND}'.")
    return "\n".join(lines)


def ensure_no_legacy_install(
    env: Mapping[str, str] | None = None, home: Path | None = None
) -> None:
    """Raise when an old OMRG install is present.

    Args:
        env: Environment to scan (default ``os.environ``).
        home: Home folder (default ``Path.home()``).

    Raises:
        LegacyInstallError: Naming every sign, its replacement and the migrate command.
    """
    signs = find_legacy_signs(env, home)
    if signs:
        raise LegacyInstallError(refusal_message(signs))


def exit_if_legacy_install() -> None:
    """Write the refusal to stderr and exit with status 1 when an old install exists.

    stdout is the MCP protocol channel (gotcha 5), so nothing goes there.
    """
    try:
        ensure_no_legacy_install()
    except LegacyInstallError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from None
