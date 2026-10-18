"""Read-only user config folder: ``omrg.jsonc`` and ``secrets/<provider>.key``.

The folder is ``$OMRG_CONFIG_DIR``, else ``$XDG_CONFIG_HOME/omrg``, else
``~/.config/omrg``. OMRG only reads it. It never creates, writes or changes
the mode of anything there.

``omrg.jsonc`` is JSON with comments and trailing commas. It may set the
non-secret provider fields, and it may point at a key with ``env://NAME`` or
``file://<absolute path inside secrets/>``. A literal key in the file is
ignored. ``secrets/<provider>.key`` holds one key per provider.

This module is a leaf: it imports no OMRG code. Messages name a field or a
path, never a value.
"""

from __future__ import annotations

import json
import logging
import os
import re
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CONFIG_FILE = "omrg.jsonc"
SECRETS_DIR = "secrets"
#: A key file is read up to this size; a larger file is refused.
MAX_KEY_BYTES = 4096
_NAME = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

#: ``omrg.jsonc`` keys that hold an address, as ``Settings`` field paths.
_ADDRESS_KEYS = ("ollama_base_url", "llamacpp_chat_url", "openai_compatible_base_url")
#: ``omrg.jsonc`` keys that hold a key reference. The provider name is the
#: key minus ``_api_key``; it names the file ``secrets/<provider>.key``.
_SECRET_KEYS = ("openrouter_api_key", "openai_compatible_api_key", "anthropic_api_key")

_warned: set[tuple[str, str]] = set()


@dataclass(frozen=True)
class UserConfig:
    """What the user config folder holds.

    ``repr`` shows field names only, because a value can be an API key.

    Attributes:
        directory: The resolved folder (it may not exist).
        values: ``omrg.jsonc`` values by ``Settings`` field path, with each
            resolved key reference.
        key_file: Key-file keys by ``Settings`` field name.
    """

    directory: Path
    values: dict[str, str] = field(default_factory=dict)
    key_file: dict[str, str] = field(default_factory=dict)

    def __repr__(self) -> str:
        names = sorted({*self.values, *self.key_file})
        return f"UserConfig(directory={self.directory}, fields={names})"


def user_config_dir() -> Path:
    """Return the user config folder, which may not exist."""
    explicit = os.environ.get("OMRG_CONFIG_DIR", "").strip()
    if explicit:
        return Path(explicit).expanduser()
    xdg = os.environ.get("XDG_CONFIG_HOME", "").strip()
    return (Path(xdg).expanduser() if xdg else Path.home() / ".config") / "omrg"


def display_path(path: Path | str) -> str:
    """Return *path* with the home folder written as ``~``."""
    text = str(path)
    home = str(Path.home())
    if text == home:
        return "~"
    return "~" + text[len(home) :] if text.startswith(home + os.sep) else text


def config_file_reason(directory: Path | str) -> str:
    """Return the lock text for a field that ``omrg.jsonc`` sets."""
    return (
        f"Set in {display_path(directory)}/{CONFIG_FILE}. Edit that file and restart to change it."
    )


def _warn_once(kind: str, subject: str, message: str, *args: object) -> None:
    """Log *message* once per (kind, subject) for the life of the process."""
    if (kind, subject) in _warned:
        return
    _warned.add((kind, subject))
    logger.warning(message, *args)


def parse_jsonc(text: str) -> Any:
    """Parse JSON that may hold ``//`` and ``/* */`` comments and trailing commas.

    Raises:
        ValueError: The text is not valid once comments and trailing commas go.
    """
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == '"':
            j = i + 1
            while j < n and text[j] != '"':
                j += 2 if text[j] == "\\" else 1
            out.append(text[i : j + 1])
            i = j + 1
        elif text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 1
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = n if end < 0 else end + 2
            out.append(" ")
        else:
            out.append(ch)
            i += 1
    return json.loads(_join_outside_strings(out))


def _join_outside_strings(parts: list[str]) -> str:
    """Join scanner parts; a trailing comma inside a string is not touched.

    The scanner keeps each string literal as one part, so the comma rule runs
    on the pieces outside strings only.
    """
    pieces: list[str] = []
    buffer: list[str] = []
    for part in parts:
        if part.startswith('"') and len(part) > 1:
            pieces.append(re.sub(r",(\s*[}\]])", r"\1", "".join(buffer)))
            buffer = []
            pieces.append(part)
        else:
            buffer.append(part)
    pieces.append(re.sub(r",(\s*[}\]])", r"\1", "".join(buffer)))
    return "".join(pieces)


