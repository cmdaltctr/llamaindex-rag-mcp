"""``omrg config`` command group.

``init`` writes a commented starter ``omrg.jsonc`` in the user config
folder. All output goes to stderr (gotcha #5).
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Annotated, NoReturn

import typer
from rich.markup import escape

from ...config.user_config import CONFIG_FILE, display_path, user_config_dir
from . import app, console
from .config_template import build_template, today

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
    stem = f"{target.name}.{today()}"
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
