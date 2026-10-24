"""Which keys the page may write, and the rule checks on write.

edit-settings-from-configuration-page, tasks 1.1 and 1.2. Every test points
``OMRS_CONFIG_DIR`` at a temporary folder; no test reads ``~/.config/omrs``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from omrs.config.provider_sources import PROVIDER_FIELDS
from omrs.config.rules import SECRET_FIELDS
from omrs.config.settings_file import check_setting, read_settings_file, setting_paths
from omrs.config.settings_file_write import (
    ALLOWED_KEYS,
    READ_ONLY_KEYS,
    SettingsFileRefused,
    read_only_reason,
    write_settings,
)
from omrs.config.user_config import parse_jsonc

EMBEDDING = (
    "The embedding model is part of every collection. Change it in omrs.jsonc and re-ingest."
)
STORAGE = "Existing collections stay where they are. Change it in omrs.jsonc and restart."
WORKERS = "The worker folder is set when the OCR workers are installed."
KEYS = "Keys are set on the provider cards as references."
BY_HAND = "Edit this in omrs.jsonc."


@pytest.fixture
def folder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    root = tmp_path / "cfg" / "omrs"
    monkeypatch.setenv("OMRS_CONFIG_DIR", str(root))
    return root


@pytest.fixture
def existing(folder: Path) -> Path:
    folder.mkdir(parents=True, mode=0o700)
    path = folder / "omrs.jsonc"
    path.write_text(
        '// mine\n{\n  "retrieval": { "hybrid_enabled": true }, // keep\n'
        '  "metadata": { "ollama_classify_timeout_override": 30 }\n}\n',
        encoding="utf-8",
    )
    return path


# ── 1.1 the writable set ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "key",
    ["retrieval.top_k", "answer.enabled", "metadata.extraction_mode", "liteparse_num_workers"],
)
def test_a_scalar_engine_setting_is_allowed(key: str) -> None:
    assert key in ALLOWED_KEYS
    assert read_only_reason(key) is None


@pytest.mark.parametrize(
    ("key", "reason"),
    [
        ("embed_model", EMBEDDING),
        ("embed_provider", EMBEDDING),
        ("local_backend", EMBEDDING),
        ("llamacpp_embed_url", EMBEDDING),
        ("openrouter_embed_model", EMBEDDING),
        ("embedding.tokenizer_model", EMBEDDING),
        ("embedding.norm_tolerance", EMBEDDING),
        ("lancedb_uri", STORAGE),
        ("vector_store", STORAGE),
        ("chroma_persist_dir", STORAGE),
        ("chroma_mode", STORAGE),
        ("collection_name", STORAGE),
        ("ocr_workers_dir", WORKERS),
        ("openrouter_api_key", KEYS),
        ("azure_doc_intelligence_key", KEYS),
        ("ingestion.ingest_extensions", BY_HAND),
        ("metadata.keyword_rules", BY_HAND),
    ],
)
def test_a_read_only_key_is_not_allowed_and_names_its_reason(key: str, reason: str) -> None:
    assert key not in ALLOWED_KEYS
    assert read_only_reason(key) == reason


def test_every_secret_field_is_read_only() -> None:
    assert all(read_only_reason(key) == KEYS for key in SECRET_FIELDS)
    assert not set(SECRET_FIELDS) & set(ALLOWED_KEYS)


def test_the_read_only_list_names_only_real_settings() -> None:
    paths = set(setting_paths())
    for entry in READ_ONLY_KEYS:
        if entry.endswith("."):
            assert any(path.startswith(entry) for path in paths), entry
        else:
            assert entry in paths, entry


def test_allowed_keys_are_every_other_setting_and_the_file_only_keys() -> None:
    others = {key for key in setting_paths() if read_only_reason(key) is None}
    assert set(ALLOWED_KEYS) == others
    assert {"web_port", "web_max_upload_mib", "mcp_http_enabled"} <= set(ALLOWED_KEYS)
    assert len(ALLOWED_KEYS) == len(set(ALLOWED_KEYS))


def test_the_card_keys_other_than_keys_stay_allowed() -> None:
    cards = {key for key in PROVIDER_FIELDS if key not in SECRET_FIELDS}
    assert cards <= set(ALLOWED_KEYS)


def test_a_provider_key_reference_is_still_written(folder: Path) -> None:
    """The Providers cards keep writing ``keychain://`` references through the writer."""
    write_settings({"openrouter_api_key": "keychain://openrouter"}, revision=None)
    text = (folder / "omrs.jsonc").read_text(encoding="utf-8")
    assert parse_jsonc(text) == {"openrouter_api_key": "keychain://openrouter"}


