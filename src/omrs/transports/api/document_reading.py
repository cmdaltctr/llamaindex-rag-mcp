"""The body and the write checks of ``/v1/settings/document-reading`` (design D10).

Settings > Document reading edits nine server-wide keys in ``omrs.jsonc``. Each
key applies only at the next launch, so a row shows the value in force since
launch (the launch ``Settings``), the valid value the file holds now, the
source, the default and whether a restart is pending. A key that ``env`` or
``.env`` sets is locked.

The body reads the launch state on ``app.state.configuration`` (the same
``ConfigurationState`` the Configuration route reads). When that state is
missing, it uses ``compose.get_settings()`` and the file as it is now, so no
row is pending.

This module imports no web framework. No message holds a submitted value.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from ... import capabilities
from ...config.rules import DOCUMENT_READING_KEYS, document_reading_problem
from ...config.settings_file import SettingsFile, read_settings_file
from ...config.user_config import display_path
from ..settings_view import plain, source_word
from .restart_snapshot import capture, pending

if TYPE_CHECKING:
    from ...config import Settings

logger = logging.getLogger(__name__)

#: Source words a row may show. ``init`` and ``yaml`` read ``default``.
_SHOWN_SOURCES = frozenset({"env", "dotenv", "config-file"})
_LOCKING_SOURCES = frozenset({"env", "dotenv"})
NOT_A_READING_KEY = "{key} is not a document reading setting."
READER_NOT_INSTALLED = (
    "pdf_reader: This PDF reader is not installed. Install its package, then save again."
)

#: The reader the running engine uses. It is resolved once per process.
_reader_in_use: list[str] = []


def reset_reader_in_use() -> None:
    """Forget the resolved reader (used by tests)."""
    _reader_in_use.clear()


def reader_in_use(launch: Settings) -> str | None:
    """Return the PDF reader that *launch* resolves to, or ``None`` when that fails."""
    if not _reader_in_use:
        try:
            _reader_in_use.append(capabilities.resolve_pdf_reader(launch))
        except Exception:
            logger.exception("The PDF reader in use could not be resolved.")
            return None
    return _reader_in_use[0]


def lock_reason(key: str) -> str:
    """Return the lock text for *key*, which names its environment variable."""
    return f"Remove {key.upper()} from the environment or .env to edit it here."


def row_source(launch: Settings, key: str) -> str:
    """Return ``env``, ``dotenv``, ``config-file`` or ``default`` for *key* at launch."""
    word = source_word(launch, key)
    return word if word in _SHOWN_SOURCES else "default"


def _launch_state(state: Any) -> tuple[Settings, SettingsFile, Mapping[str, Any]]:
    """Return the launch ``Settings``, the file now and the launch snapshot."""
    launch = launch_settings(state)
    read_file = getattr(state, "read_file", None) or read_settings_file
    file = read_file()
    snapshot = getattr(state, "snapshot", None)
    return launch, file, capture(file) if snapshot is None else snapshot


def _saved(file: SettingsFile, key: str) -> Any:
    """Return the valid value the file holds for *key*, or ``None``."""
    if key in file.values:
        value = file.values[key]
        return None if document_reading_problem(key, value) is not None else value
    return None


def _rows(launch: Settings, file: SettingsFile, snapshot: Mapping[str, Any]) -> list[dict]:
    changed = pending(snapshot, file)
    fields = type(launch).model_fields
    rows = []
    for key in DOCUMENT_READING_KEYS:
        source = row_source(launch, key)
        locked = source in _LOCKING_SOURCES
        rows.append(
            {
                "key": key,
                "value": plain(getattr(launch, key)),
                "saved": _saved(file, key),
                "source": source,
                "locked": locked,
                "lock_reason": lock_reason(key) if locked else None,
                "restart_pending": key in changed and not locked,
                "default": fields[key].default,
            }
        )
    return rows


def _readers() -> list[dict[str, Any]]:
    readers: list[dict[str, Any]] = [{"name": "auto", "available": True, "reason": None}]
    for name, reason in capabilities.pdf_reader_options().items():
        readers.append({"name": name, "available": reason is None, "reason": reason})
    return readers


def _ocr(launch: Settings, rows: list[dict[str, Any]]) -> dict[str, Any]:
    workers_dir = launch.ocr_workers_dir.strip()
    names = [
        str(row[field] or "")
        for row in rows
        if row["key"] in ("ocr_engine_primary", "ocr_engine_fallback")
        for field in ("value", "saved")
    ]
    return {
        "workers_dir": display_path(workers_dir) if workers_dir else None,
        "worker_command_set": bool(launch.ocr_worker_command.strip()),
        "engines": capabilities.ocr_engine_options(workers_dir, names),
    }


def build_document_reading(state: Any) -> dict[str, Any]:
    """Return the body of ``GET /v1/settings/document-reading`` without ``status``.

    Args:
        state: ``app.state.configuration``, or ``None`` when the launch set none.

    Returns:
        ``revision``, the nine ``settings`` rows in key order, ``pdf_readers``,
        ``pdf_reader_in_use`` and the ``ocr`` block (design D10).
    """
    launch, file, snapshot = _launch_state(state)
    rows = _rows(launch, file, snapshot)
    return {
        "revision": file.revision,
        "settings": rows,
        "pdf_readers": _readers(),
        "pdf_reader_in_use": reader_in_use(launch),
        "ocr": _ocr(launch, rows),
    }


def launch_settings(state: Any) -> Settings:
    """Return the launch ``Settings`` of *state*, or ``compose.get_settings()``."""
    launch = getattr(state, "launch_settings", None)
    if launch is not None:
        return launch
    from ... import compose

    return compose.get_settings()


def update_refusal(values: Mapping[str, Any], launch: Settings) -> tuple[int, str] | None:
    """Run checks 2 to 5 of a ``PUT`` and return ``(status, message)``, or ``None``.

    The checks run in contract order: a key outside the nine (400), a locked key
    (409, the first in key order), a value that breaks its rule (400), then a
    PDF reader that is not installed (400). The body shape (check 1) is the
    framework's job; the file checks (6 to 8) belong to the writer.

    Args:
        values: The ``values`` member of the request.
        launch: The launch ``Settings``, which say where each value came from.
    """
    for key in values:
        if key not in DOCUMENT_READING_KEYS:
            return 400, NOT_A_READING_KEY.format(key=key)
    for key in DOCUMENT_READING_KEYS:
        if key in values and row_source(launch, key) in _LOCKING_SOURCES:
            return 409, lock_reason(key)
    for key in DOCUMENT_READING_KEYS:
        if key in values:
            rule = document_reading_problem(key, values[key])
            if rule is not None:
                return 400, f"{key}: {rule}"
    return reader_refusal(values)


def reader_refusal(values: Mapping[str, Any]) -> tuple[int, str] | None:
    """Return ``(400, READER_NOT_INSTALLED)`` when *values* name a PDF reader that is missing.

    ``auto``, ``None`` and a missing ``pdf_reader`` pass. The Configuration save
    runs this check too.
    """
    reader = values.get("pdf_reader")
    if reader not in (None, "auto") and capabilities.pdf_reader_options().get(reader) is not None:
        return 400, READER_NOT_INSTALLED
    return None
