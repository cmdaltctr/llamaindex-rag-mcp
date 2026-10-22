"""Bounded previews and private run artefacts.

Events and run records hold small, redacted previews only. When a value is
larger than a preview limit, the full redacted value goes to a private
artefact file under the workspace, and the preview names it with an
``artefact_ref``. Raw vectors are never stored: they become a short
``{"omitted": "vector data", "length": n}`` marker everywhere.

Directories that the store creates get mode 0o700. Files get mode 0o600.
"""

from __future__ import annotations

import dataclasses
import json
import math
import os
import re
import uuid
from collections.abc import Mapping, Set
from pathlib import Path
from typing import Any

from omrs.core.workspace.redaction import redact

MAX_PREVIEW_ROWS = 100
MAX_TEXT_BYTES = 4 * 1024
MAX_SUMMARY_BYTES = 16 * 1024
MAX_ARTEFACT_BYTES = 64 * 1024 * 1024
VECTOR_KEYS: frozenset[str] = frozenset({"embedding", "embeddings", "vector", "vectors"})
# A list of this many floats or more is treated as a raw vector.
VECTOR_MIN_LENGTH = 64

_SEGMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")


def _omitted_vector(length: int) -> dict[str, Any]:
    return {"omitted": "vector data", "length": length}


def _is_vector(items: list[Any]) -> bool:
    return len(items) >= VECTOR_MIN_LENGTH and all(
        isinstance(item, float) and not isinstance(item, bool) for item in items
    )


def to_jsonable(value: Any) -> Any:
    """Return a JSON-compatible copy of ``value`` without raw vectors.

    Pydantic models are dumped, sequences become lists, NaN and infinity
    become text, and any other object becomes its text form. Values under a
    vector key, and long lists of floats, become an omission marker.
    """
    if hasattr(value, "model_dump"):
        return to_jsonable(value.model_dump())
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        # Graph port values (for example ranked evidence) are frozen
        # dataclasses. Keep their fields; a ``public_rows()`` method gives
        # the public row shape, the same rows ``search()`` returns.
        data = {f.name: getattr(value, f.name) for f in dataclasses.fields(value)}
        public_rows = getattr(value, "public_rows", None)
        if callable(public_rows):
            data["rows"] = public_rows()
        return to_jsonable(data)
    if hasattr(value, "tolist") and not isinstance(value, str | bytes):
        return to_jsonable(value.tolist())
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if str(key).lower() in VECTOR_KEYS and isinstance(item, list | tuple):
                result[str(key)] = _omitted_vector(len(item))
            else:
                result[str(key)] = to_jsonable(item)
        return result
    if isinstance(value, list | tuple | Set):
        items = sorted(value, key=repr) if isinstance(value, Set) else list(value)
        return _omitted_vector(len(items)) if _is_vector(items) else [to_jsonable(i) for i in items]
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, bytes | bytearray):
        return {"omitted": "binary data", "length": len(value)}
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _bound(value: Any) -> tuple[Any, bool]:
    if isinstance(value, str):
        encoded = value.encode("utf-8")
        if len(encoded) <= MAX_TEXT_BYTES:
            return value, False
        return encoded[:MAX_TEXT_BYTES].decode("utf-8", errors="ignore"), True
    if isinstance(value, dict):
        items = list(value.items())
        truncated = len(items) > MAX_PREVIEW_ROWS
        bounded: dict[str, Any] = {}
        for key, item in items[:MAX_PREVIEW_ROWS]:
            bounded[key], cut = _bound(item)
            truncated = truncated or cut
        return bounded, truncated
    if isinstance(value, list):
        truncated = len(value) > MAX_PREVIEW_ROWS
        rows = []
        for item in value[:MAX_PREVIEW_ROWS]:
            row, cut = _bound(item)
            rows.append(row)
            truncated = truncated or cut
        return rows, truncated
    return value, False


def bound_preview(value: Any) -> tuple[Any, bool]:
    """Limit a JSON-compatible value to the preview bounds.

    Lists and mappings keep their first 100 entries. Text keeps its first
    4 KiB of UTF-8.

    Returns:
        The bounded copy and whether anything was cut.
    """
    return _bound(value)


