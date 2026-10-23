"""``omrs.jsonc`` accepts every setting (move-settings-to-config-file, tasks 2.1 to 2.4).

Every test points ``OMRS_CONFIG_DIR`` at a temporary folder. No test reads the
real ``~/.config/omrs``. Keys and addresses here are fake constants.
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

import pytest

from omrs.config import Settings, provenance
from omrs.config.settings_file import (
    KIND_BROKEN,
    KIND_INVALID,
    KIND_RETIRED,
    KIND_UNKNOWN,
    UserConfigSource,
    read_settings_file,
)

#: Variables that conftest or the host may set and that these tests care about.
VARIABLES = (
    "RETRIEVAL__TOP_K",
    "RETRIEVAL__RERANK_ENABLED",
    "EMBED_PROVIDER",
    "LOCAL_BACKEND",
    "COMMUNITY_SEED",
    "LLAMACPP_CHAT_URL",
    "OLLAMA_BASE_URL",
    "RAG_PROFILE",
    "ANSWER__MODEL",
    "ANSWER__PROVIDER",
    "METADATA__CLASSIFY_MAX_ATTEMPTS",
)


@pytest.fixture(autouse=True)
def folder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    for variable in VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setattr(provenance, "DOTENV_KEYS", frozenset())  # a repo .env must not leak in
    root = tmp_path / "omrs-config"
    root.mkdir(mode=0o700)
    monkeypatch.setenv("OMRS_CONFIG_DIR", str(root))
    return root


def write_config(root: Path, text: str) -> Path:
    path = root / "omrs.jsonc"
    path.write_text(text, encoding="utf-8")
    return path


def build(tmp_path: Path, dotenv: str = "") -> Settings:
    env_file = tmp_path / "test.env"
    env_file.write_text(dotenv, encoding="utf-8")
    return Settings(_env_file=env_file)


def source_of(settings: Settings, path: str) -> str:
    return settings.setting_sources.get(path, "default")


def warnings_of(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]


# ── Naming rule (task 2.1) ───────────────────────────────────────────────


def test_nested_key_sets_the_nested_setting(folder: Path, tmp_path: Path) -> None:
    write_config(folder, '{ "retrieval": { "top_k": 7 } }')
    settings = build(tmp_path)
    assert settings.retrieval.top_k == 7
    assert source_of(settings, "retrieval.top_k") == "config-file"


def test_flat_key_sets_the_flat_setting(folder: Path, tmp_path: Path) -> None:
    write_config(folder, '{ "embed_provider": "local", "local_backend": "ollama" }')
    settings = build(tmp_path)
    assert (settings.embed_provider, settings.local_backend) == ("local", "ollama")
    assert source_of(settings, "local_backend") == "config-file"
    assert settings.config_file_fields >= {"embed_provider", "local_backend"}


def test_comments_and_trailing_commas_are_read(folder: Path, tmp_path: Path) -> None:
    write_config(
        folder,
        """// header
        {
          /* block */
          "community_seed": 5, // note
          "retrieval": { "top_k": 6, },
        }""",
    )
    settings = build(tmp_path)
    assert (settings.community_seed, settings.retrieval.top_k) == (5, 6)


def test_nested_block_is_deep_merged_with_lower_sources(folder: Path, tmp_path: Path) -> None:
    write_config(folder, '{ "retrieval": { "top_k": 7 } }')
    settings = build(tmp_path)
    # rerank_enabled comes from the documents profile bundle, not from the file.
    assert settings.retrieval.rerank_enabled is True
    assert source_of(settings, "retrieval.rerank_enabled") == "yaml"


def test_profile_named_in_the_file_selects_its_bundle(folder: Path, tmp_path: Path) -> None:
    write_config(folder, '{ "rag_profile": "codebase" }')
    settings = build(tmp_path)
    assert settings.rag_profile == "codebase"
    assert settings.retrieval.top_k == 20  # codebase.yaml


def test_file_only_keys_are_not_settings_fields(folder: Path, tmp_path: Path) -> None:
    write_config(
        folder, '{ "web_port": 9100, "web_max_upload_mib": 200, "mcp_http_enabled": true }'
    )
    settings = build(tmp_path)
    assert not hasattr(settings, "web_port")
    parsed = read_settings_file()
    assert parsed.values["web_port"] == 9100
    assert parsed.values["web_max_upload_mib"] == 200
    assert parsed.values["mcp_http_enabled"] is True
    assert parsed.problems == ()


# ── Source order (task 2.1) ──────────────────────────────────────────────


def test_source_order_env_dotenv_file_yaml_default(
    folder: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plain = build(tmp_path)
    assert plain.retrieval.top_k == 10
    assert source_of(plain, "retrieval.top_k") == "yaml"
    assert source_of(plain, "community_seed") == "default"

    write_config(folder, '{ "retrieval": { "top_k": 7 } }')
    assert (build(tmp_path).retrieval.top_k, source_of(build(tmp_path), "retrieval.top_k")) == (
        7,
        "config-file",
    )

    dotenv = build(tmp_path, "RETRIEVAL__TOP_K=12\n")
    assert dotenv.retrieval.top_k == 12
    assert source_of(dotenv, "retrieval.top_k") == "dotenv"

    monkeypatch.setenv("RETRIEVAL__TOP_K", "15")
    env = build(tmp_path, "RETRIEVAL__TOP_K=12\n")
    assert env.retrieval.top_k == 15
    assert source_of(env, "retrieval.top_k") == "env"


def test_file_value_does_not_enter_provider_explicit(folder: Path, tmp_path: Path) -> None:
    write_config(folder, '{ "ollama_base_url": "http://from-file:1" }')
    settings = build(tmp_path)
    assert settings.ollama_base_url == "http://from-file:1"
    assert "ollama_base_url" in settings.config_file_fields
    assert "ollama_base_url" not in settings.provider_explicit


def test_dotenv_wins_over_the_file_for_a_provider_field(folder: Path, tmp_path: Path) -> None:
    write_config(folder, '{ "llamacpp_chat_url": "http://from-file:1/v1" }')
    settings = build(tmp_path, "LLAMACPP_CHAT_URL=http://from-dotenv:2/v1\n")
    assert settings.llamacpp_chat_url == "http://from-dotenv:2/v1"
    assert source_of(settings, "llamacpp_chat_url") == "dotenv"
    assert "llamacpp_chat_url" in settings.provider_explicit
    assert "llamacpp_chat_url" not in settings.config_file_fields


def test_chat_choice_comes_from_the_file(folder: Path, tmp_path: Path) -> None:
    write_config(folder, '{ "answer": { "provider": "anthropic", "model": "claude-x" } }')
    settings = build(tmp_path)
    assert (settings.answer.provider, settings.answer.model) == ("anthropic", "claude-x")
    assert source_of(settings, "answer.model") == "config-file"


# ── env against dotenv (task 2.3) ────────────────────────────────────────


def test_shell_export_reports_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://from-shell:1")
    settings = build(tmp_path)
    assert source_of(settings, "ollama_base_url") == "env"


def test_dotenv_line_reports_dotenv(tmp_path: Path) -> None:
    settings = build(tmp_path, "OLLAMA_BASE_URL=http://from-dotenv:2\n")
    assert source_of(settings, "ollama_base_url") == "dotenv"


def test_key_loaded_from_dotenv_into_the_environment_reports_dotenv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``load_dotenv`` copies ``.env`` into ``os.environ`` at import; the name still tells."""
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://from-dotenv:2")
    monkeypatch.setattr(provenance, "DOTENV_KEYS", frozenset({"OLLAMA_BASE_URL"}))
    assert source_of(build(tmp_path), "ollama_base_url") == "dotenv"


