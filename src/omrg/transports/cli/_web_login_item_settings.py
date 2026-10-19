"""Settings text of the ``omrg web install`` plan (move-settings-to-config-file, 10.1).

The login item reads ``omrg.jsonc`` from the user config folder. It also
reads ``~/.omrg/.env`` when that file exists. This module only checks that
files exist. It never reads, copies or moves a ``.env`` file.
"""

from __future__ import annotations

import os
from pathlib import Path

from ...config.user_config import CONFIG_FILE, user_config_dir

_INDENT = " " * 16


def config_file() -> Path:
    """Return the path of ``omrg.jsonc`` in the user config folder."""
    return user_config_dir() / CONFIG_FILE


def _tilde(path: Path, home: Path) -> str:
    text = str(path)
    prefix = str(home) + os.sep
    return "~" + text[len(str(home)) :] if text.startswith(prefix) else text


def plan_rows(settings_file: Path, home: Path | None = None) -> list[str]:
    """Return the plan rows that name the settings file and the optional ``.env``."""
    home = home or Path.home()
    return [
        f"  Settings:     {_tilde(settings_file, home)}",
        f"{_INDENT}~/.omrg/.env is optional and overrides it.",
    ]


def plan_warnings(settings_file: Path, cwd: Path, home: Path | None = None) -> list[str]:
    """Return the warnings about the settings file and a ``.env`` in *cwd*."""
    home = home or Path.home()
    shown = _tilde(settings_file, home)
    messages: list[str] = []
    if not settings_file.is_file():
        messages.append(
            f"{shown} does not exist, so the login item starts with the code defaults. "
            "Run 'omrg config init' to write a starter file."
        )
    dotenv = cwd / ".env"
    if dotenv.is_file():
        messages.append(
            f"The login item does not read {dotenv}. Run 'omrg config init', then copy the "
            f"settings you need into {shown}."
        )
    return messages