def _size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False).encode("utf-8"))


def preview(value: Any, *, max_bytes: int = MAX_SUMMARY_BYTES) -> tuple[Any, bool]:
    """Return a redacted, bounded preview of any value.

    When the bounded preview is still larger than ``max_bytes``, it is
    replaced by an omission marker.

    Returns:
        The preview and whether it differs from the full redacted value.
    """
    bounded, truncated = bound_preview(redact(to_jsonable(value)))
    if _size(bounded) > max_bytes:
        return {"omitted": f"preview larger than {max_bytes} bytes"}, True
    return bounded, truncated


def _private_dir(path: Path) -> None:
    missing = []
    while not path.exists():
        missing.append(path)
        path = path.parent
    for directory in reversed(missing):
        directory.mkdir(mode=0o700)
        os.chmod(directory, 0o700)


def _check_segment(value: str, label: str) -> str:
    if not _SEGMENT.fullmatch(value) or ".." in value:
        raise ValueError(f"invalid artefact {label}: {value!r}")
    return value


class ArtefactStore:
    """Private JSON artefacts for runs, under one root directory.

    A reference has the form ``<run_id>/<name>.json``. It is relative to the
    root and cannot name a path outside it. The root is created on the
    first write.

    Args:
        root: Artefact directory inside the workspace.
    """

    def __init__(self, root: Path) -> None:
        """Create a store; nothing is written until the first artefact."""
        self.root = Path(root)

    def path(self, ref: str) -> Path:
        """Return the file of a reference.

        Raises:
            ValueError: If the reference is malformed or leaves the root.
        """
        run_id, sep, file_name = ref.partition("/")
        if not sep or not file_name.endswith(".json"):
            raise ValueError(f"invalid artefact reference: {ref!r}")
        _check_segment(run_id, "reference")
        _check_segment(file_name[: -len(".json")], "reference")
        path = self.root / run_id / file_name
        if path.exists() and not path.resolve().is_relative_to(self.root.resolve()):
            raise ValueError(f"artefact reference leaves the store: {ref!r}")
        return path

    def write_json(self, run_id: str, name: str, value: Any) -> str:
        """Write a redacted JSON artefact and return its reference.

        A value larger than 64 MiB is replaced by an omission marker.

        Raises:
            ValueError: If ``run_id`` or ``name`` is not a safe file name.
        """
        _check_segment(run_id, "run id")
        _check_segment(name, "name")
        data = json.dumps(redact(to_jsonable(value)), ensure_ascii=False).encode("utf-8")
        if len(data) > MAX_ARTEFACT_BYTES:
            marker = {"omitted": f"artefact larger than {MAX_ARTEFACT_BYTES} bytes"}
            data = json.dumps({**marker, "bytes": len(data)}).encode("utf-8")
        directory = self.root / run_id
        _private_dir(directory)
        target = directory / f"{name}.json"
        temporary = directory / f".{name}.{uuid.uuid4().hex}.tmp"
        descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
            os.chmod(temporary, 0o600)
            os.replace(temporary, target)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        return f"{run_id}/{name}.json"

    def read_json(self, ref: str) -> Any:
        """Return the content of an artefact.

        Raises:
            ValueError: If the reference is invalid.
            FileNotFoundError: If the artefact does not exist.
        """
        return json.loads(self.path(ref).read_text(encoding="utf-8"))

    def safe_summary(self, run_id: str, name: str, value: Mapping[str, Any]) -> dict[str, Any]:
        """Return a redacted, bounded event summary.

        When the summary had to be cut, the full redacted value is written
        to an artefact. The summary then carries ``truncated: true`` and the
        ``artefact_ref`` of that artefact.
        """
        summary, truncated = preview(dict(value), max_bytes=MAX_SUMMARY_BYTES - 512)
        if not truncated:
            return summary
        ref = self.write_json(run_id, name, dict(value))
        return {**summary, "truncated": True, "artefact_ref": ref}