@pytest.mark.parametrize("key", ["embed_model", "lancedb_uri", "ingestion.ingest_extensions"])
def test_a_read_only_key_is_refused_by_the_writer(existing: Path, key: str) -> None:
    before = existing.read_bytes()
    with pytest.raises(SettingsFileRefused) as caught:
        write_settings({key: "x"}, revision=None)
    assert str(caught.value) == f"{key} is not a setting that can be changed here."
    assert existing.read_bytes() == before


def test_a_non_provider_key_field_is_refused(existing: Path) -> None:
    before = existing.read_bytes()
    with pytest.raises(SettingsFileRefused):
        write_settings({"chroma_cloud_api_key": "env://CHROMA_KEY"}, revision=None)
    assert existing.read_bytes() == before


# ── 1.2 rules on write ───────────────────────────────────────────────────


def test_top_k_merges_into_the_existing_block_and_keeps_every_other_byte(existing: Path) -> None:
    before = existing.read_text(encoding="utf-8")
    write_settings({"retrieval.top_k": 20}, revision=None)
    after = existing.read_text(encoding="utf-8")
    assert parse_jsonc(after)["retrieval"] == {"hybrid_enabled": True, "top_k": 20}
    assert after.startswith("// mine\n") and "// keep" in after
    # Only the new member was added: removing it gives the old bytes back.
    write_settings({"retrieval.top_k": None}, revision=None)
    assert existing.read_text(encoding="utf-8") == before


def test_max_rounds_out_of_range_is_refused_with_the_range(existing: Path) -> None:
    before = existing.read_bytes()
    with pytest.raises(SettingsFileRefused) as caught:
        write_settings({"answer.max_rounds": 12}, revision=None)
    assert str(caught.value) == "answer.max_rounds: The value must be a whole number from 1 to 8."
    assert existing.read_bytes() == before


def test_an_unknown_extraction_mode_is_refused_with_the_choices(existing: Path) -> None:
    before = existing.read_bytes()
    with pytest.raises(SettingsFileRefused) as caught:
        write_settings({"metadata.extraction_mode": "magic"}, revision=None)
    message = str(caught.value)
    assert message.startswith("metadata.extraction_mode: The value must be one of: disabled,")
    assert "magic" not in message
    assert existing.read_bytes() == before


def test_null_removes_an_optional_setting(existing: Path) -> None:
    write_settings({"metadata.ollama_classify_timeout_override": None}, revision=None)
    data = parse_jsonc(existing.read_text(encoding="utf-8"))
    assert "ollama_classify_timeout_override" not in data.get("metadata", {})
    assert "metadata.ollama_classify_timeout_override" not in read_settings_file().values


def test_a_wrong_type_is_refused_and_the_file_is_unchanged(existing: Path) -> None:
    before = existing.read_bytes()
    with pytest.raises(SettingsFileRefused):
        write_settings({"retrieval.top_k": True}, revision=None)
    assert existing.read_bytes() == before


@pytest.mark.parametrize(
    ("key", "rule"),
    [
        ("answer.timeout", "The value must be a number greater than 0."),
        ("answer.context_window", "The value must be a whole number greater than 0."),
        ("ocr_worker_seconds_per_page", "The value must be a number of at least 0.0."),
    ],
)
def test_a_one_sided_bound_is_named(key: str, rule: str) -> None:
    assert check_setting(key, -1) == (None, rule)


def test_a_two_sided_bound_keeps_its_text() -> None:
    assert check_setting("ocr_maths_page_fraction", 2.0) == (
        None,
        "The value must be a number from 0.0 to 1.0.",
    )
