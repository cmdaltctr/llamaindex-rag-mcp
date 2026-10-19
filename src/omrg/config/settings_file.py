"""Read ``omrg.jsonc``: every setting, one naming rule (ADR-087, D2, D3).

The file key is the environment name in lower case, and ``__`` nests one
level: ``RETRIEVAL__TOP_K`` is ``retrieval.top_k`` (the object
``{"retrieval": {"top_k": 7}}``) and ``EMBED_PROVIDER`` is ``embed_provider``.
``web_port``, ``web_max_upload_mib`` and ``mcp_http_enabled`` have no
environment twin and live only in the file.

:func:`read_settings_file` checks each value on its own. A value that breaks
its rule is ignored and listed as a :class:`Problem`, and the other values
stay. A file that cannot be parsed gives no values. Nothing here raises for a
bad file, and no message holds a value.

:class:`UserConfigSource` hands the validated values to ``Settings`` between
the ``.env`` source and the YAML sources.

This module is a leaf: it reads files and imports pure-data models only.
"""

from __future__ import annotations

import hashlib
import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, get_args

from pydantic import BaseModel, TypeAdapter, ValidationError
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource

from .rules import (
    FILE_ONLY,
    INTERNAL_FIELDS,
    SECRET_FIELDS,
    accepted_problem,
    file_only_problem,
)
from .user_config import (
    CONFIG_FILE,
    REFERENCE_RULE,
    SECRETS_DIR,
    KeychainRef,
    UserConfig,
    _resolve_reference,
    _warn_once,
    key_files,
    parse_jsonc,
    user_config_dir,
)

if TYPE_CHECKING:
    from pydantic.fields import FieldInfo

logger = logging.getLogger(__name__)

#: Problem kinds.
KIND_BROKEN = "broken"
KIND_INVALID = "invalid"
KIND_UNKNOWN = "unknown"
KIND_RETIRED = "retired"

#: Revision of a folder with no ``omrg.jsonc``.
ABSENT = "absent"
#: Revision of a file that exists and cannot be read.
UNREADABLE = "unreadable"
BROKEN_MESSAGE = "omrg.jsonc could not be read"


@dataclass(frozen=True)
class Problem:
    """One thing wrong in ``omrg.jsonc``. It never holds a value.

    Attributes:
        kind: ``broken``, ``invalid``, ``unknown`` or ``retired``.
        key: The dotted key (``retrieval.top_k``), or ``omrg.jsonc`` for a broken file.
        message: Plain-English rule or advice.
        replacement: For ``retired``: the key that replaced it.
    """

    kind: str
    key: str
    message: str
    replacement: str | None = None


@dataclass(frozen=True)
class SettingsFile:
    """What ``omrg.jsonc`` and ``secrets/`` hold. ``repr`` shows names only.

    Attributes:
        directory: The user config folder (it may not exist).
        path: The ``omrg.jsonc`` path.
        revision: SHA-256 of the file bytes, or ``absent``.
        state: ``absent``, ``ok`` or ``broken``.
        values: Valid non-secret values by dotted key, including the
            file-only keys.
        secrets: Keys that ``env://`` and ``file://`` references resolved.
        references: ``keychain://`` references: field name to provider name.
        key_paths: Field name to the file a ``file://`` reference read.
        key_file: Keys from ``secrets/<provider>.key``, by field name.
        problems: Everything that was ignored, in file order.
    """

    directory: Path
    path: Path
    revision: str = ABSENT
    state: str = "absent"
    values: Mapping[str, Any] = field(default_factory=dict)
    secrets: Mapping[str, str] = field(default_factory=dict, repr=False)
    references: Mapping[str, str] = field(default_factory=dict)
    key_paths: Mapping[str, str] = field(default_factory=dict)
    key_file: Mapping[str, str] = field(default_factory=dict, repr=False)
    problems: tuple[Problem, ...] = ()

    def __repr__(self) -> str:
        names = sorted({*self.values, *self.secrets, *self.references, *self.key_file})
        return f"SettingsFile(path={self.path}, state={self.state}, fields={names})"