def test_load_project_dotenv_keeps_names_not_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "http://value-that-must-not-be-kept:9"  # noqa: S105
    (tmp_path / ".env").write_text(
        f"LLAMACPP_CHAT_URL={secret}\nOLLAMA_BASE_URL=http://dotenv-ollama:1\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LLAMACPP_CHAT_URL", raising=False)
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://shell-ollama:2")  # a shell export wins
    monkeypatch.setattr(provenance, "DOTENV_KEYS", frozenset())
    names = provenance.load_project_dotenv()
    try:
        assert names == provenance.DOTENV_KEYS
        assert "LLAMACPP_CHAT_URL" in names
        assert "OLLAMA_BASE_URL" not in names  # the shell set it first
        assert secret not in repr(names)
    finally:
        os.environ.pop("LLAMACPP_CHAT_URL", None)  # load_dotenv put it there, not monkeypatch


# ── Problems (task 2.4) ──────────────────────────────────────────────────


def test_broken_file_gives_no_values_one_warning_and_the_server_starts(
    folder: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    write_config(folder, '{ "retrieval": { "top_k": 7 }, oops')
    with caplog.at_level(logging.WARNING):
        parsed = read_settings_file()
        read_settings_file()
        settings = build(tmp_path)
    assert parsed.state == "broken"
    assert parsed.values == {}
    assert [(p.kind, p.key) for p in parsed.problems] == [(KIND_BROKEN, "omrs.jsonc")]
    assert parsed.problems[0].message == "omrs.jsonc could not be read"
    assert settings.retrieval.top_k == 10
    assert len([m for m in warnings_of(caplog) if "omrs.jsonc" in m]) == 1


def test_invalid_value_is_ignored_and_named_without_its_value(
    folder: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    write_config(folder, '{ "retrieval": { "top_k": "many-things" } }')
    with caplog.at_level(logging.WARNING):
        parsed = read_settings_file()
        settings = build(tmp_path)
    assert settings.retrieval.top_k == 10
    assert [(p.kind, p.key) for p in parsed.problems] == [(KIND_INVALID, "retrieval.top_k")]
    assert "many-things" not in parsed.problems[0].message
    assert all("many-things" not in m for m in warnings_of(caplog))
    assert any("retrieval.top_k" in m for m in warnings_of(caplog))


def test_out_of_range_number_is_invalid(folder: Path) -> None:
    write_config(folder, '{ "ollama_context_window": 12 }')
    parsed = read_settings_file()
    assert [(p.kind, p.key) for p in parsed.problems] == [(KIND_INVALID, "ollama_context_window")]
    assert "ollama_context_window" not in parsed.values


def test_boolean_is_not_a_number(folder: Path) -> None:
    write_config(folder, '{ "community_seed": true }')
    assert [p.key for p in read_settings_file().problems] == ["community_seed"]


def test_invalid_address_is_ignored_and_the_warning_names_the_field(
    folder: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    write_config(folder, '{ "ollama_base_url": "file:///etc/passwd" }')
    with caplog.at_level(logging.WARNING):
        parsed = read_settings_file()
        settings = build(tmp_path)
    assert settings.ollama_base_url == Settings.model_fields["ollama_base_url"].default
    assert [(p.kind, p.key) for p in parsed.problems] == [(KIND_INVALID, "ollama_base_url")]
    messages = warnings_of(caplog)
    assert any("ollama_base_url" in m for m in messages)
    assert all("passwd" not in m for m in messages)


def test_unaccepted_choice_is_ignored(folder: Path, tmp_path: Path) -> None:
    write_config(folder, '{ "embed_provider": "bogus" }')
    parsed = read_settings_file()
    assert [(p.kind, p.key) for p in parsed.problems] == [(KIND_INVALID, "embed_provider")]
    assert build(tmp_path).embed_provider == "local"  # conftest env: the file did not apply


def test_one_bad_value_does_not_drop_the_good_ones(folder: Path, tmp_path: Path) -> None:
    write_config(folder, '{ "retrieval": { "top_k": "x", "similarity_threshold": 0.4 } }')
    settings = build(tmp_path)
    assert settings.retrieval.similarity_threshold == 0.4
    assert settings.retrieval.top_k == 10


def test_typo_in_a_block_name_is_unknown(folder: Path, tmp_path: Path) -> None:
    write_config(folder, '{ "retreival": { "top_k": 5 } }')
    parsed = read_settings_file()
    assert [(p.kind, p.key) for p in parsed.problems] == [(KIND_UNKNOWN, "retreival")]
    assert build(tmp_path).retrieval.top_k == 10


def test_unknown_key_inside_a_block(folder: Path, tmp_path: Path) -> None:
    write_config(folder, '{ "retrieval": { "top_kk": 5, "top_k": 6 } }')
    parsed = read_settings_file()
    assert [(p.kind, p.key) for p in parsed.problems] == [(KIND_UNKNOWN, "retrieval.top_kk")]
    assert build(tmp_path).retrieval.top_k == 6


def test_retired_flat_name_names_its_replacement(folder: Path, tmp_path: Path) -> None:
    write_config(folder, '{ "top_k": 5 }')
    parsed = read_settings_file()
    (problem,) = parsed.problems
    assert (problem.kind, problem.key, problem.replacement) == (
        KIND_RETIRED,
        "top_k",
        "retrieval.top_k",
    )
    assert "retrieval.top_k" in problem.message
    assert build(tmp_path).retrieval.top_k == 10


def test_retired_name_inside_a_block_names_its_replacement(folder: Path) -> None:
    write_config(folder, '{ "metadata": { "ollama_classify_max_attempts": 3 } }')
    (problem,) = read_settings_file().problems
    assert (problem.kind, problem.key, problem.replacement) == (
        KIND_RETIRED,
        "metadata.ollama_classify_max_attempts",
        "metadata.classify_max_attempts",
    )


def test_top_level_value_that_is_not_an_object_is_broken(folder: Path) -> None:
    write_config(folder, "[1, 2]")
    parsed = read_settings_file()
    assert parsed.state == "broken"
    assert parsed.problems[0].kind == KIND_BROKEN


def test_block_that_is_not_an_object_is_invalid(folder: Path) -> None:
    write_config(folder, '{ "retrieval": 5 }')
    assert [(p.kind, p.key) for p in read_settings_file().problems] == [(KIND_INVALID, "retrieval")]


def test_a_clean_file_has_no_problems(folder: Path) -> None:
    write_config(folder, '{ "retrieval": { "top_k": 7 }, "ollama_base_url": "http://box:11434" }')
    parsed = read_settings_file()
    assert parsed.state == "ok"
    assert parsed.problems == ()


def test_a_missing_file_has_no_problems_and_no_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("OMRS_CONFIG_DIR", str(tmp_path / "never"))
    with caplog.at_level(logging.WARNING):
        parsed = read_settings_file()
    assert (parsed.state, parsed.revision, parsed.values, parsed.problems) == (
        "absent",
        "absent",
        {},
        (),
    )
    assert warnings_of(caplog) == []
    assert not (tmp_path / "never").exists()


def test_the_source_does_not_hand_unknown_keys_to_pydantic(folder: Path) -> None:
    write_config(folder, '{ "retreival": { "top_k": 5 }, "retrieval": { "top_kk": 1 } }')
    assert UserConfigSource(Settings)() == {}


# ── Revision ─────────────────────────────────────────────────────────────


def test_revision_is_the_sha256_of_the_bytes(folder: Path) -> None:
    path = write_config(folder, '{ "community_seed": 5 }\n')
    assert read_settings_file().revision == hashlib.sha256(path.read_bytes()).hexdigest()


def test_revision_changes_when_one_byte_changes(folder: Path) -> None:
    path = write_config(folder, '{ "community_seed": 5 }')
    before = read_settings_file().revision
    path.write_text('{ "community_seed": 6 }', encoding="utf-8")
    assert read_settings_file().revision != before


# ── The configuration guide (task 2.6) ───────────────────────────────────

GUIDE = Path(__file__).resolve().parents[2] / "docs" / "guides" / "configuration.md"


def guide_example() -> str:
    text = GUIDE.read_text(encoding="utf-8")
    after = text.split("Example `omrs.jsonc` (fake values):", 1)[1]
    return after.split("```jsonc", 1)[1].split("```", 1)[0]


def test_the_example_file_in_the_guide_parses_and_has_no_problems(folder: Path) -> None:
    from omrs.config.user_config import parse_jsonc

    example = guide_example()
    assert isinstance(parse_jsonc(example), dict)
    write_config(folder, example)
    parsed = read_settings_file()
    assert parsed.state == "ok"
    assert parsed.problems == ()
    assert parsed.values["retrieval.top_k"] == 7
    assert parsed.values["web_port"] == 9100
    assert parsed.references == {"openrouter_api_key": "openrouter"}


def test_the_key_name_examples_in_the_guide_parse() -> None:
    from omrs.config.user_config import parse_jsonc

    text = GUIDE.read_text(encoding="utf-8")
    block = text.split("##### Key names", 1)[1].split("```text", 1)[1].split("```", 1)[0]
    pairs = [line.split("→") for line in block.strip().splitlines()]
    assert len(pairs) == 4
    for variable, example in pairs:
        parsed = parse_jsonc(example.strip())
        path = variable.strip().lower().split("__")
        node = parsed
        for part in path:
            node = node[part.replace(" ", "")] if isinstance(node, dict) else node
        assert node is not None
