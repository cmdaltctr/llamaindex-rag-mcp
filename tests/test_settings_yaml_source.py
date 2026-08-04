"""Tests for ``config/defaults.yaml`` resolution in the Settings resolver.

Covers OpenSpec change ``phase-2-refactor-config-core-split`` task 2.7.

The YAML source sits between field defaults (lower) and env/.env (higher).
These tests pin:
- values present in defaults.yaml resolve to their YAML value,
- environment variables override the YAML source,
- a YAML-backed field and a non-YAML field both resolve correctly,
- the YAML loads via ``importlib.resources`` independent of CWD,
- the packaged defaults.yaml resource path exists.
"""

from __future__ import annotations

import os

import pytest
import yaml

from rag_mcp.config import Settings


def _fresh_settings() -> Settings:
    """Build a fresh ``Settings`` with the ``.env`` source disabled."""
    return Settings(_env_file=None)


def _load_packaged_yaml() -> dict[str, object]:
    """Load the packaged defaults.yaml as a plain dict."""
    from importlib.resources import files

    yaml_path = files("rag_mcp.config") / "defaults.yaml"
    with yaml_path.open("r") as fh:
        data = yaml.safe_load(fh)
    return data if isinstance(data, dict) else {}


# ── Packaged resource ───────────────────────────────────────────────────


def test_defaults_yaml_resource_exists() -> None:
    """The packaged ``defaults.yaml`` SHALL be discoverable as a file."""
    from importlib.resources import files

    yaml_path = files("rag_mcp.config") / "defaults.yaml"
    assert yaml_path.is_file()


def test_defaults_yaml_is_valid_mapping() -> None:
    """defaults.yaml SHALL parse to a non-empty mapping."""
    data = _load_packaged_yaml()
    assert isinstance(data, dict)
    assert len(data) > 0


# ── Values match defaults.yaml ──────────────────────────────────────────


@pytest.mark.parametrize(
    "env_name, field_name",
    [
        ("CHUNK_SIZE", "chunk_size"),
        ("CHUNK_OVERLAP", "chunk_overlap"),
        ("TOP_K", "top_k"),
        ("CHROMA_PERSIST_DIR", "chroma_persist_dir"),
        ("COLLECTION_NAME", "collection_name"),
        ("EMBED_PROVIDER", "embed_provider"),
        ("HYBRID_SPARSE_BACKEND", "hybrid_sparse_backend"),
        ("DOC_SIMILARITY_THRESHOLD", "doc_similarity_threshold"),
    ],
    ids=lambda v: v,
)
def test_resolved_value_matches_defaults_yaml(
    env_name: str,
    field_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With the env var unset, the resolved value SHALL equal defaults.yaml."""
    monkeypatch.delenv(env_name, raising=False)
    data = _load_packaged_yaml()
    settings = _fresh_settings()
    assert getattr(settings, field_name) == data[env_name]


# ── Precedence: env overrides YAML ──────────────────────────────────────


def test_env_overrides_yaml_for_chunk_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An environment variable SHALL win over defaults.yaml."""
    monkeypatch.setenv("CHUNK_SIZE", "999")
    settings = _fresh_settings()
    assert settings.chunk_size == 999


def test_env_overrides_yaml_for_top_k(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TOP_K env var SHALL take precedence over the YAML default."""
    monkeypatch.setenv("TOP_K", "42")
    settings = _fresh_settings()
    assert settings.top_k == 42


# ── YAML-backed vs field-default-only ───────────────────────────────────


def test_yaml_backed_field_resolves_from_yaml(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A field present in defaults.yaml SHALL resolve to its YAML value."""
    monkeypatch.delenv("CHUNK_SIZE", raising=False)
    data = _load_packaged_yaml()
    assert "CHUNK_SIZE" in data
    settings = _fresh_settings()
    assert settings.chunk_size == data["CHUNK_SIZE"]


def test_non_yaml_field_resolves_from_field_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A field absent from defaults.yaml SHALL fall back to its field default.

    LLAMACPP_EMBED_URL is not in defaults.yaml, so the model's declared
    field default applies.
    """
    monkeypatch.delenv("LLAMACPP_EMBED_URL", raising=False)
    data = _load_packaged_yaml()
    assert "LLAMACPP_EMBED_URL" not in data
    field_default = Settings.model_fields["llamacpp_embed_url"].default
    settings = _fresh_settings()
    assert settings.llamacpp_embed_url == field_default


# ── CWD independence (installed-wheel behaviour) ────────────────────────


def test_yaml_resolves_from_temporary_working_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """defaults.yaml SHALL load via importlib.resources regardless of CWD.

    Simulates installed-wheel resource loading: from a temp directory with
    no ``pyproject.toml`` and no ``config/`` folder, the packaged YAML is
    still found and applied.
    """
    monkeypatch.delenv("CHUNK_SIZE", raising=False)
    monkeypatch.delenv("TOP_K", raising=False)
    monkeypatch.delenv("CHROMA_PERSIST_DIR", raising=False)

    original_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        assert not (tmp_path / "pyproject.toml").exists()
        assert not (tmp_path / "config").exists()
        settings = _fresh_settings()
        assert settings.chunk_size == 512
        assert settings.top_k == 10
        assert settings.chroma_persist_dir == "./chroma_db"
    finally:
        os.chdir(original_cwd)


# ── Drift guard: defaults.yaml vs model field defaults ───────────────────


def _normalise_yaml_value(field_name: str, yaml_value: object) -> object:
    """Normalise a raw YAML value for comparison with the model field default.

    Boolean knobs are stored as the strings ``"true"``/``"false"`` in
    defaults.yaml (matching the legacy env-parsing contract); the model
    declares real booleans.  Everything else compares as-is.
    """
    default = Settings.model_fields[field_name].default
    if isinstance(default, bool):
        if isinstance(yaml_value, str):
            return yaml_value.lower() == "true"
        return bool(yaml_value)
    return yaml_value


def test_yaml_defaults_match_model_field_defaults() -> None:
    """Every key in defaults.yaml SHALL agree with its model field default.

    Guard against drift between the two default locations: the subpackage
    settings models declare the authoritative default, and defaults.yaml
    ships a copy as a resolution layer.  If they diverge, this fails.
    """
    data = _load_packaged_yaml()
    assert data, "defaults.yaml must not be empty"
    for env_name, yaml_value in data.items():
        field_name = env_name.lower()
        assert field_name in Settings.model_fields, (
            f"defaults.yaml key {env_name} has no Settings field {field_name!r}"
        )
        assert (
            _normalise_yaml_value(field_name, yaml_value)
            == Settings.model_fields[field_name].default
        ), (
            f"defaults.yaml {env_name}={yaml_value!r} disagrees with the "
            f"model default {Settings.model_fields[field_name].default!r}"
        )
