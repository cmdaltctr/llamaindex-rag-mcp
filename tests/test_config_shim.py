"""Tests for the PEP 562 legacy-constant shim in ``rag_mcp.config``.

Covers OpenSpec change ``phase-2-refactor-config-core-split`` task 4.2.

The rewritten ``config`` package exposes each frozen legacy constant
(``TOP_K``, ``CHUNK_SIZE``, ``RERANK_ENABLED`` …) via a module-level
``__getattr__`` that resolves the value from the resolved ``Settings``
singleton and emits a ``DeprecationWarning``.  Real attributes
(``Settings``, static data mappings) resolve without warning, and
unknown names raise ``AttributeError``.
"""

from __future__ import annotations

import warnings

import pytest

import rag_mcp.config as config


@pytest.fixture(autouse=True)
def _exercise_legacy_shim_path() -> None:
    """Strip any legacy constants present as real module attributes.

    The shared ``conftest.py`` patches a handful of legacy names directly
    onto the config module via ``monkeypatch.setattr``, which makes them
    real ``__dict__`` entries.  A real entry bypasses the PEP 562
    ``__getattr__`` (so no ``DeprecationWarning`` fires) and
    ``monkeypatch.delattr`` cannot remove it because ``hasattr`` returns
    True via ``__getattr__`` while the name is absent from ``__dict__``.

    Popping such names from ``__dict__`` for the duration of each test
    guarantees the ``__getattr__`` path is exercised.  ``monkeypatch.delattr``
    is avoided precisely because it is incompatible with virtual attributes.
    """
    saved: dict[str, object] = {}
    for name in list(config.__dict__):
        if name in config._LEGACY_ALIASES:
            saved[name] = config.__dict__.pop(name)
    yield
    config.__dict__.update(saved)


# ── Legacy constant resolution with deprecation warning ────────────────


def _legacy_alias_cases() -> list[tuple[str, str]]:
    """Return (legacy_name, settings_field) pairs for every shimmed constant.

    Pulled dynamically from the module's ``_LEGACY_ALIASES`` registry so
    the test stays in lock-step with the implementation surface.
    """
    return sorted(config._LEGACY_ALIASES.items())


@pytest.mark.parametrize(
    "legacy_name, field_name",
    _legacy_alias_cases(),
    ids=[name for name, _ in _legacy_alias_cases()],
)
def test_legacy_constant_resolves_and_warns(
    legacy_name: str, field_name: str
) -> None:
    """Each legacy constant SHALL resolve from Settings and warn on access."""
    with pytest.warns(DeprecationWarning, match=legacy_name):
        value = getattr(config, legacy_name)
    assert value == getattr(config.settings, field_name)


@pytest.mark.parametrize(
    "legacy_name",
    [
        "TOP_K",
        "CHUNK_SIZE",
        "CHUNK_OVERLAP",
        "RERANK_ENABLED",
        "RERANK_ENABLED_FOR_SEMANTIC",
        "HARD_TECHNICAL_THRESHOLD",
        "SIMILARITY_THRESHOLD",
        "EMBED_PROVIDER",
        "METADATA_LLM_PROVIDER",
        "LOCAL_BACKEND",
        "CLOUD_BACKEND",
        "EMBED_MODEL_NAME",
        "HYBRID_ENABLED",
        "HYBRID_RRF_K",
        "HYBRID_SPARSE_BACKEND",
        "PDF_READER",
        "DOC_SIMILARITY_THRESHOLD",
        "CHROMA_PERSIST_DIR",
        "COLLECTION_NAME",
    ],
)
def test_legacy_constant_warns_with_migration_hint(
    legacy_name: str,
) -> None:
    """The deprecation message SHALL point at the structured setting."""
    with pytest.warns(DeprecationWarning, match=r"use `from rag_mcp\.config import settings"):
        getattr(config, legacy_name)


def test_embed_model_name_alias_maps_to_embed_model() -> None:
    """EMBED_MODEL_NAME (legacy) SHALL alias the ``embed_model`` field."""
    with pytest.warns(DeprecationWarning):
        value = getattr(config, "EMBED_MODEL_NAME")
    assert value == config.settings.embed_model


def test_liteparse_num_workers_alias_maps_to_field() -> None:
    """LITEPARSE_NUM_WORKERS SHALL alias the int|None field."""
    with pytest.warns(DeprecationWarning):
        value = getattr(config, "LITEPARSE_NUM_WORKERS")
    assert value == config.settings.liteparse_num_workers


# ── Real attributes resolve without warning ────────────────────────────


def test_settings_class_is_real_attribute() -> None:
    """``Settings`` SHALL be importable without a DeprecationWarning."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        resolved = getattr(config, "Settings")
    assert resolved is config.Settings


def test_singleton_settings_is_real_attribute() -> None:
    """The ``settings`` singleton SHALL be a real attribute (no warning)."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        resolved = getattr(config, "settings")
    assert resolved is config.settings


def test_get_settings_callable_is_real_attribute() -> None:
    """``get_settings`` SHALL be a real attribute (no warning)."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        resolved = getattr(config, "get_settings")
    assert callable(resolved)


# ── Static data mappings resolve without warning ───────────────────────


def test_supported_extensions_is_static_data() -> None:
    """SUPPORTED_EXTENSIONS SHALL be a real data attribute, not shimmed."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        value = getattr(config, "SUPPORTED_EXTENSIONS")
    assert isinstance(value, set)
    assert ".pdf" in value
    assert ".md" in value


def test_magika_label_to_treesitter_is_static_data() -> None:
    """MAGIKA_LABEL_TO_TREESITTER SHALL be a real data attribute, not shimmed."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        value = getattr(config, "MAGIKA_LABEL_TO_TREESITTER")
    assert isinstance(value, dict)
    assert value["python"] == "python"


def test_resolved_runtime_constants_are_static() -> None:
    """RESOLVED_* runtime probes SHALL be real attributes (no warning)."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        sparse = getattr(config, "RESOLVED_HYBRID_SPARSE_BACKEND")
        reader = getattr(config, "RESOLVED_PDF_READER")
    assert sparse in ("bm25", "native")
    assert reader in ("auto", "liteparse", "pypdfium2", "pypdf")


# ── Unknown attributes ──────────────────────────────────────────────────


def test_unknown_constant_raises_attribute_error() -> None:
    """A genuinely unknown name SHALL raise AttributeError."""
    with pytest.raises(AttributeError, match="NONEXISTENT_CONSTANT"):
        getattr(config, "NONEXISTENT_CONSTANT")


def test_unknown_constant_does_not_warn() -> None:
    """An unknown name SHALL raise, not emit a deprecation warning."""
    with pytest.raises(AttributeError):
        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            getattr(config, "ALSO_NOT_REAL")