def _revision_of(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def file_revision(directory: Path | None = None) -> str:
    """Return the revision of ``omrg.jsonc``: SHA-256 of its bytes, or ``absent``."""
    path = (directory or user_config_dir()) / CONFIG_FILE
    try:
        return _revision_of(path.read_bytes())
    except (FileNotFoundError, NotADirectoryError):
        return ABSENT
    except OSError:
        return UNREADABLE


# ── The setting catalogue ────────────────────────────────────────────────


def _settings_class() -> type[BaseSettings]:
    from . import Settings  # lazy: this module loads before Settings is defined

    return Settings


def setting_blocks(cls: type[BaseSettings]) -> dict[str, type[BaseModel]]:
    return {
        name: info.annotation
        for name, info in cls.model_fields.items()
        if isinstance(info.annotation, type) and issubclass(info.annotation, BaseModel)
    }


def setting_paths(*, file_only: bool = True) -> tuple[str, ...]:
    """Return every dotted setting key the file accepts, in model order.

    Secret fields are included (they take a reference). Bookkeeping fields
    are not.
    """
    cls = _settings_class()
    blocks = setting_blocks(cls)
    paths: list[str] = []
    for name in cls.model_fields:
        if name in INTERNAL_FIELDS:
            continue
        if name in blocks:
            paths.extend(f"{name}.{leaf}" for leaf in blocks[name].model_fields)
        else:
            paths.append(name)
    return (*paths, *FILE_ONLY) if file_only else tuple(paths)


def _replacement(env_name: str) -> str | None:
    """Return the file key that replaced the retired environment name, if any."""
    from .legacy import _NEVER_SHIPPED_ALIASES, _RETIRED_ENV_VARS

    new = _RETIRED_ENV_VARS.get(env_name) or _NEVER_SHIPPED_ALIASES.get(env_name)
    return None if new is None else new.lower().replace("__", ".")


def _rule_text(info: FieldInfo) -> str:
    """Describe the type rule of a field. It names a kind and a range, never a value."""
    names = {info.annotation, *get_args(info.annotation)}
    low = high = None
    for item in info.metadata:
        low = getattr(item, "ge", getattr(item, "gt", low))
        high = getattr(item, "le", getattr(item, "lt", high))
    if bool in names:
        return "The value must be true or false."
    kind = "a whole number" if int in names else "a number" if float in names else None
    if kind is None:
        return "The value must be text." if str in names else "The value is not valid."
    span = f" from {low} to {high}" if low is not None and high is not None else ""
    return f"The value must be {kind}{span}."


_adapters: dict[int, TypeAdapter[Any]] = {}


def _adapter(info: FieldInfo) -> TypeAdapter[Any]:
    key = id(info)
    if key not in _adapters:
        kind = Annotated[(info.annotation, *info.metadata)] if info.metadata else info.annotation
        _adapters[key] = TypeAdapter(kind)
    return _adapters[key]


def _check(
    path: str, value: Any, info: FieldInfo, block: type[BaseModel] | None, leaf: str
) -> tuple[Any, str | None]:
    """Return ``(validated, rule)``: *rule* is ``None`` when *value* is fine."""
    try:
        if block is not None:
            validated = getattr(block.model_validate({leaf: value}), leaf)
        else:
            validated = _adapter(info).validate_python(value)
    except (ValidationError, ValueError, TypeError):
        return None, _rule_text(info)
    if isinstance(value, bool) and not isinstance(validated, bool):
        return None, _rule_text(info)  # true is not the number 1
    if isinstance(validated, str):
        validated = validated.strip()
    return validated, accepted_problem(path, validated)


def check_setting(path: str, value: Any) -> tuple[Any, str | None]:
    """Check *value* for the non-secret setting *path*, as the reader does.

    Returns:
        ``(validated, rule)``. *rule* is ``None`` when *value* is fine and a
        plain-English rule (never the value) when it is not. A path that names
        no setting gives a rule too.
    """
    if path in FILE_ONLY:
        rule = file_only_problem(path, value)
        return (value, None) if rule is None else (None, rule)
    cls = _settings_class()
    block_name, _, leaf = path.rpartition(".")
    if block_name:
        block = setting_blocks(cls).get(block_name)
        if block is None or leaf not in block.model_fields:
            return None, "This is not a setting."
        return _check(path, value, block.model_fields[leaf], block, leaf)
    if path not in cls.model_fields or path in INTERNAL_FIELDS or path in SECRET_FIELDS:
        return None, "This is not a setting."
    return _check(path, value, cls.model_fields[path], None, path)


# ── Reading ──────────────────────────────────────────────────────────────


class _Reader:
    """Collects the result of one read, then freezes it."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.path = directory / CONFIG_FILE
        self.secrets_dir = directory / SECRETS_DIR
        self.values: dict[str, Any] = {}
        self.secrets: dict[str, str] = {}
        self.references: dict[str, str] = {}
        self.key_paths: dict[str, str] = {}
        self.problems: list[Problem] = []
        cls = _settings_class()
        self.fields = cls.model_fields
        self.blocks = setting_blocks(cls)

    def problem(
        self,
        kind: str,
        key: str,
        message: str,
        replacement: str | None = None,
        *,
        log: bool = True,
    ) -> None:
        self.problems.append(Problem(kind, key, message, replacement))
        if log:
            _warn_once(kind, f"{self.path}:{key}", "Ignoring %s in %s: %s", key, self.path, message)

    def add(self, path: str, value: Any, info: FieldInfo, block: type[BaseModel] | None) -> None:
        if isinstance(value, str) and not value.strip():
            return  # blank means not set
        validated, rule = _check(path, value, info, block, path.rpartition(".")[2])
        if rule is not None:
            self.problem(KIND_INVALID, path, rule)
        elif validated is not None:
            self.values[path] = validated

    def secret(self, key: str, value: Any) -> None:
        if not isinstance(value, str):
            self.problem(KIND_INVALID, key, REFERENCE_RULE)
            return
        resolved, problem = _resolve_reference(key, value, self.secrets_dir, self.path)
        if problem is not None:
            self.problem(KIND_INVALID, key, problem, log=False)  # the resolver logged it
        elif isinstance(resolved, KeychainRef):
            self.references[key] = resolved.provider
        elif resolved:
            self.secrets[key] = resolved
            if value.startswith("file://"):
                self.key_paths[key] = os.path.expanduser(value[len("file://") :])

    def unknown(self, key: str, leaf: str | None = None) -> None:
        name = key if leaf is None else f"{key}.{leaf}"
        new = _replacement((key if leaf is None else f"{key}__{leaf}").upper())
        if new is not None:
            self.problem(KIND_RETIRED, name, f"This name is retired. Use {new}.", new)
        else:
            self.problem(KIND_UNKNOWN, name, "This is not a setting.")

    def read(self, data: Mapping[str, Any]) -> None:
        for key, value in data.items():
            if key in FILE_ONLY:
                rule = file_only_problem(key, value)
                if rule is None:
                    self.values[key] = value
                else:
                    self.problem(KIND_INVALID, key, rule)
            elif key in SECRET_FIELDS:
                self.secret(key, value)
            elif key in self.blocks:
                self.read_block(key, value)
            elif key in self.fields and key not in INTERNAL_FIELDS:
                self.add(key, value, self.fields[key], None)
            elif isinstance(value, Mapping) and value:
                self.unknown_block(key, value)
            else:
                self.unknown(key)

    def read_block(self, name: str, value: Any) -> None:
        if not isinstance(value, Mapping):
            self.problem(KIND_INVALID, name, "This must be an object of settings.")
            return
        block = self.blocks[name]
        for leaf, leaf_value in value.items():
            if leaf in block.model_fields:
                self.add(f"{name}.{leaf}", leaf_value, block.model_fields[leaf], block)
            else:
                self.unknown(name, str(leaf))

    def unknown_block(self, name: str, value: Mapping[str, Any]) -> None:
        retired = [leaf for leaf in value if _replacement(f"{name}__{leaf}".upper())]
        for leaf in retired:
            self.unknown(name, str(leaf))
        if len(retired) < len(value):
            self.unknown(name)


def _broken(directory: Path, path: Path, revision: str, key_file: dict[str, str]) -> SettingsFile:
    _warn_once("broken", str(path), "Ignoring %s: it cannot be read as JSON with comments.", path)
    problems = (Problem(KIND_BROKEN, CONFIG_FILE, BROKEN_MESSAGE),)
    return SettingsFile(directory, path, revision, "broken", key_file=key_file, problems=problems)


def read_settings_file(directory: Path | None = None) -> SettingsFile:
    """Read ``omrg.jsonc`` and ``secrets/`` in *directory* (default: the user config folder).

    Nothing is created or changed. A missing folder or file gives no values and
    no warning. A file that cannot be parsed gives no values and one warning. A
    value that breaks its rule is ignored with one warning and a
    :class:`Problem`; the other values stay.
    """
    directory = directory or user_config_dir()
    path = directory / CONFIG_FILE
    key_file = key_files(directory / SECRETS_DIR)
    try:
        raw = path.read_bytes()
    except (FileNotFoundError, NotADirectoryError):
        return SettingsFile(directory, path, key_file=key_file)
    except OSError:
        return _broken(directory, path, UNREADABLE, key_file)
    revision = _revision_of(raw)
    try:
        data = parse_jsonc(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return _broken(directory, path, revision, key_file)
    if not isinstance(data, dict):
        return _broken(directory, path, revision, key_file)
    reader = _Reader(directory)
    reader.read(data)
    return SettingsFile(
        directory,
        path,
        revision,
        "ok",
        reader.values,
        reader.secrets,
        reader.references,
        reader.key_paths,
        key_file,
        tuple(reader.problems),
    )


def load_user_config() -> UserConfig:
    """Read the user config folder as a :class:`~.user_config.UserConfig`. Nothing changes.

    Returns:
        The values from ``omrg.jsonc`` and the key files. A missing folder or
        a broken file gives empty values (a broken file logs one warning).
        A value that breaks its rule is left out; the rest stay.
    """
    parsed = read_settings_file()
    return UserConfig(
        parsed.directory,
        {**parsed.values, **parsed.secrets},
        dict(parsed.key_file),
        dict(parsed.references),
        dict(parsed.key_paths),
    )


# ── The pydantic-settings source ─────────────────────────────────────────


class UserConfigSource(PydanticBaseSettingsSource):
    """Settings source for the non-secret values of ``omrg.jsonc``.

    It sits between the ``.env`` source and the YAML sources, and returns a
    nested mapping like the YAML source, so ``Settings`` deep-merges it. Keys
    that are unknown, invalid or file-only never reach ``Settings``. Key
    fields are not supplied here: ``Settings`` applies their references after
    validation (see ``ProviderSourceMixin``).

    Attributes:
        file: The file as read when the source was built.
    """

    def __init__(self, settings_cls: type[BaseSettings]) -> None:
        super().__init__(settings_cls)
        self.file = read_settings_file()

    def get_field_value(self, field: Any, field_name: str) -> tuple[Any, str, bool]:
        """Return no per-field value; :meth:`__call__` supplies the whole mapping."""
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for path, value in self.file.values.items():
            if path in FILE_ONLY:
                continue
            block, _, leaf = path.rpartition(".")
            if block:
                result.setdefault(block, {})[leaf] = value
            else:
                result[leaf] = value
        return result
