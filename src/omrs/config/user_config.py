"""The user config folder: ``omrs.jsonc`` and ``secrets/<provider>.key``.

The folder is ``$OMRS_CONFIG_DIR``, else ``$XDG_CONFIG_HOME/omrs``, else
``~/.config/omrs``. This module only reads it. Writing ``omrs.jsonc`` is the
job of ``settings_file_write``; nothing here creates or changes anything.

``omrs.jsonc`` is JSON with comments and trailing commas (read in
``settings_file``). A key field holds a reference: ``env://NAME``,
``file://<absolute path inside secrets/>`` (a leading ``~`` expands to the
home folder) or ``keychain://<provider>``. A literal key in the file is
ignored. ``secrets/<provider>.key`` holds one key per provider.

This module is a leaf: it imports no OMRS code. It returns a ``keychain://``
reference unresolved (``compose_providers`` resolves it). Messages name a
field or a path, never a value.
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

CONFIG_FILE = "omrs.jsonc"
SECRETS_DIR = "secrets"
#: A key file is read up to this size; a larger file is refused.
MAX_KEY_BYTES = 4096
_NAME = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
KEYCHAIN_PREFIX = "keychain://"

#: ``omrs.jsonc`` keys that hold a whole number, with the allowed range. The
#: same range binds the environment, the saved web value and the descriptors.
INT_KEY_BOUNDS: dict[str, tuple[int, int]] = {
    "ollama_context_window": (2048, 262144),
    "llamacpp_context_window": (2048, 262144),
    "llamacpp_idle_sleep_seconds": (0, 86400),
}
#: Keys that also read ``secrets/<provider>.key`` when ``omrs.jsonc`` holds no
#: reference. The provider name is the key minus ``_api_key``.
_SECRET_KEYS = ("openrouter_api_key", "openai_compatible_api_key", "anthropic_api_key")

_warned: set[tuple[str, str]] = set()


@dataclass(frozen=True)
class UserConfig:
    """What the user config folder holds.

    ``repr`` shows field names only, because a value can be an API key.

    Attributes:
        directory: The resolved folder (it may not exist).
        values: ``omrs.jsonc`` values by ``Settings`` field path, with each
            ``env://`` and ``file://`` key reference resolved.
        key_file: Key-file keys by ``Settings`` field name.
        references: ``keychain://`` references by ``Settings`` field name,
            as the provider name. They stay unresolved here.
        key_paths: Where each key from ``file://`` or ``secrets/`` came from.
    """

    directory: Path
    values: dict[str, Any] = field(default_factory=dict)
    key_file: dict[str, str] = field(default_factory=dict)
    references: dict[str, str] = field(default_factory=dict)
    key_paths: dict[str, str] = field(default_factory=dict)

    def __repr__(self) -> str:
        names = sorted({*self.values, *self.key_file, *self.references})
        return f"UserConfig(directory={self.directory}, fields={names})"


def user_config_dir() -> Path:
    """Return the user config folder, which may not exist."""
    explicit = os.environ.get("OMRS_CONFIG_DIR", "").strip()
    if explicit:
        return Path(explicit).expanduser()
    xdg = os.environ.get("XDG_CONFIG_HOME", "").strip()
    return (Path(xdg).expanduser() if xdg else Path.home() / ".config") / "omrs"


def display_path(path: Path | str) -> str:
    """Return *path* with the home folder written as ``~``."""
    text = str(path)
    home = str(Path.home())
    if text == home:
        return "~"
    return "~" + text[len(home) :] if text.startswith(home + os.sep) else text


def config_file_reason(directory: Path | str) -> str:
    """Return the lock text for a field that ``omrs.jsonc`` sets."""
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


@dataclass(frozen=True)
class KeychainRef:
    """A ``keychain://<provider>`` reference, left unresolved for the composition root."""

    provider: str


def _resolve_reference(
    key: str, reference: str, secrets: Path, config_path: Path
) -> tuple[str | KeychainRef | None, str | None]:
    """Resolve a key reference. Warn once, naming *key* only.

    Returns:
        ``(resolved, problem)``. *resolved* is the key text for ``env://`` and
        ``file://``, a :class:`KeychainRef` for ``keychain://``, or ``None``.
        *problem* is a rule text (never a value) when the reference is bad; an
        ``env://`` name that is not set is not a problem.
    """
    subject = f"{config_path}:{key}"
    if reference.startswith("env://"):
        name = reference[len("env://") :]
        if not _ENV_NAME.match(name):
            _warn_once("ref", subject, "Ignoring %s in %s: bad env name.", key, config_path)
            return None, "The env:// reference needs a valid variable name."
        return os.environ.get(name, "").strip() or None, None
    if reference.startswith("file://"):
        raw = os.path.expanduser(reference[len("file://") :])
        value = _read_secret_file(Path(raw), secrets) if os.path.isabs(raw) else None
        if value is None:
            _warn_once(
                "ref",
                subject,
                "Ignoring %s in %s: its file reference is not a readable file inside secrets/.",
                key,
                config_path,
            )
            return None, "The file:// reference must name a readable file inside secrets/."
        return value, None
    if reference.startswith(KEYCHAIN_PREFIX):
        provider = reference[len(KEYCHAIN_PREFIX) :]
        if _NAME.match(provider):
            return KeychainRef(provider), None
        _warn_once("ref", subject, "Ignoring %s in %s: bad keychain name.", key, config_path)
        return None, "The keychain:// reference needs a provider name."
    if not reference.strip():
        return None, None
    _warn_once(
        "literal",
        subject,
        "Ignoring %s in %s: use env://NAME, file://<path in secrets/> or keychain://<provider>, "
        "not the key itself.",
        key,
        config_path,
    )
    return None, REFERENCE_RULE


#: The rule for a key field. It never repeats the value that broke it.
REFERENCE_RULE = (
    "A key field must hold env://NAME, file://<path in secrets/> or keychain://<provider>, "
    "not the key itself."
)


def reference_problem(reference: str, secrets: Path) -> str | None:
    """Return the rule that key *reference* breaks, or ``None`` when its form is valid.

    This checks the form only, so a save can refuse a literal key without
    reading anything. Reading re-checks the file itself (links, size, type).
    The result never contains *reference*.
    """
    if reference.startswith("env://"):
        ok = bool(_ENV_NAME.match(reference[len("env://") :]))
    elif reference.startswith(KEYCHAIN_PREFIX):
        ok = bool(_NAME.match(reference[len(KEYCHAIN_PREFIX) :]))
    elif reference.startswith("file://"):
        raw = os.path.expanduser(reference[len("file://") :])
        root = os.path.normpath(secrets)
        ok = os.path.isabs(raw) and os.path.normpath(raw).startswith(root + os.sep)
    else:
        return REFERENCE_RULE
    return None if ok else REFERENCE_RULE


def key_files(secrets: Path) -> dict[str, str]:
    """Return the keys from ``secrets/<provider>.key``, by ``Settings`` field name."""
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
