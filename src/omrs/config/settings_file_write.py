"""Write ``omrs.jsonc`` safely (ADR-087, D5).

The Settings page is a second editor of the file. :func:`write_settings`
changes only the keys it is given and keeps every other byte (comments, order,
layout) through ``jsonc_edit``. It refuses, and writes nothing, when:

- a key is not one the page edits (:data:`ALLOWED_KEYS`, or a provider key
  field) or a value breaks its rule (:class:`SettingsFileRefused`, answer 400);
- a key field holds a literal key instead of a reference (same error);
- the file changed since the caller read it (:class:`SettingsFileConflict`,
  answer 409);
- the file cannot be parsed, or a key on the path appears twice (same error).

A write goes to ``omrs.jsonc.tmp`` in the same folder, is flushed, then
replaces the file with ``os.replace``, so a crash leaves the old content or
the new, never half. A new file gets mode 0600 and a new folder 0700; an
existing file keeps its mode. A lock serialises writes inside the process.
Only ``omrs web`` writes the file, so there is no cross-process lock.

The server writes references into the file, never a key. It does not create or
change ``.env`` or anything in ``secrets/``. No message holds a value.

This module is a leaf: it imports only ``config/`` modules.
"""

from __future__ import annotations

import hashlib
import os
import stat
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .jsonc_edit import JsoncEditError, remove_value, set_value
from .provider_sources import PROVIDER_FIELDS
from .rules import INTERNAL_FIELDS, SECRET_FIELDS, document_reading_problem
from .setting_shapes import is_scalar
from .settings_file import ABSENT, check_setting, setting_paths
from .user_config import (
    CONFIG_FILE,
    REFERENCE_RULE,
    SECRETS_DIR,
    parse_jsonc,
    reference_problem,
    user_config_dir,
)

_EMBEDDING = (
    "The embedding model is part of every collection. Change it in omrs.jsonc and re-ingest."
)
_STORAGE = "Existing collections stay where they are. Change it in omrs.jsonc and restart."
#: The reason of every key field: the Providers cards write references.
KEY_FIELD_REASON = "Keys are set on the provider cards as references."
EDIT_BY_HAND = "Edit this in omrs.jsonc."
NOT_A_SETTING = "This is not a setting."

#: Keys the page never writes, each with the reason the page shows (design D1).
#: An entry that ends in ``.`` covers every key of that block. Key fields are
#: read-only too (:data:`KEY_FIELD_REASON`), as is any setting that is not one
#: plain value (:data:`EDIT_BY_HAND`).
READ_ONLY_KEYS: Mapping[str, str] = {
    "embed_provider": _EMBEDDING,
    "embed_model": _EMBEDDING,
    "local_backend": _EMBEDDING,
    "cloud_backend": _EMBEDDING,
    "llamacpp_embed_url": _EMBEDDING,
    "llamacpp_embed_model": _EMBEDDING,
    "openrouter_embed_model": _EMBEDDING,
    "embedding.": _EMBEDDING,
    "vector_store": _STORAGE,
    "lancedb_uri": _STORAGE,
    "chroma_persist_dir": _STORAGE,
    "chroma_mode": _STORAGE,
    "collection_name": _STORAGE,
    "ocr_workers_dir": "The worker folder is set when the OCR workers are installed.",
    "ingestion.ingest_extensions": EDIT_BY_HAND,
    "metadata.keyword_rules": EDIT_BY_HAND,
}


def read_only_reason(key: str) -> str | None:
    """Return why the page may not write *key*, or ``None`` when it may.

    The reason never holds a value. A key that names no setting gives
    :data:`NOT_A_SETTING`.
    """
    if key in SECRET_FIELDS:
        return KEY_FIELD_REASON
    if key in READ_ONLY_KEYS:
        return READ_ONLY_KEYS[key]
    block, dot, _ = key.partition(".")
    if dot and f"{block}." in READ_ONLY_KEYS:
        return READ_ONLY_KEYS[f"{block}."]
    if key in INTERNAL_FIELDS or key not in setting_paths():
        return NOT_A_SETTING
    return None if is_scalar(key) else EDIT_BY_HAND


#: The keys the Settings page may write: every setting that is one plain value
#: (a boolean, a number, a text or a choice) and has no read-only reason. It is
#: computed from the model, so a new plain setting is writable with no edit here.
ALLOWED_KEYS: tuple[str, ...] = tuple(
    key for key in setting_paths() if read_only_reason(key) is None
)
#: What :func:`write_settings` takes: :data:`ALLOWED_KEYS` plus the provider key
#: fields, which the Providers cards write as references only.
_WRITABLE: frozenset[str] = frozenset(
    {*ALLOWED_KEYS, *(key for key in PROVIDER_FIELDS if key in SECRET_FIELDS)}
)

CONFLICT_CHANGED = "omrs.jsonc changed on disk. Reload to see the new values."
CONFLICT_BROKEN = "omrs.jsonc could not be read. Fix it, then save again."
WRITE_FAILED = "omrs.jsonc could not be written."
_TEMP_NAME = f"{CONFIG_FILE}.tmp"
_NEW_FILE_MODE = 0o600
_NEW_FOLDER_MODE = 0o700
_HEADER = (
    "// omrs.jsonc: OMRS settings. The Settings page and a text editor both edit this file.\n"
    '// A key is the environment name in lower case; "__" nests one level, so\n'
    "// RETRIEVAL__TOP_K is retrieval.top_k.\n"
    "// A key field holds a reference (env://NAME, file://<path in secrets/> or\n"
    "// keychain://<provider>), never the key itself.\n"
    "{\n}\n"
)

_lock = threading.Lock()


