"""``omrs config init`` (move-settings-to-config-file, tasks 8.1 and 8.2).

Every case runs in a temporary config folder named by ``OMRS_CONFIG_DIR``.
No test reads or writes the real ``~/.config/omrs``.
"""

from __future__ import annotations

import re
import stat
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel
from typer.testing import CliRunner

from omrs.config import Settings, rules
from omrs.config.user_config import parse_jsonc
from omrs.transports.cli import app as cli_app
from omrs.transports.cli import config_template as template

runner = CliRunner()

#: A line the template comments out: a setting, a block opener or a closer.
_COMMENTED_CODE = re.compile(r'^(\s*)// ?(\s*(?:"[^"]+": .*|\},?))$')


def flat(text: str) -> str:
    """Collapse whitespace, so a wrapped terminal line still matches."""
    return " ".join(text.split())


@pytest.fixture
def config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path / "cfg" / "omrs"
    monkeypatch.setenv("OMRS_CONFIG_DIR", str(folder))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    return folder


def _init(*args: str) -> Any:
    return runner.invoke(cli_app, ["config", "init", *args])


def _uncomment(text: str) -> str:
    """Remove the comment mark from every commented setting line."""
    lines = []
    for line in text.splitlines():
        match = _COMMENTED_CODE.match(line)
        lines.append(f"{match.group(1)}{match.group(2)}" if match else line)
    return "\n".join(lines)


def _is_block(annotation: object) -> bool:
    return isinstance(annotation, type) and issubclass(annotation, BaseModel)


def _expected_keys() -> set[str]:
    """Every file key the template must offer, derived from the model."""
    keys: set[str] = set()
    for name, field in Settings.model_fields.items():
        if name in template.INTERNAL_FIELDS:
            continue
        if _is_block(field.annotation):
            keys.update(f"{name}.{leaf}" for leaf in field.annotation.model_fields)  # type: ignore[union-attr]
        else:
            keys.add(name)
    return keys | set(template.FILE_ONLY)


def _flatten(data: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, dict):
            out.update(_flatten(value, f"{prefix}{key}."))
        else:
            out[f"{prefix}{key}"] = value
    return out


# ── The template ─────────────────────────────────────────────────────────


def test_template_parses_and_sets_nothing() -> None:
    assert parse_jsonc(template.build_template()) == {}


def test_template_covers_every_settings_field() -> None:
    """Uncommenting every line must give exactly the model's keys, so it cannot drift."""
    offered = _flatten(parse_jsonc(_uncomment(template.build_template())))

    assert set(offered) == _expected_keys()


def test_internal_field_list_names_only_real_fields() -> None:
    """A stale entry hides a renamed field from the template."""
    assert template.INTERNAL_FIELDS <= set(Settings.model_fields)


def test_file_only_keys_match_the_reader() -> None:
    """The template offers exactly the file-only keys the file reader accepts."""
    assert set(template.FILE_ONLY) == set(rules.FILE_ONLY)


def test_template_values_are_the_defaults() -> None:
    offered = _flatten(parse_jsonc(_uncomment(template.build_template())))

    assert offered["retrieval.top_k"] == 10
    assert offered["chunking.chunk_overlap"] == 100
    assert offered["embed_provider"] == "local"
    assert offered["web_port"] == 8765
    assert offered["web_max_upload_mib"] == 50
    assert offered["mcp_http_enabled"] is False
    assert offered["liteparse_num_workers"] is None


def test_defaults_yaml_overrides_the_model_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        template,
        "_yaml_defaults",
        lambda: {"retrieval": {"top_k": 99}, "pdf_reader": "pypdf"},
    )

    offered = _flatten(parse_jsonc(_uncomment(template.build_template())))

    assert offered["retrieval.top_k"] == 99
    assert offered["pdf_reader"] == "pypdf"
    assert offered["retrieval.rerank_model"] == "cross-encoder/ms-marco-MiniLM-L-6-v2"


def test_every_setting_shows_its_environment_name() -> None:
    text = template.build_template()

    assert "RETRIEVAL__TOP_K" in text
    assert "EMBED_PROVIDER" in text
    assert "ANSWER__MODEL" in text
    assert "WEB_MAX_UPLOAD_MIB" in text


