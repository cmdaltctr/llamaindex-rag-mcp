"""``omrg config`` command group.

``init`` writes a commented starter ``omrg.jsonc`` in the user config
folder. ``show`` prints every setting with its value and source. All output
goes to stderr (gotcha #5).
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Annotated, NoReturn

import typer
from rich.markup import escape

from ...config.settings_file import SettingsFile, read_settings_file
from ...config.user_config import CONFIG_FILE, display_path, user_config_dir
from ..settings_view import SettingView, describe_settings
from . import app, config_template, console
from .config_template import build_template

config_app = typer.Typer(
    name="config",
    help="Write or inspect omrg.jsonc, the file that holds every omrg setting.",
    no_args_is_help=True,
)
app.add_typer(config_app, name="config")


@config_app.callback()
def config() -> None:
    """Write or inspect omrg.jsonc, the file that holds every omrg setting."""


def _fail(message: str) -> NoReturn:
    console.print(f"[red]Error:[/red] {escape(message)}", soft_wrap=True)
    raise typer.Exit(code=1)


def _backup_path(target: Path) -> Path:
    """Return a free ``omrg.jsonc.<date>.bak`` name beside *target*."""
    # Look ``today`` up on its module so a test can fix the date there.
    stem = f"{target.name}.{config_template.today()}"
    candidate = target.with_name(f"{stem}.bak")
    number = 2
    while candidate.exists():
        candidate = target.with_name(f"{stem}.{number}.bak")
        number += 1
    return candidate


def _write_private(target: Path, text: str, *, replace: bool) -> None:
    """Write *text* to *target* with mode 0600.

    A new file is created with ``O_EXCL``. A replacement goes to a temporary
    file first, so the target holds the old or the new text, never a mix.
    """
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if not replace:
        descriptor = os.open(target, flags, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
        return
    temporary = target.with_name(target.name + ".tmp")
    temporary.unlink(missing_ok=True)
    descriptor = os.open(temporary, flags, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, target)


@config_app.command()
def init(
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help="Replace an existing omrg.jsonc. The old file is kept as omrg.jsonc.<date>.bak.",
        ),
    ] = False,
) -> None:
    """Write a starter omrg.jsonc with every setting commented out.

    The file lives in $OMRG_CONFIG_DIR, else $XDG_CONFIG_HOME/omrg, else
    ~/.config/omrg. It sets nothing until you remove a comment mark.
    """
    folder = user_config_dir()
    target = folder / CONFIG_FILE
    shown = escape(display_path(target))
    exists = target.exists() or target.is_symlink()
    if exists and not force:
        _fail(f"{display_path(target)} already exists. Pass --force to replace it.")
    try:
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        backup = None
        if exists:
            backup = _backup_path(target)
            shutil.copy2(target, backup)
        _write_private(target, build_template(), replace=exists)
    except OSError as exc:
        _fail(f"Could not write {display_path(target)}: {exc.strerror or exc}")
    if backup is not None:
        console.print(f"Old file kept as {escape(display_path(backup))}.", soft_wrap=True)
    console.print(
        f"[green]✓[/green] Wrote {shown}. Every setting is commented out.", soft_wrap=True
    )


_KEYCHAIN_NOTES = {
    "keychain-missing": "The keychain has no key for {provider}.",
    "keychain-unreadable": "The keychain could not be read, so the key for {provider} is not set.",
}


def _value_text(view: SettingView) -> str:
    """Return the value column: JSON for a value, a masked phrase for a key field."""
    if view.last4 is not None:
        return f"set, ending {view.last4}" if view.last4 else "set"
    if view.value is None:
        return "not set"
    return json.dumps(view.value, ensure_ascii=False)


_FILE_STATES = {"absent": "not found", "ok": "found", "broken": "cannot be read"}


def _file_line(file: SettingsFile) -> str:
    return f"File: {display_path(file.path)} ({_FILE_STATES.get(file.state, file.state)})"


@config_app.command()
def show() -> None:
    """Print every setting with its value and where the value came from.

    A key shows only whether it is set and its last four characters. Problems
    found in omrg.jsonc are listed by key. The command writes nothing and
    prints to stderr only.
    """
    from ...compose_providers import resolve_keychain_references
    from ...config import Settings

    settings, key_problems = resolve_keychain_references(Settings())
    file = read_settings_file()
    views = describe_settings(
        launch=settings, live=settings, file=file, snapshot=file.values, pending=()
    )
    console.print(escape(_file_line(file)), soft_wrap=True)
    groups: dict[str, list[SettingView]] = {}
    for view in views:
        block = view.key.partition(".")[0] if "." in view.key else "general"
        groups.setdefault(block, []).append(view)
    for block, members in groups.items():
        console.print(f"\n{escape(block)}:", soft_wrap=True)
        for view in members:
            line = f"  {view.key} = {_value_text(view)}  ({view.source})"
            console.print(escape(line), soft_wrap=True)
    notes = [
        _KEYCHAIN_NOTES[reason].format(provider=provider)
        for provider, reason in sorted(key_problems.items())
        if reason in _KEYCHAIN_NOTES
    ]
    if file.problems or notes:
        console.print(f"\nProblems in {escape(display_path(file.path))}:", soft_wrap=True)
        for problem in file.problems:
            console.print(escape(f"  {problem.key}: {problem.message}"), soft_wrap=True)
        for note in notes:
            console.print(escape(f"  {note}"), soft_wrap=True)