class SettingsFileError(Exception):
    """A write did not happen. ``str(error)`` is a message that holds no value."""


class SettingsFileRefused(SettingsFileError):
    """A key or value is not allowed (answer 400). Nothing was written."""


class SettingsFileConflict(SettingsFileError):
    """The file changed, is broken or has a duplicate key (answer 409). Nothing was written."""


class SettingsFileWriteError(SettingsFileError):
    """The disk refused the write. The old file is intact."""


@dataclass(frozen=True)
class WriteResult:
    """Outcome of a write.

    Attributes:
        revision: Revision of the file after the write (``absent`` if none exists).
        changed: Whether the file was written.
    """

    revision: str
    changed: bool


def _revision(raw: bytes | None) -> str:
    return ABSENT if raw is None else hashlib.sha256(raw).hexdigest()


def _plan(changes: Mapping[str, Any], secrets: Path) -> dict[str, Any]:
    """Check every change. Return ``{key: value or None}``, a blank value as ``None``."""
    plan: dict[str, Any] = {}
    for key, value in changes.items():
        if key not in _WRITABLE:
            raise SettingsFileRefused(f"{key} is not a setting that can be changed here.")
        reading_rule = document_reading_problem(key, value)  # blank text is refused here
        if reading_rule is not None:
            raise SettingsFileRefused(f"{key}: {reading_rule}")
        if value is None or (isinstance(value, str) and not value.strip()):
            plan[key] = None
        elif key in SECRET_FIELDS:
            rule = (
                REFERENCE_RULE if not isinstance(value, str) else reference_problem(value, secrets)
            )
            if rule is not None:
                raise SettingsFileRefused(f"{key}: {rule}")
            plan[key] = value
        else:
            validated, rule = check_setting(key, value)
            if rule is not None:
                raise SettingsFileRefused(f"{key}: {rule}")
            plan[key] = validated
    return plan


def _read(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except (FileNotFoundError, NotADirectoryError):
        return None
    except OSError as exc:
        raise SettingsFileConflict(CONFLICT_BROKEN) from exc


def _edit(text: str, plan: Mapping[str, Any]) -> str:
    try:
        for key, value in plan.items():
            path = tuple(key.split("."))
            text = remove_value(text, path) if value is None else set_value(text, path, value)
        parse_jsonc(text)
    except JsoncEditError as exc:
        raise SettingsFileConflict(str(exc)) from exc
    except ValueError as exc:
        raise SettingsFileConflict(CONFLICT_BROKEN) from exc
    return text


def _write_atomically(real: Path, data: bytes, mode: int) -> None:
    """Write *data* to *real* through a temporary file and ``os.replace``."""
    temp = real.with_name(_TEMP_NAME)
    try:
        temp.unlink(missing_ok=True)
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
        try:
            if hasattr(os, "fchmod"):
                os.fchmod(fd, mode)  # the umask may have narrowed the mode
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        except BaseException:
            temp.unlink(missing_ok=True)
            raise
        os.replace(temp, real)
    except OSError as exc:
        temp.unlink(missing_ok=True)
        raise SettingsFileWriteError(WRITE_FAILED) from exc


def write_settings(
    changes: Mapping[str, Any], *, revision: str | None, directory: Path | None = None
) -> WriteResult:
    """Set or remove keys in ``omrs.jsonc``. All changes land in one replace, or none do.

    Args:
        changes: Dotted key to new value. ``None`` or a blank string removes the
            key. A key field takes a reference, never a key. Keys must be in
            :data:`ALLOWED_KEYS` or be a provider key field.
        revision: The revision the caller read (``absent`` for no file). The
            write refuses when the file differs. ``None`` skips the check; use
            it only where no person edited the file in between.
        directory: The user config folder (default: the resolved one).

    Returns:
        The revision after the write. When nothing changes, the file is not
        rewritten.

    Raises:
        SettingsFileRefused: A key or value is not allowed.
        SettingsFileConflict: The file changed, cannot be parsed, or holds a
            duplicate key on the path.
        SettingsFileWriteError: The disk refused the write.
    """
    folder = directory or user_config_dir()
    plan = _plan(changes, folder / SECRETS_DIR)
    path = folder / CONFIG_FILE
    with _lock:
        real = Path(os.path.realpath(path))  # write through a link (dotfile managers)
        raw = _read(real)
        if revision is not None and revision != _revision(raw):
            raise SettingsFileConflict(CONFLICT_CHANGED)
        if raw is None and all(value is None for value in plan.values()):
            return WriteResult(ABSENT, False)
        old = _HEADER if raw is None else raw.decode("utf-8", errors="replace")
        if raw is not None:
            try:
                if not isinstance(parse_jsonc(old), dict):
                    raise ValueError
            except ValueError as exc:
                raise SettingsFileConflict(CONFLICT_BROKEN) from exc
        new = _edit(old, plan)
        if raw is not None and new == old:
            return WriteResult(_revision(raw), False)
        data = new.encode("utf-8")
        mode = _NEW_FILE_MODE if raw is None else stat.S_IMODE(real.stat().st_mode)
        _ensure_folder(real.parent)
        _write_atomically(real, data, mode)
        return WriteResult(_revision(data), True)


def _ensure_folder(folder: Path) -> None:
    """Create *folder* with mode 0700 when it is missing. An existing folder is not changed."""
    if folder.is_dir():
        return
    try:
        folder.mkdir(parents=True, mode=_NEW_FOLDER_MODE, exist_ok=True)
        folder.chmod(_NEW_FOLDER_MODE)
    except OSError as exc:
        raise SettingsFileWriteError(WRITE_FAILED) from exc
