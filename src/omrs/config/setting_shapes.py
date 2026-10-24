"""The shape of each setting: the control kind, its choices, bounds and null (D2).

The Configuration page shows one control per setting. The server reads the
control from the ``Settings`` model, so the page keeps no key lists of its own:

- ``kind`` is ``bool``, ``int``, ``float``, ``text`` or ``choice``, or ``None``
  for a setting that is not one plain value (a tuple, for example);
- ``choices`` come from a ``Literal`` type, from :data:`rules.ACCEPTED`, or
  from :data:`rules.PDF_READER_NAMES` for ``pdf_reader``;
- ``min`` and ``max`` are inclusive. A whole-number ``gt`` n gives the minimum
  n + 1; a number ``gt`` or ``lt`` has no inclusive bound, so it gives ``None``;
- ``nullable`` is true for a setting that takes ``None`` (an optional number).

The three file-only keys take their shape from :data:`rules.FILE_ONLY`.

This module is a leaf: it imports only ``config/`` modules, which read the
pure-data settings models.
"""

from __future__ import annotations

import types
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, Union, get_args, get_origin

from .rules import ACCEPTED, FILE_ONLY, PDF_READER_NAMES
from .settings_file import _settings_class, field_bounds, setting_blocks

if TYPE_CHECKING:
    from pydantic.fields import FieldInfo

KIND_BOOL = "bool"
KIND_INT = "int"
KIND_FLOAT = "float"
KIND_TEXT = "text"
KIND_CHOICE = "choice"

_KINDS: dict[type, str] = {bool: KIND_BOOL, int: KIND_INT, float: KIND_FLOAT, str: KIND_TEXT}


@dataclass(frozen=True)
class SettingShape:
    """The control of one setting.

    Attributes:
        kind: ``bool``, ``int``, ``float``, ``text`` or ``choice``; ``None`` when
            the setting is not one plain value.
        choices: The accepted values of a ``choice`` setting, else ``None``.
        min: The inclusive lower bound of a number, else ``None``.
        max: The inclusive upper bound of a number, else ``None``.
        nullable: The setting takes ``None``, so Clear restores its default.
    """

    kind: str | None
    choices: tuple[str, ...] | None = None
    min: int | float | None = None
    max: int | float | None = None
    nullable: bool = False


#: The shape of a key that names no setting.
NO_SHAPE = SettingShape(kind=None)


def setting_field(path: str) -> FieldInfo | None:
    """Return the ``Settings`` field of the dotted *path*, or ``None`` when there is none."""
    cls = _settings_class()
    block_name, _, leaf = path.rpartition(".")
    if not block_name:
        return cls.model_fields.get(path)
    block = setting_blocks(cls).get(block_name)
    return None if block is None else block.model_fields.get(leaf)


def _base_type(annotation: Any) -> tuple[Any, bool]:
    """Return ``(type, nullable)``: the one non-``None`` member of *annotation*."""
    if get_origin(annotation) in (Union, types.UnionType):
        members = [arg for arg in get_args(annotation) if arg is not type(None)]
        nullable = len(members) < len(get_args(annotation))
        return (members[0] if len(members) == 1 else None), nullable
    return annotation, False


def _bounds(kind: str, info: FieldInfo) -> tuple[Any, Any]:
    """Return the inclusive ``(min, max)`` of a number field."""
    found = field_bounds(info)
    low, high = found.get("ge"), found.get("le")
    if kind == KIND_INT:
        if low is None and found.get("gt") is not None:
            low = found["gt"] + 1
        if high is None and found.get("lt") is not None:
            high = found["lt"] - 1
    return low, high


def _choices(path: str, base: Any) -> tuple[str, ...] | None:
    if get_origin(base) is Literal:
        return tuple(str(arg) for arg in get_args(base))
    if path == "pdf_reader":
        return PDF_READER_NAMES
    return ACCEPTED.get(path)


def setting_shape(path: str) -> SettingShape:
    """Return the control of the setting *path*; :data:`NO_SHAPE` when it is unknown."""
    if path in FILE_ONLY:
        kind, low, high = FILE_ONLY[path]
        return (
            SettingShape(KIND_BOOL) if kind == "bool" else SettingShape(KIND_INT, None, low, high)
        )
    info = setting_field(path)
    if info is None:
        return NO_SHAPE
    base, nullable = _base_type(info.annotation)
    choices = _choices(path, base)
    if choices is not None:
        return SettingShape(KIND_CHOICE, choices, nullable=nullable)
    kind = _KINDS.get(base) if isinstance(base, type) else None
    if kind is None:
        return SettingShape(None, nullable=nullable)
    low, high = _bounds(kind, info) if kind in (KIND_INT, KIND_FLOAT) else (None, None)
    return SettingShape(kind, None, low, high, nullable)


def is_scalar(path: str) -> bool:
    """Return whether *path* holds one plain value: a boolean, a number, a text or a choice."""
    return setting_shape(path).kind is not None
