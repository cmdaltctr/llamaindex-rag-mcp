"""Manifest validation for external-tool plugins (task 8.1, spec notebook-plugins)."""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest

from omrs.core.plugins.manifest import (
    REQUIRED_LAUNCH_CAPABILITIES,
    ManifestError,
    parse_manifest,
    parse_version,
    substitute,
)


def valid_manifest() -> dict[str, Any]:
    """Return a minimal valid manifest dictionary."""
    return {
        "schema_version": 1,
        "plugin_id": "fakeedit",
        "plugin_version": "0.1.0",
        "display_name": "Fake editor",
        "tool": {
            "name": "fakeedit",
            "executable": "fakeedit",
            "tested_versions": {"minimum": "1.2.0", "below": "2.0.0"},
        },
        "capabilities": {
            "loopback_bind": {"argument": "--host"},
            "token_auth": {"argument": "--token-password-file"},
            "update_check_disabled": {"argument": "--skip-update-check"},
            "auto_install_disabled": {"argument": "--no-sandbox"},
            "startup_execution_disabled": {"config": "runtime.auto_instantiate", "value": False},
        },
        "recipes": {
            "probe": {"version_args": ["--version"], "help_args": ["edit", "--help"]},
            "launch_notebook": {
                "args": [
                    "edit",
                    "{notebook_path}",
                    "--headless",
                    "--host",
                    "{host}",
                    "--port={port}",
                    "--token-password-file",
                    "{token_file}",
                    "--skip-update-check",
                    "--no-sandbox",
                ],
                "config_file": {
                    "name": ".fakeedit.toml",
                    "values": {"runtime": {"auto_instantiate": False, "on_cell_change": "lazy"}},
                },
            },
        },
    }


def encode(data: dict[str, Any]) -> bytes:
    return json.dumps(data).encode("utf-8")


def problems_for(data: dict[str, Any]) -> str:
    with pytest.raises(ManifestError) as caught:
        parse_manifest(encode(data))
    return " | ".join(caught.value.problems)


def test_valid_manifest_parses_with_hash_and_capabilities() -> None:
    raw = encode(valid_manifest())
    manifest = parse_manifest(raw)
    assert manifest.plugin_id == "fakeedit"
    assert len(manifest.sha256) == 64
    assert manifest.missing_capabilities == ()
    assert set(REQUIRED_LAUNCH_CAPABILITIES) <= set(manifest.capabilities)
    assert manifest.tested_versions.contains((1, 2, 0))
    assert manifest.tested_versions.contains((1, 9, 9))
    assert not manifest.tested_versions.contains((2, 0))
    assert not manifest.tested_versions.contains((1, 1, 9))


def test_hash_changes_with_any_byte() -> None:
    first = parse_manifest(encode(valid_manifest()))
    changed = valid_manifest()
    changed["description"] = "x"
    assert parse_manifest(encode(changed)).sha256 != first.sha256


def test_substitute_fills_only_host_values() -> None:
    manifest = parse_manifest(encode(valid_manifest()))
    argv = substitute(
        manifest.launch.args,
        {"notebook_path": "/n.py", "host": "127.0.0.1", "port": "4000", "token_file": "/t"},
    )
    assert "--port=4000" in argv and "/n.py" in argv and "/t" in argv
    assert not any("{" in arg for arg in argv)


def test_config_file_renders_toml() -> None:
    config = parse_manifest(encode(valid_manifest())).launch.config_file
    assert config is not None
    text = config.render_toml()
    assert "[runtime]" in text
    assert "auto_instantiate = false" in text
    assert 'on_cell_change = "lazy"' in text


@pytest.mark.parametrize(
    ("text", "expected"),
    [("0.25.1", (0, 25, 1)), ("marimo, version 1.2", (1, 2)), ("v3.4.5.6\n", (3, 4, 5, 6))],
)
def test_parse_version(text: str, expected: tuple[int, ...]) -> None:
    assert parse_version(text) == expected


def test_parse_version_without_number() -> None:
    assert parse_version("unknown") is None


def _mutate(path: list[str], value: Any) -> dict[str, Any]:
    data = copy.deepcopy(valid_manifest())
    target = data
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    return data


LAUNCH = ["recipes", "launch_notebook", "args"]


