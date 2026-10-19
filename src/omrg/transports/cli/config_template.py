"""Starter ``omrg.jsonc`` text for ``omrg config init``.

The template comes from the ``Settings`` model and ``config/defaults.yaml``,
so it cannot drift from the settings the program reads. A file key is the
environment name in lower case, and ``__`` nests one level (design D2).
Every setting is a commented line, so the file sets nothing until the user
removes a comment mark.
"""

from __future__ import annotations

import datetime
import json
from importlib.resources import files
from typing import Any

import yaml
from pydantic import BaseModel

from ...config import Settings
from ...config.rules import INTERNAL_FIELDS, SECRET_FIELDS
from ..api.uploads import DEFAULT_MAX_UPLOAD_BYTES, MIB
from .web import DEFAULT_PORT

#: Settings that live only in the file, with their default and the
#: environment name that also sets them (``None`` when there is none).
#: The keys must equal ``config.rules.FILE_ONLY``; a test pins that.
FILE_ONLY: dict[str, tuple[Any, str | None]] = {
    "web_port": (DEFAULT_PORT, None),
    "web_max_upload_mib": (DEFAULT_MAX_UPLOAD_BYTES // MIB, "WEB_MAX_UPLOAD_MIB"),
    "mcp_http_enabled": (False, None),
}

_HEADER = """\
// omrg.jsonc: settings for OMRG.
//
// Every setting below is commented out, so this file sets nothing yet.
// To change a setting, remove the leading // from its line. For a setting
// inside a block, also remove the // from the block line and its closing brace.
//
// A key is the environment name in lower case. "__" nests one level:
// RETRIEVAL__TOP_K is "top_k" inside "retrieval".
// The process environment and a .env file override this file.
//
// Never write an API key here. Write a reference:
//   env://NAME                          read the environment variable NAME
//   file://~/.config/omrg/secrets/NAME.key   read a key file inside secrets/
//   keychain://PROVIDER                 read the system keychain"""


def today() -> str:
    """Return today's date as ``YYYY-MM-DD`` for the backup file name."""
    return datetime.date.today().isoformat()


def _yaml_defaults() -> dict[str, Any]:
    """Return ``config/defaults.yaml`` with top-level keys in lower case."""
    try:
        with (files("omrg.config") / "defaults.yaml").open("r") as handle:
            data = yaml.safe_load(handle)
    except (FileNotFoundError, ModuleNotFoundError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(key).lower(): value for key, value in data.items()}


def _is_block(annotation: object) -> bool:
    return isinstance(annotation, type) and issubclass(annotation, BaseModel)


def _json(value: Any) -> str:
    return json.dumps(list(value) if isinstance(value, tuple) else value)


def _setting_lines(
    key: str, value: Any, env_name: str | None, *, indent: str, secret: bool
) -> list[str]:
    """Return the two comment lines for one setting."""
    env = f"Environment name: {env_name}." if env_name else "File only: no environment name."
    if secret:
        shown = f"env://{env_name}" if env_name else "env://NAME"
        note = f"{env} Write a reference, never a key."
        return [f"{indent}// {note}", f'{indent}// "{key}": {_json(shown)},']
    default = "unset" if value is None else _json(value)
    return [f"{indent}// {env} Default: {default}.", f'{indent}// "{key}": {_json(value)},']


def _flat_section(yaml_data: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for name, field in Settings.model_fields.items():
        if name in INTERNAL_FIELDS or _is_block(field.annotation):
            continue
        value = yaml_data.get(name, field.default)
        lines += _setting_lines(
            name, value, name.upper(), indent="  ", secret=name in SECRET_FIELDS
        )
        lines.append("")
    return lines


def _block_section(yaml_data: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for name, field in Settings.model_fields.items():
        if not _is_block(field.annotation):
            continue
        block_yaml = yaml_data.get(name)
        block_yaml = block_yaml if isinstance(block_yaml, dict) else {}
        lines.append(f'  // "{name}": {{')
        for leaf, leaf_field in field.annotation.model_fields.items():  # type: ignore[union-attr]
            value = block_yaml.get(leaf, leaf_field.default)
            lines += _setting_lines(
                leaf, value, f"{name.upper()}__{leaf.upper()}", indent="    ", secret=False
            )
        lines += ["  // },", ""]
    return lines


def _file_only_section() -> list[str]:
    lines: list[str] = []
    for key, (value, env_name) in FILE_ONLY.items():
        lines += _setting_lines(key, value, env_name, indent="  ", secret=False)
        lines.append("")
    return lines


def build_template() -> str:
    """Return the text of a starter ``omrg.jsonc``.

    The outer braces are the only lines that are not comments, so the text
    parses as an empty object.
    """
    yaml_data = _yaml_defaults()
    body = [*_flat_section(yaml_data), *_block_section(yaml_data), *_file_only_section()]
    while body and body[-1] == "":
        body.pop()
    return "\n".join([_HEADER, "{", *body, "}", ""])