def _load_json(path: Path) -> dict[str, Any] | None:
    """Return the parsed ``omrg.jsonc`` object, or ``None`` when it is absent or broken."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError):
        _warn_once("broken", str(path), "Ignoring %s: it cannot be read.", path)
        return None
    try:
        data = parse_jsonc(text)
    except ValueError:
        _warn_once("broken", str(path), "Ignoring %s: it is not valid JSON.", path)
        return None
    if not isinstance(data, dict):
        _warn_once("broken", str(path), "Ignoring %s: the top level must be an object.", path)
        return None
    return data


def _typed(data: dict[str, Any]) -> bool:
    """Return whether every known key in *data* has the right type."""
    for key in (*_ADDRESS_KEYS, *_SECRET_KEYS):
        if key in data and not isinstance(data[key], str):
            return False
    answer = data.get("answer")
    if answer is None:
        return True
    return isinstance(answer, dict) and all(
        isinstance(answer.get(k, ""), str) for k in ("provider", "model")
    )


def _is_windows() -> bool:
    """Return whether file modes are meaningless here (Windows)."""
    return os.name == "nt"


def _mode_warning(path: Path, loose_mask: int, what: str) -> None:
    """Warn once when *path* is readable by group or others. Skipped on Windows."""
    if _is_windows():
        return
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except OSError:
        return
    if mode & loose_mask:
        _warn_once(
            "mode",
            str(path),
            "%s %s has mode %s; it should not be readable by group or others.",
            what,
            path,
            format(mode, "o"),
        )


def _read_secret_file(path: Path, secrets: Path) -> str | None:
    """Return the stripped content of *path*, or ``None`` when it is not usable.

    The file must resolve to a regular file inside *secrets*, hold at most
    :data:`MAX_KEY_BYTES` and not be blank. A loose mode only warns.
    """
    try:
        real = path.resolve(strict=True)
        root = secrets.resolve(strict=True)
        if not real.is_relative_to(root):
            return None
        info = real.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_KEY_BYTES:
            return None
        _mode_warning(secrets, 0o077, "Secrets folder")
        _mode_warning(real, 0o077, "Key file")
        with real.open("rb") as handle:
            raw = handle.read(MAX_KEY_BYTES + 1)
        if len(raw) > MAX_KEY_BYTES:
            return None
        return raw.decode("utf-8").strip() or None
    except (OSError, UnicodeDecodeError, RuntimeError):
        return None


def _resolve_reference(key: str, reference: str, secrets: Path, config_path: Path) -> str | None:
    """Resolve an ``env://`` or ``file://`` reference; warn naming *key* only."""
    if reference.startswith("env://"):
        name = reference[len("env://") :]
        if not _ENV_NAME.match(name):
            _warn_once(
                "ref", f"{config_path}:{key}", "Ignoring %s in %s: bad env name.", key, config_path
            )
            return None
        return os.environ.get(name, "").strip() or None
    if reference.startswith("file://"):
        raw = reference[len("file://") :]
        value = _read_secret_file(Path(raw), secrets) if os.path.isabs(raw) else None
        if value is None:
            _warn_once(
                "ref",
                f"{config_path}:{key}",
                "Ignoring %s in %s: its file reference is not a readable file inside secrets/.",
                key,
                config_path,
            )
        return value
    if reference.strip():
        _warn_once(
            "literal",
            f"{config_path}:{key}",
            "Ignoring %s in %s: use env://NAME or file://<path in secrets/>, not the key itself.",
            key,
            config_path,
        )
    return None


def _jsonc_values(data: dict[str, Any], secrets: Path, config_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for key in _ADDRESS_KEYS:
        if str(data.get(key, "")).strip():
            values[key] = data[key].strip()
    for key in _SECRET_KEYS:
        if isinstance(data.get(key), str):
            resolved = _resolve_reference(key, data[key], secrets, config_path)
            if resolved:
                values[key] = resolved
    answer = data.get("answer") or {}
    for part in ("provider", "model"):
        if str(answer.get(part, "")).strip():
            values[f"answer.{part}"] = answer[part].strip()
    return values


def _key_files(secrets: Path) -> dict[str, str]:
    found: dict[str, str] = {}
    for key in _SECRET_KEYS:
        provider = key.removesuffix("_api_key")
        if not _NAME.match(provider):
            continue
        path = secrets / f"{provider}.key"
        if not (path.is_symlink() or path.exists()):
            continue
        value = _read_secret_file(path, secrets)
        if value:
            found[key] = value
    return found


def load_user_config() -> UserConfig:
    """Read the user config folder. Nothing is created or changed.

    Returns:
        The values from ``omrg.jsonc`` and the key files. A missing folder or
        a broken file gives empty values (a broken file logs one warning).
    """
    directory = user_config_dir()
    secrets = directory / SECRETS_DIR
    config_path = directory / CONFIG_FILE
    values: dict[str, str] = {}
    data = _load_json(config_path)
    if data is not None:
        if _typed(data):
            values = _jsonc_values(data, secrets, config_path)
        else:
            _warn_once(
                "broken", str(config_path), "Ignoring %s: a field has the wrong type.", config_path
            )
    return UserConfig(directory, values, _key_files(secrets))
