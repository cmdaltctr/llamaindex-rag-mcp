"""How this server was installed, and what it may install into itself (design D2, D4).

The server reports one of three install types:

* ``uv-tool``: ``uv-receipt.toml`` sits in the server's own Python
  environment folder (``sys.prefix``). The receipt gives the extras and the
  source of the lasting copy command.
* ``checkout``: the ``omrs`` package file sits under a folder that holds
  both ``pyproject.toml`` and ``uv.lock``.
* ``other``: every other case (pip, a container, a wheel).

Only a ``uv-tool`` install with a ``uv`` program found may install an extra
from the app. The extra's requirements come from the installed package
metadata, never from request text. This module only reads files; it starts
no process. Standard library only, so no optional extra is needed.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import sys
import tomllib
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

InstallType = Literal["uv-tool", "checkout", "other"]

UV_TOOL: InstallType = "uv-tool"
CHECKOUT: InstallType = "checkout"
OTHER: InstallType = "other"

#: Extras the app never installs: ``web`` runs the page already, and
#: ``torch`` is several GB and opt-in only (ADR-073).
EXCLUDED_EXTRAS: frozenset[str] = frozenset({"web", "torch"})

#: Availability values that mean the extra needs no install.
INSTALLED_STATES: frozenset[str] = frozenset({"available", "restart-needed"})

RECEIPT_NAME = "uv-receipt.toml"

Which = Callable[[str], str | None]

_EXTRA_CLAUSE = re.compile(r"""\(?\s*extra\s*==\s*(['"])(?P<name>[^'"]+)\1\s*\)?""")
_AND = re.compile(r"\s+and\s+")


@dataclass(frozen=True)
class InstallEnvironment:
    """What the server knows about its own install.

    Attributes:
        install_type: ``uv-tool``, ``checkout`` or ``other``.
        receipt_extras: Extras the ``uv tool`` receipt lists for ``omrs``.
        receipt_source: The receipt source with the home folder as ``~``,
            or ``None`` (an index install or an unreadable receipt).
        receipt_editable: Whether the receipt records an editable install.
        uv: Path of the ``uv`` program, or ``None`` when not found.
    """

    install_type: InstallType
    receipt_extras: tuple[str, ...] = ()
    receipt_source: str | None = None
    receipt_editable: bool = False
    uv: str | None = None


def _tilde(path: str, home: Path) -> str:
    """Write *path* with the home folder as ``~``."""
    home_text = str(home).rstrip(os.sep)
    if path == home_text:
        return "~"
    if path.startswith(home_text + os.sep):
        return "~" + path[len(home_text) :]
    return path


def _receipt_requirement(receipt: Path) -> dict[str, object]:
    """Return the receipt's ``omrs`` requirement table, or an empty mapping."""
    try:
        data = tomllib.loads(receipt.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        logger.warning("Could not read the uv tool receipt %s.", receipt)
        return {}
    requirements = data.get("tool", {}).get("requirements", [])
    for item in requirements if isinstance(requirements, list) else []:
        if isinstance(item, dict) and item.get("name") == "omrs":
            return item
    return {}


def _receipt_source(requirement: dict[str, object], home: Path) -> str | None:
    """Return the requirement's source in copy form, or ``None``."""
    for key in ("directory", "editable", "path"):
        value = requirement.get(key)
        if isinstance(value, str):
            return _tilde(value, home)
    git = requirement.get("git")
    if isinstance(git, str):
        return f"git+{git}"
    url = requirement.get("url")
    return url if isinstance(url, str) else None


def _is_checkout(package_file: Path) -> bool:
    """Return whether a parent folder of *package_file* holds a uv project."""
    for folder in package_file.resolve().parents:
        if (folder / "pyproject.toml").is_file() and (folder / "uv.lock").is_file():
            return True
    return False


def find_uv(*, home: Path | None = None, which: Which = shutil.which) -> str | None:
    """Return the ``uv`` program path, or ``None``.

    The login item has a short ``PATH``, so the usual install folders
    ``~/.local/bin`` and ``~/.cargo/bin`` are checked after ``PATH``.

    Args:
        home: The home folder. Defaults to ``Path.home()``.
        which: ``shutil.which`` or a test double.
    """
    found = which("uv")
    if found:
        return found
    home = Path.home() if home is None else home
    for candidate in (home / ".local" / "bin" / "uv", home / ".cargo" / "bin" / "uv"):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def detect_environment(
    *,
    prefix: Path | str | None = None,
    package_file: Path | str | None = None,
    home: Path | None = None,
    which: Which = shutil.which,
) -> InstallEnvironment:
    """Return the install type of this server and the ``uv`` program.

    Args:
        prefix: The Python environment folder. Defaults to ``sys.prefix``.
        package_file: The ``omrs`` package file. Defaults to the real one.
        home: The home folder. Defaults to ``Path.home()``.
        which: ``shutil.which`` or a test double.
    """
    if package_file is None:
        import omrs

        package_file = omrs.__file__ or ""
    home = Path.home() if home is None else home
    uv = find_uv(home=home, which=which)
    receipt = Path(sys.prefix if prefix is None else prefix, RECEIPT_NAME)
    if receipt.is_file():
        requirement = _receipt_requirement(receipt)
        extras = requirement.get("extras", [])
        return InstallEnvironment(
            install_type=UV_TOOL,
            receipt_extras=tuple(str(item) for item in extras) if isinstance(extras, list) else (),
            receipt_source=_receipt_source(requirement, home),
            receipt_editable=isinstance(requirement.get("editable"), str),
            uv=uv,
        )
    kind = CHECKOUT if _is_checkout(Path(package_file)) else OTHER
    return InstallEnvironment(install_type=kind, uv=uv)


def copy_command(environment: InstallEnvironment, extra: str) -> str:
    """Return the copy-ready install command for *extra* (design D4).

    Args:
        environment: The detected install.
        extra: The extra to add.
    """
    if environment.install_type == CHECKOUT:
        return f"uv sync --extra {extra}"
    if environment.install_type == OTHER:
        return f'pip install "omrs[{extra}]"'
    extras = list(environment.receipt_extras)
    if extra not in extras:
        extras.append(extra)
    requirement = f"omrs[{','.join(extras)}]"
    if environment.receipt_source:
        requirement += f" @ {environment.receipt_source}"
    flags = "--reinstall --editable" if environment.receipt_editable else "--reinstall"
    return f'uv tool install {flags} "{requirement}"'


def install_reason(
    extra: str | None,
    availability: str,
    packages: list[str],
    environment: InstallEnvironment,
) -> str | None:
    """Return why *extra* cannot be installed from the app, or ``None``.

    The checks run in a fixed order: the allowed list, the current
    availability (``unknown`` refuses, because the server does not know
    what is there), the requirements, the install type, the ``uv`` program.

    Args:
        extra: The entry's extra, or ``None`` for an always-on integration.
        availability: The entry's availability in this launch.
        packages: The extra's requirements.
        environment: The detected install.
    """
    if extra is None or extra in EXCLUDED_EXTRAS:
        return "not-installable-here"
    if availability == "unknown":
        return "status-unknown"
    if availability in INSTALLED_STATES:
        return "already-installed"
    if not packages:
        return "no-requirements"
    if environment.install_type != UV_TOOL:
        return "not-uv-tool"
    if environment.uv is None:
        return "uv-not-found"
    return None


def _without_extra(marker: str, extra: str) -> str | None:
    """Return *marker* without its ``extra == <extra>`` clause.

    Returns ``None`` when the marker does not name *extra* as one of its
    ``and`` parts. A marker with ``or`` around the extra is not simplified.
    """
    parts = _AND.split(marker)
    kept = []
    found = False
    for part in parts:
        match = _EXTRA_CLAUSE.fullmatch(part.strip())
        if match is None:
            kept.append(part.strip())
        elif match["name"] == extra:
            found = True
        else:
            return None
    return " and ".join(kept) if found else None


def extra_requirements(extra: str, requires: Iterable[str] | None = None) -> list[str]:
    """Return the requirements the installed ``omrs`` declares for *extra*.

    The ``extra ==`` marker is removed; any other marker part is kept.

    Args:
        extra: The extra name.
        requires: Requirement lines. Defaults to the installed metadata.

    Returns:
        The requirement lines, or an empty list for an unknown extra.
    """
    if requires is None:
        try:
            requires = metadata.distribution("omrs").requires or []
        except metadata.PackageNotFoundError:
            return []
    found = []
    for line in requires:
        spec, _, marker = line.partition(";")
        rest = _without_extra(marker.strip(), extra) if marker.strip() else None
        if rest is None:
            continue
        found.append(f"{spec.strip()}; {rest}" if rest else spec.strip())
    return found
