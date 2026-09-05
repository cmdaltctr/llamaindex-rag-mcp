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

from omrg.config import Settings


def _yaml_lookup(data: dict, dotted: str, env_name: str) -> object:
    """Read a value from defaults.yaml by its schema location.

    Nested subpackage keys live under their block with lowercase leaves
    (``retrieval: {top_k: 10}``); cross-cutting keys stay flat and
    SCREAMING_SNAKE at the top level.
    """
    if "." in dotted:
        block, leaf = dotted.split(".", 1)
        return data[block][leaf]
    return data[env_name]


def _get_nested(obj: object, dotted: str) -> object:
    """Resolve a dotted field path (``retrieval.top_k``) on nested Settings."""
    for part in dotted.split("."):
        obj = getattr(obj, part)
    return obj


def _fresh_settings() -> Settings:
    """Build a fresh ``Settings`` with the ``.env`` source disabled."""
    return Settings(_env_file=None)


def _load_packaged_yaml() -> dict[str, object]:
    """Load the packaged defaults.yaml as a plain dict."""
    from importlib.resources import files

    yaml_path = files("omrg.config") / "defaults.yaml"
    with yaml_path.open("r") as fh:
        data = yaml.safe_load(fh)
    return data if isinstance(data, dict) else {}


# ── Packaged resource ───────────────────────────────────────────────────


def test_defaults_yaml_resource_exists() -> None:
    """The packaged ``defaults.yaml`` SHALL be discoverable as a file."""
    from importlib.resources import files

    yaml_path = files("omrg.config") / "defaults.yaml"
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
        ("CHUNKING__CHUNK_SIZE", "chunking.chunk_size"),
        ("CHUNKING__CHUNK_OVERLAP", "chunking.chunk_overlap"),
        ("RETRIEVAL__TOP_K", "retrieval.top_k"),
        ("CHROMA_PERSIST_DIR", "chroma_persist_dir"),
        ("COLLECTION_NAME", "collection_name"),
        ("EMBED_PROVIDER", "embed_provider"),
        ("RETRIEVAL__HYBRID_SPARSE_BACKEND", "retrieval.hybrid_sparse_backend"),
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
    assert _get_nested(settings, field_name) == _yaml_lookup(data, field_name, env_name)


# ── Precedence: env overrides YAML ──────────────────────────────────────


def test_env_overrides_yaml_for_chunk_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An environment variable SHALL win over defaults.yaml."""
    monkeypatch.setenv("CHUNKING__CHUNK_SIZE", "999")
    settings = _fresh_settings()
    assert settings.chunking.chunk_size == 999


def test_env_overrides_yaml_for_top_k(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TOP_K env var SHALL take precedence over the YAML default."""
    monkeypatch.setenv("RETRIEVAL__TOP_K", "42")
    settings = _fresh_settings()
    assert settings.retrieval.top_k == 42


# ── YAML-backed vs field-default-only ───────────────────────────────────


def test_yaml_backed_field_resolves_from_yaml(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A field present in defaults.yaml SHALL resolve to its YAML value."""
    monkeypatch.delenv("CHUNKING__CHUNK_SIZE", raising=False)
    data = _load_packaged_yaml()
    assert "chunking" in data and "chunk_size" in data["chunking"]
    settings = _fresh_settings()
    assert settings.chunking.chunk_size == data["chunking"]["chunk_size"]


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
    monkeypatch.delenv("CHUNKING__CHUNK_SIZE", raising=False)
    monkeypatch.delenv("RETRIEVAL__TOP_K", raising=False)
    monkeypatch.delenv("CHROMA_PERSIST_DIR", raising=False)

    original_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        assert not (tmp_path / "pyproject.toml").exists()
        assert not (tmp_path / "config").exists()
        settings = _fresh_settings()
        assert settings.chunking.chunk_size == 512
        assert settings.retrieval.top_k == 10
        assert settings.chroma_persist_dir == "./chroma_db"
    finally:
        os.chdir(original_cwd)


# ── Drift guard: defaults.yaml vs model field defaults ───────────────────


def _normalise_yaml_value(expected: object, yaml_value: object) -> object:
    """Normalise a raw YAML value for comparison with a model field default.

    v2.0.0 writes native YAML booleans, but a quoted ``"true"``/``"false"``
    is still accepted by the LegacyBool validators, so normalise both to a
    real bool when the expected default is boolean.
    """
    if isinstance(expected, bool):
        if isinstance(yaml_value, str):
            return yaml_value.lower() == "true"
        return bool(yaml_value)
    return yaml_value


def test_yaml_defaults_match_model_field_defaults() -> None:
    """Every key in defaults.yaml SHALL agree with its model field default.

    Guards against drift between the two default locations: the subpackage
    settings models declare the authoritative default, and defaults.yaml
    ships a copy as a resolution layer. If they diverge, this fails.

    v2.0.0: subpackage keys are nested under their block with lowercase
    leaves; cross-cutting keys remain flat and SCREAMING_SNAKE.
    """
    data = _load_packaged_yaml()
    assert data, "defaults.yaml must not be empty"

    for key, value in data.items():
        if isinstance(value, dict):
            # Nested block: compare each leaf against the block model's default.
            assert key in Settings.model_fields, (
                f"defaults.yaml block {key!r} has no matching Settings field"
            )
            block_cls = Settings.model_fields[key].annotation
            for leaf, leaf_value in value.items():
                assert leaf in block_cls.model_fields, (
                    f"defaults.yaml {key}.{leaf} has no field on {block_cls.__name__}"
                )
                expected = block_cls.model_fields[leaf].default
                assert _normalise_yaml_value(expected, leaf_value) == expected, (
                    f"defaults.yaml {key}.{leaf}={leaf_value!r} disagrees "
                    f"with the model default {expected!r}"
                )
        else:
            # Flat cross-cutting key.
            field_name = key.lower()
            assert field_name in Settings.model_fields, (
                f"defaults.yaml key {key} has no Settings field {field_name!r}"
            )
            expected = Settings.model_fields[field_name].default
            assert _normalise_yaml_value(expected, value) == expected, (
                f"defaults.yaml {key}={value!r} disagrees with the model default {expected!r}"
            )


def test_every_subpackage_block_is_present_in_yaml() -> None:
    """All four nested blocks must ship defaults, so none silently drifts."""
    data = _load_packaged_yaml()
    for block in ("chunking", "ingestion", "retrieval", "metadata"):
        assert block in data, f"defaults.yaml is missing the {block!r} block"
