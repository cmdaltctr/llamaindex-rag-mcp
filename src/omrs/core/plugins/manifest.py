"""Constrained external-tool manifests (design D10, spec ``notebook-plugins``).

A manifest is data. It names one external tool, a tested version range, the
capabilities its launch recipe supplies, and two fixed recipes: ``probe`` and
``launch_notebook``. Recipes are argument lists, never shell strings. They may
use only the host substitutions in :data:`SUBSTITUTIONS`. The schema is closed:
an unknown key, a shell construct, an interpreter or import hook, a credential,
or an installation action makes the whole manifest invalid.

This module does no I/O apart from hashing the bytes it receives.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

SCHEMA_VERSION = 1
MAX_MANIFEST_BYTES = 64 * 1024
MAX_ARGS = 32
MAX_ARG_LENGTH = 256

RECIPE_NAMES: frozenset[str] = frozenset({"probe", "launch_notebook"})
SUBSTITUTIONS: frozenset[str] = frozenset({"notebook_path", "host", "port", "token_file"})

# The host refuses a launch unless the manifest declares all of these and the
# installed tool confirms the declared flags (see registration.py).
REQUIRED_LAUNCH_CAPABILITIES: tuple[str, ...] = (
    "loopback_bind",
    "token_auth",
    "startup_execution_disabled",
    "auto_install_disabled",
    "update_check_disabled",
)
# A capability that consumes a host value must use its substitution.
CAPABILITY_SUBSTITUTIONS: Mapping[str, str] = {
    "loopback_bind": "host",
    "token_auth": "token_file",
}

_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
_FILE_RE = re.compile(r"^\.?[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_VERSION_RE = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?(?:\.(\d+))?")
_PLACEHOLDER_RE = re.compile(r"\{([^{}]*)\}")
_SHELL_CHARS = frozenset(";&|$`<>()!*?~\"'\\\n\r\t ")
_CREDENTIAL_WORDS = ("password", "passwd", "secret", "token", "api_key", "apikey", "credential")
_INTERPRETERS = frozenset(
    {
        "sh", "bash", "zsh", "fish", "dash", "ksh", "csh", "tcsh", "cmd", "powershell", "pwsh",
        "python", "python3", "pythonw", "env", "uv", "uvx", "pip", "pip3", "pipx", "conda",
        "mamba", "npm", "npx", "node", "perl", "ruby",
    }
)  # fmt: skip
_FORBIDDEN_TOKENS = frozenset(
    {
        "install", "uninstall", "reinstall", "upgrade", "update", "self-update", "pip", "uv",
        "uvx", "pipx", "-c", "-m", "--command", "exec", "eval", "__import__", "importlib",
    }
)  # fmt: skip
_FORBIDDEN_PREFIXES = ("--upgrade", "--install", "--reinstall", "--force-reinstall")

_TOP_KEYS = frozenset(
    {
        "schema_version", "plugin_id", "plugin_version", "display_name", "description",
        "tool", "capabilities", "recipes",
    }
)  # fmt: skip
_TOOL_KEYS = frozenset({"name", "executable", "tested_versions"})
_RANGE_KEYS = frozenset({"minimum", "below"})
_PROBE_KEYS = frozenset({"version_args", "help_args"})
_LAUNCH_KEYS = frozenset({"args", "config_file"})
_CONFIG_KEYS = frozenset({"name", "values"})
_CAPABILITY_KEYS = frozenset({"argument", "config", "value"})


class ManifestError(ValueError):
    """A manifest is not valid. ``problems`` lists every reason found."""

    def __init__(self, problems: Sequence[str]) -> None:
        self.problems = tuple(problems)
        super().__init__("invalid plugin manifest: " + "; ".join(self.problems))


Version = tuple[int, ...]


def parse_version(text: str) -> Version | None:
    """Return the first dotted version number in ``text``, or ``None``."""
    match = _VERSION_RE.search(text)
    if match is None:
        return None
    return tuple(int(part) for part in match.groups() if part is not None)


def format_version(version: Version) -> str:
    """Return ``version`` as a dotted string."""
    return ".".join(str(part) for part in version)


@dataclass(frozen=True)
class VersionRange:
    """Tested tool versions: ``minimum`` inclusive, ``below`` exclusive."""

    minimum: Version
    below: Version

    def contains(self, version: Version) -> bool:
        """Return whether ``version`` is inside the tested range."""
        return _pad(self.minimum) <= _pad(version) < _pad(self.below)

    def describe(self) -> str:
        """Return the range as text for messages."""
        return f">={format_version(self.minimum)},<{format_version(self.below)}"


@dataclass(frozen=True)
class Capability:
    """A capability and the launch argument or config value that supplies it."""

    name: str
    argument: str | None = None
    config: str | None = None
    value: Any = None


@dataclass(frozen=True)
class ProbeRecipe:
    """Arguments that print the tool version, and optionally its launch help."""

    version_args: tuple[str, ...]
    help_args: tuple[str, ...] | None = None


@dataclass(frozen=True)
class ConfigFile:
    """A tool configuration file the launcher writes into its private directory."""

    name: str
    values: Mapping[str, Mapping[str, Any]]

    def lookup(self, dotted: str) -> tuple[bool, Any]:
        """Return ``(found, value)`` for a ``table.key`` path."""
        table, _, key = dotted.partition(".")
        section = self.values.get(table)
        if not isinstance(section, Mapping) or key not in section:
            return False, None
        return True, section[key]

    def render_toml(self) -> str:
        """Return the values as TOML tables of scalars."""
        lines: list[str] = []
        for table in sorted(self.values):
            lines.append(f"[{table}]")
            for key in sorted(self.values[table]):
                lines.append(f"{key} = {_toml_scalar(self.values[table][key])}")
            lines.append("")
        return "\n".join(lines)


@dataclass(frozen=True)
class LaunchRecipe:
    """Argument templates for ``launch_notebook`` and an optional config file."""

    args: tuple[str, ...]
    config_file: ConfigFile | None = None


@dataclass(frozen=True)
class PluginManifest:
    """A validated external-tool manifest and the SHA-256 of its bytes."""

    schema_version: int
    plugin_id: str
    plugin_version: str
    display_name: str
    tool_name: str
    executable_name: str
    tested_versions: VersionRange
    capabilities: Mapping[str, Capability]
    probe: ProbeRecipe
    launch: LaunchRecipe
    sha256: str
    description: str = ""
    missing_capabilities: tuple[str, ...] = field(default=())


def parse_manifest(raw: bytes) -> PluginManifest:
    """Parse and validate manifest bytes.

    Args:
        raw: The manifest file content (UTF-8 JSON).

    Returns:
        The validated manifest.

    Raises:
        ManifestError: If the bytes are not a valid manifest.
    """
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ManifestError([f"manifest is larger than {MAX_MANIFEST_BYTES} bytes"])
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_no_duplicates)
    except (UnicodeDecodeError, ValueError) as exc:
        raise ManifestError([f"manifest is not valid UTF-8 JSON: {exc}"]) from exc
    problems: list[str] = []
    manifest = _build(data, hashlib.sha256(raw).hexdigest(), problems)
    if problems or manifest is None:
        raise ManifestError(problems or ["manifest could not be read"])
    return manifest


def substitute(args: Sequence[str], values: Mapping[str, str]) -> tuple[str, ...]:
    """Replace host substitutions in validated argument templates.

    Raises:
        KeyError: If a template uses a substitution without a value.
    """
    return tuple(_PLACEHOLDER_RE.sub(lambda m: values[m.group(1)], arg) for arg in args)


# --- validation -----------------------------------------------------------


def _build(data: Any, sha256: str, problems: list[str]) -> PluginManifest | None:
    if not isinstance(data, dict):
        problems.append("manifest must be a JSON object")
        return None
    _closed(data, _TOP_KEYS, "manifest", problems)
    if data.get("schema_version") != SCHEMA_VERSION:
        problems.append(f"schema_version must be {SCHEMA_VERSION}")
    plugin_id = _text(data, "plugin_id", "manifest", problems)
    if plugin_id and not _ID_RE.match(plugin_id):
        problems.append("plugin_id must be lower-case letters, digits, '-' or '_'")
    plugin_version = _text(data, "plugin_version", "manifest", problems)
    display_name = _text(data, "display_name", "manifest", problems)
    tool = _section(data, "tool", "manifest", problems)
    tool_name = _text(tool, "name", "tool", problems)
    recipes = _section(data, "recipes", "manifest", problems)
    _closed(recipes, RECIPE_NAMES, "recipes", problems, noun="recipe")
    for name in sorted(RECIPE_NAMES - set(recipes)):
        problems.append(f"recipes.{name} is required")
    probe = _probe(_section(recipes, "probe", "recipes", problems, required=False), problems)
    launch = _launch(_section(recipes, "launch_notebook", "recipes", problems, False), problems)
    tested = _range(tool, problems)
    executable = _executable(tool, problems)
    capabilities = _capabilities(data.get("capabilities", {}), launch, problems)
    if problems or tested is None:
        return None
    return PluginManifest(
        schema_version=SCHEMA_VERSION,
        plugin_id=plugin_id,
        plugin_version=plugin_version,
        display_name=display_name,
        tool_name=tool_name,
        executable_name=executable,
        tested_versions=tested,
        capabilities=capabilities,
        probe=probe,
        launch=launch,
        sha256=sha256,
        description=str(data.get("description", "")),
        missing_capabilities=tuple(
            name for name in REQUIRED_LAUNCH_CAPABILITIES if name not in capabilities
        ),
    )


def _executable(tool: Mapping[str, Any], problems: list[str]) -> str:
    _closed(tool, _TOOL_KEYS, "tool", problems)
    name = _text(tool, "executable", "tool", problems)
    if "/" in name or "\\" in name:
        problems.append("tool.executable must be a command name, not a path or interpreter hook")
    elif name.lower().removesuffix(".exe") in _INTERPRETERS or name.startswith("python"):
        problems.append(f"tool.executable {name!r} is an interpreter or installer")
    return name


def _range(tool: Mapping[str, Any], problems: list[str]) -> VersionRange | None:
    raw = _section(tool, "tested_versions", "tool", problems)
    _closed(raw, _RANGE_KEYS, "tool.tested_versions", problems)
    bounds = [parse_version(str(raw.get(key, ""))) for key in ("minimum", "below")]
    if bounds[0] is None or bounds[1] is None:
        problems.append("tool.tested_versions needs 'minimum' and 'below' versions")
        return None
    tested = VersionRange(bounds[0], bounds[1])
    if _pad(tested.minimum) >= _pad(tested.below):
        problems.append("tool.tested_versions.minimum must be below 'below'")
    return tested


def _probe(raw: Mapping[str, Any], problems: list[str]) -> ProbeRecipe:
    _closed(raw, _PROBE_KEYS, "recipes.probe", problems)
    version_args = _args(raw.get("version_args"), "recipes.probe.version_args", (), problems)
    help_args = None
    if "help_args" in raw:
        help_args = _args(raw["help_args"], "recipes.probe.help_args", (), problems)
    return ProbeRecipe(version_args, help_args)


def _launch(raw: Mapping[str, Any], problems: list[str]) -> LaunchRecipe:
    _closed(raw, _LAUNCH_KEYS, "recipes.launch_notebook", problems)
    where = "recipes.launch_notebook.args"
    args = _args(raw.get("args"), where, SUBSTITUTIONS, problems)
    for name in ("notebook_path", "host", "port"):
        if not any(f"{{{name}}}" in arg for arg in args):
            problems.append(f"{where} must use {{{name}}}")
    config = None
    if "config_file" in raw:
        config = _config_file(raw["config_file"], problems)
    return LaunchRecipe(args, config)


def _config_file(raw: Any, problems: list[str]) -> ConfigFile | None:
    where = "recipes.launch_notebook.config_file"
    if not isinstance(raw, dict):
        problems.append(f"{where} must be an object")
        return None
    _closed(raw, _CONFIG_KEYS, where, problems)
    name = str(raw.get("name", ""))
    if not _FILE_RE.match(name) or ".." in name:
        problems.append(f"{where}.name must be a plain file name")
    values = raw.get("values")
    if not isinstance(values, dict) or not values:
        problems.append(f"{where}.values must be a non-empty object of tables")
        return None
    for table, section in values.items():
        if not _KEY_RE.match(table) or not isinstance(section, dict):
            problems.append(f"{where}.values.{table} must be a table of scalars")
            continue
        for key, value in section.items():
            _config_value(f"{where}.values.{table}.{key}", key, value, problems)
    return ConfigFile(name, values)


def _config_value(where: str, key: str, value: Any, problems: list[str]) -> None:
    if not _KEY_RE.match(key):
        problems.append(f"{where}: key is not a plain name")
    if any(word in key.lower() for word in _CREDENTIAL_WORDS):
        problems.append(f"{where}: manifests must not carry credentials")
    if isinstance(value, str):
        if "{" in value or "}" in value or "\n" in value or len(value) > MAX_ARG_LENGTH:
            problems.append(f"{where}: string values must be short literals")
    elif not isinstance(value, bool | int | float):
        problems.append(f"{where}: values must be strings, numbers or booleans")


def _capabilities(raw: Any, launch: LaunchRecipe, problems: list[str]) -> dict[str, Capability]:
    if not isinstance(raw, dict):
        problems.append("capabilities must be an object")
        return {}
    result: dict[str, Capability] = {}
    for name, spec in raw.items():
        where = f"capabilities.{name}"
        if not _ID_RE.match(name) or not isinstance(spec, dict):
            problems.append(f"{where} must be an object with a plain name")
            continue
        _closed(spec, _CAPABILITY_KEYS, where, problems)
        cap = Capability(name, spec.get("argument"), spec.get("config"), spec.get("value"))
        if (cap.argument is None) == (cap.config is None):
            problems.append(f"{where} needs exactly one of 'argument' or 'config'")
        elif cap.argument is not None and cap.argument not in launch.args:
            problems.append(f"{where}: argument {cap.argument!r} is not in the launch recipe")
        elif cap.config is not None:
            config = launch.config_file
            found, value = config.lookup(cap.config) if config else (False, None)
            if not found or value != cap.value:
                problems.append(f"{where}: config {cap.config!r} must be set to {cap.value!r}")
        token = CAPABILITY_SUBSTITUTIONS.get(name)
        if token and not any(f"{{{token}}}" in arg for arg in launch.args):
            problems.append(f"{where} requires the launch recipe to use {{{token}}}")
        result[name] = cap
    return result


def _args(
    raw: Any, where: str, allowed: frozenset[str] | tuple[()], problems: list[str]
) -> tuple[str, ...]:
    if not isinstance(raw, list) or not raw:
        problems.append(f"{where} must be a non-empty list of arguments, not a shell string")
        return ()
    if len(raw) > MAX_ARGS:
        problems.append(f"{where} has more than {MAX_ARGS} arguments")
    args: list[str] = []
    for index, arg in enumerate(raw):
        if not isinstance(arg, str) or not arg or len(arg) > MAX_ARG_LENGTH:
            problems.append(f"{where}[{index}] must be a short non-empty string")
            continue
        _check_arg(f"{where}[{index}]", arg, allowed, problems)
        args.append(arg)
    for index, arg in enumerate(args[:-1]):
        if _is_secret_flag(arg) and not _PLACEHOLDER_RE.search(args[index + 1]):
            problems.append(f"{where}: {arg} must take a substitution, not a literal credential")
    return tuple(args)


def _check_arg(where: str, arg: str, allowed: Any, problems: list[str]) -> None:
    if _SHELL_CHARS.intersection(arg):
        problems.append(f"{where}: shell syntax or whitespace is not allowed ({arg!r})")
    lowered = arg.lower()
    if lowered in _FORBIDDEN_TOKENS or lowered.startswith(_FORBIDDEN_PREFIXES):
        problems.append(f"{where}: installer, interpreter or import hooks are not allowed")
    names = _PLACEHOLDER_RE.findall(arg)
    for name in names:
        if name not in allowed:
            problems.append(f"{where}: unknown substitution {{{name}}}")
    if "{" in _PLACEHOLDER_RE.sub("", arg) or "}" in _PLACEHOLDER_RE.sub("", arg):
        problems.append(f"{where}: unbalanced braces")
    if "=" in arg and not names:
        left = lowered.partition("=")[0]
        if any(word in left for word in _CREDENTIAL_WORDS):
            problems.append(f"{where}: manifests must not carry credentials")


def _is_secret_flag(arg: str) -> bool:
    lowered = arg.lower()
    return lowered.startswith("-") and any(w in lowered for w in ("password", "secret", "api"))


def _closed(
    raw: Mapping[str, Any],
    allowed: frozenset[str],
    where: str,
    problems: list[str],
    *,
    noun: str = "key",
) -> None:
    for key in sorted(set(raw) - allowed):
        problems.append(f"{where}: unsupported {noun} {key!r}")


def _section(
    raw: Mapping[str, Any], key: str, where: str, problems: list[str], required: bool = True
) -> Mapping[str, Any]:
    value = raw.get(key)
    if isinstance(value, dict):
        return value
    if required or value is not None:
        problems.append(f"{where}.{key} must be an object")
    return {}


def _text(raw: Mapping[str, Any], key: str, where: str, problems: list[str]) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        problems.append(f"{where}.{key} must be a non-empty string")
        return ""
    return value


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key {key!r}")
        result[key] = value
    return result


def _pad(version: Version) -> Version:
    return tuple(version) + (0,) * (4 - len(version))


def _toml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return repr(value)
    return json.dumps(value)  # a JSON string is a valid TOML basic string here