@pytest.mark.parametrize(
    ("path", "value", "fragment"),
    [
        # Shell strings and shell syntax.
        (LAUNCH, "edit {notebook_path} --host {host}", "not a shell string"),
        (["recipes", "probe", "version_args"], ["--version;rm"], "shell syntax"),
        (LAUNCH, ["edit", "{notebook_path}", "{host}", "{port}", "$(id)"], "shell syntax"),
        # Unknown and malformed substitutions.
        (LAUNCH, ["edit", "{notebook_path}", "{host}", "{port}", "{home}"], "unknown substitution"),
        (LAUNCH, ["edit", "{notebook_path}", "{host}", "{port}", "{executable}"], "unknown"),
        (["recipes", "probe", "version_args"], ["{port}"], "unknown substitution"),
        (LAUNCH, ["edit", "{notebook_path}", "{host}", "{port}", "x}"], "unbalanced"),
        (LAUNCH, ["edit", "{host}", "{port}"], "must use {notebook_path}"),
        # Interpreter and import hooks.
        (["tool", "executable"], "/usr/bin/python3", "not a path"),
        (["tool", "executable"], "python3.12", "interpreter"),
        (["tool", "executable"], "bash", "interpreter"),
        (["recipes", "probe", "version_args"], ["-c", "import_os"], "import hooks"),
        (["recipes", "probe", "version_args"], ["-m", "marimo"], "import hooks"),
        # Installation actions.
        (["recipes", "probe", "version_args"], ["install"], "installer"),
        (["recipes", "probe", "version_args"], ["--upgrade-all"], "installer"),
        (["recipes", "install"], {"args": ["pip"]}, "unsupported recipe 'install'"),
        (["install"], ["uv", "tool", "install", "marimo"], "unsupported key 'install'"),
        # Credentials.
        (LAUNCH, ["edit", "{notebook_path}", "{host}", "{port}", "--token=abc"],
         "credentials"),
        (LAUNCH, ["edit", "{notebook_path}", "{host}", "{port}", "--token-password", "hunter2"],
         "literal credential"),
        (["recipes", "launch_notebook", "config_file", "values"],
         {"ai": {"api_key": "sk-x"}}, "credentials"),
        # Unknown keys and fixed recipe set.
        (["recipes", "launch_notebook", "env"], {"A": "1"}, "unsupported key 'env'"),
        (["hooks"], {"pre_launch": "x"}, "unsupported key 'hooks'"),
        (["recipes", "run_app"], {"args": ["run"]}, "unsupported recipe 'run_app'"),
        # Schema and version range.
        (["schema_version"], 2, "schema_version"),
        (["tool", "tested_versions"], {"minimum": "2.0", "below": "1.0"}, "must be below"),
        (["tool", "tested_versions"], {"minimum": "1.0"}, "'minimum' and 'below'"),
        (["recipes", "launch_notebook", "config_file", "name"], "../escape.toml", "plain file"),
        (["recipes", "launch_notebook", "config_file", "values"],
         {"runtime": {"auto_instantiate": "{host}"}}, "short literals"),
        # A declared capability must be backed by the recipe.
        (["capabilities", "update_check_disabled"], {"argument": "--quiet"}, "not in the launch"),
        (["capabilities", "startup_execution_disabled"],
         {"config": "runtime.auto_instantiate", "value": True}, "must be set to True"),
    ],
)  # fmt: skip
def test_rejects_unsafe_or_malformed_manifests(path: list[str], value: Any, fragment: str) -> None:
    assert fragment in problems_for(_mutate(path, value))


def test_missing_recipe_is_reported() -> None:
    data = valid_manifest()
    del data["recipes"]["probe"]
    assert "recipes.probe is required" in problems_for(data)


def test_token_capability_requires_token_substitution() -> None:
    data = valid_manifest()
    args = data["recipes"]["launch_notebook"]["args"]
    args[args.index("{token_file}")] = "{port}"
    assert "requires the launch recipe to use {token_file}" in problems_for(data)


def test_duplicate_keys_and_bad_json_are_rejected() -> None:
    with pytest.raises(ManifestError, match="duplicate key"):
        parse_manifest(b'{"plugin_id": "a", "plugin_id": "b"}')
    with pytest.raises(ManifestError, match="not valid UTF-8 JSON"):
        parse_manifest(b"\xff")
    with pytest.raises(ManifestError, match="JSON object"):
        parse_manifest(b"[]")


def test_oversized_manifest_is_rejected() -> None:
    with pytest.raises(ManifestError, match="larger than"):
        parse_manifest(b" " * (64 * 1024 + 1))


def test_missing_required_capability_is_recorded_not_hidden() -> None:
    data = valid_manifest()
    del data["capabilities"]["token_auth"]
    manifest = parse_manifest(encode(data))
    assert manifest.missing_capabilities == ("token_auth",)


CONFIG = ["recipes", "launch_notebook", "config_file"]


@pytest.mark.parametrize(
    ("path", "value", "fragment"),
    [
        (CONFIG, "x.toml", "must be an object"),
        (CONFIG + ["values"], {}, "non-empty object of tables"),
        (CONFIG + ["values"], {"runtime": 3}, "table of scalars"),
        (CONFIG + ["values"], {"runtime": {"bad key": 1}}, "not a plain name"),
        (CONFIG + ["values"], {"runtime": {"limit": [1]}}, "strings, numbers or booleans"),
        (["capabilities"], [], "capabilities must be an object"),
        (["capabilities", "headless"], "--headless", "must be an object"),
        (["capabilities", "headless"], {"argument": "--headless", "config": "a.b"}, "exactly one"),
        (LAUNCH, ["edit", "{notebook_path}", "{host}", "{port}", *["-v"] * 40], "more than 32"),
        (LAUNCH, ["edit", "{notebook_path}", "{host}", "{port}", 5], "short non-empty string"),
        (["tool"], "marimo", "manifest.tool must be an object"),
        (["recipes", "probe"], "--version", "recipes.probe must be an object"),
        (["plugin_id"], "Bad Id", "plugin_id must be lower-case"),
        (["display_name"], "", "display_name must be a non-empty string"),
    ],
)  # fmt: skip
def test_rejects_malformed_sections(path: list[str], value: Any, fragment: str) -> None:
    assert fragment in problems_for(_mutate(path, value))


def test_numeric_config_values_render() -> None:
    data = valid_manifest()
    data["recipes"]["launch_notebook"]["config_file"]["values"]["runtime"]["limit"] = 3
    config = parse_manifest(encode(data)).launch.config_file
    assert config is not None and "limit = 3" in config.render_toml()
    assert config.lookup("missing.key") == (False, None)