def test_file_only_keys_name_no_environment_variable() -> None:
    text = template.build_template()

    assert "WEB_PORT" not in text
    assert "MCP_HTTP_ENABLED" not in text


def test_every_line_is_a_comment_apart_from_the_outer_braces() -> None:
    lines = [line for line in template.build_template().splitlines() if line.strip()]
    code = [line for line in lines if not line.lstrip().startswith("//")]

    assert code == ["{", "}"]


def test_key_fields_offer_a_reference_never_a_key() -> None:
    text = template.build_template()

    assert '// "openrouter_api_key": "env://OPENROUTER_API_KEY",' in text
    assert "env://" in text
    assert "keychain://" in text
    assert '"openrouter_api_key": ""' not in text


# ── The command ──────────────────────────────────────────────────────────


def test_init_writes_the_file_in_the_config_folder(config_dir: Path) -> None:
    result = _init()

    target = config_dir / "omrs.jsonc"
    assert result.exit_code == 0, result.output
    assert parse_jsonc(target.read_text(encoding="utf-8")) == {}
    assert "omrs.jsonc" in flat(result.output)


def test_init_uses_modes_0700_and_0600(config_dir: Path) -> None:
    _init()

    assert stat.S_IMODE(config_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE((config_dir / "omrs.jsonc").stat().st_mode) == 0o600


def test_init_writes_nothing_to_stdout(config_dir: Path) -> None:
    result = runner.invoke(cli_app, ["config", "init"])

    assert result.exit_code == 0
    assert result.stdout == ""
    assert result.stderr != ""


def test_init_refuses_an_existing_file(config_dir: Path) -> None:
    config_dir.mkdir(parents=True)
    target = config_dir / "omrs.jsonc"
    target.write_text('{ "retrieval": { "top_k": 3 } }\n', encoding="utf-8")

    result = _init()

    assert result.exit_code == 1
    assert "omrs.jsonc" in flat(result.output)
    assert "--force" in flat(result.output)
    assert target.read_text(encoding="utf-8") == '{ "retrieval": { "top_k": 3 } }\n'
    assert sorted(path.name for path in config_dir.iterdir()) == ["omrs.jsonc"]


def test_force_keeps_a_dated_copy_and_replaces_the_file(
    config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir.mkdir(parents=True)
    target = config_dir / "omrs.jsonc"
    target.write_text('{ "retrieval": { "top_k": 3 } }\n', encoding="utf-8")
    target.chmod(0o640)
    monkeypatch.setattr(template, "today", lambda: "2026-10-19")

    result = _init("--force")

    backup = config_dir / "omrs.jsonc.2026-10-19.bak"
    assert result.exit_code == 0, result.output
    assert backup.read_text(encoding="utf-8") == '{ "retrieval": { "top_k": 3 } }\n'
    assert parse_jsonc(target.read_text(encoding="utf-8")) == {}
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert "omrs.jsonc.2026-10-19.bak" in flat(result.output)


def test_force_does_not_overwrite_an_earlier_copy(
    config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir.mkdir(parents=True)
    (config_dir / "omrs.jsonc").write_text("second\n", encoding="utf-8")
    first = config_dir / "omrs.jsonc.2026-10-19.bak"
    first.write_text("first\n", encoding="utf-8")
    monkeypatch.setattr(template, "today", lambda: "2026-10-19")

    result = _init("--force")

    assert result.exit_code == 0, result.output
    assert first.read_text(encoding="utf-8") == "first\n"
    copies = sorted(path.name for path in config_dir.glob("omrs.jsonc.*.bak*"))
    assert len(copies) == 2


def test_force_on_a_new_file_makes_no_copy(config_dir: Path) -> None:
    result = _init("--force")

    assert result.exit_code == 0, result.output
    assert sorted(path.name for path in config_dir.iterdir()) == ["omrs.jsonc"]


def test_init_follows_xdg_config_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OMRS_CONFIG_DIR", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    result = _init()

    assert result.exit_code == 0, result.output
    assert (tmp_path / "xdg" / "omrs" / "omrs.jsonc").is_file()


def test_the_config_group_lists_init() -> None:
    result = runner.invoke(cli_app, ["config", "--help"])

    assert result.exit_code == 0
    assert "init" in result.output
