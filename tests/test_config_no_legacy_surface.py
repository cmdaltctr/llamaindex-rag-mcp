"""The v1 configuration surface is gone (v2.0.0).

Replaces ``test_config_shim.py``, which tested the PEP 562 legacy-constant
``__getattr__``. That shim resolved names like ``TOP_K`` from a module-level
``Settings`` singleton; both were deleted in the architecture-v2 conformance
change (tasks 5.7 and 9.1). These tests assert the removal stuck.
"""

from __future__ import annotations

import pytest

import omrg.config as config


class TestNoLegacyConstantShim:
    """The PEP 562 alias table must not come back."""

    @pytest.mark.parametrize(
        "name",
        ["TOP_K", "CHUNK_SIZE", "RERANK_ENABLED", "MARKDOWN_CHUNK_SIZE"],
    )
    def test_legacy_constant_raises_attribute_error(self, name: str) -> None:
        """A legacy flat constant must raise, not resolve with a warning."""
        with pytest.raises(AttributeError):
            getattr(config, name)

    def test_no_module_level_settings_singleton(self) -> None:
        """``config.settings`` is gone; callers use get_settings()."""
        assert not hasattr(config, "settings")

    def test_no_resolved_constants(self) -> None:
        """The RESOLVED_* constants moved to compose as capability probes."""
        assert not hasattr(config, "RESOLVED_PDF_READER")
        assert not hasattr(config, "RESOLVED_HYBRID_SPARSE_BACKEND")


class TestImportHasNoSideEffects:
    """Importing config must resolve nothing (spec: config-composition-root)."""

    def test_import_does_not_construct_settings(self) -> None:
        """No Settings instance is built as an import side effect."""
        assert config._settings is None or isinstance(config._settings, config.Settings)

    def test_get_settings_is_the_entry_point(self) -> None:
        """get_settings() still resolves and caches."""
        first = config.get_settings()
        assert first is config.get_settings()


class TestLegacyEnvTripwire:
    """Retired env vars fail loudly rather than being ignored."""

    @pytest.mark.parametrize(
        ("old", "new"),
        sorted(config._RETIRED_ENV_VARS.items()),
    )
    def test_retired_name_raises_naming_replacement(self, old: str, new: str) -> None:
        """The error names both the offending var and its replacement.

        Parametrised over the whole mapping so a newly retired name is
        covered the moment it is added, rather than whenever someone
        remembers to write a case for it.

        Asserts on the rendered ``old  ->  new`` line rather than bare
        membership of each name: for 19 of the pairs ``old`` is a substring
        of ``new`` (``TOP_K`` in ``RETRIEVAL__TOP_K``), so two separate
        ``in`` checks would pass even if the message dropped the offending
        name entirely — which is half the point of the message.
        """
        with pytest.raises(ValueError) as exc:
            config.check_legacy_env_vars({old: "x"})
        assert f"{old}  ->  {new}" in str(exc.value)

    def test_retired_mapping_is_pinned(self) -> None:
        """Deleting a mapping entry must fail, not silently shrink the sweep.

        ``test_retired_name_raises_naming_replacement`` draws its cases from
        the mapping itself, so a removed entry takes its own test case with
        it and the suite stays green. Pinning the key set makes a deletion —
        the regression that actually matters — fail loudly.
        """
        assert set(config._RETIRED_ENV_VARS) == {
            "CHUNK_SIZE",
            "CHUNK_OVERLAP",
            "MARKDOWN_CHUNK_SIZE",
            "MARKDOWN_HEADING_PREPEND",
            "MARKDOWN_MIN_CHUNK_FRACTION",
            "CHUNK_STRATEGY_FALLBACK",
            "EMBED_CONCURRENCY",
            "EMBED_BATCH_SIZE",
            "TOP_K",
            "SIMILARITY_THRESHOLD",
            "RERANK_ENABLED",
            "RERANK_ENABLED_FOR_SEMANTIC",
            "HARD_TECHNICAL_THRESHOLD",
            "RERANK_FETCH_MULTIPLIER",
            "RERANK_MAX_FETCH",
            "RERANK_MODEL",
            "HYBRID_ENABLED",
            "HYBRID_RRF_K",
            "HYBRID_SPARSE_BACKEND",
            "METADATA_EXTRACTION_MODE",
            "METADATA_KEYWORD_RULES",
            "METADATA_TAXONOMY_MODE",
            "OLLAMA_CLASSIFY_MODEL",
            "OLLAMA_CLASSIFY_MAX_ATTEMPTS",
            "OLLAMA_CLASSIFY_TIMEOUT",
            "METADATA__OLLAMA_CLASSIFY_MAX_ATTEMPTS",
            "METADATA__OLLAMA_CLASSIFY_TIMEOUT",
        }

    @pytest.mark.parametrize(
        ("old", "new"),
        [
            (
                "METADATA__OLLAMA_CLASSIFY_MAX_ATTEMPTS",
                "METADATA__CLASSIFY_MAX_ATTEMPTS",
            ),
            (
                "METADATA__OLLAMA_CLASSIFY_TIMEOUT",
                "METADATA__CLASSIFY_TIMEOUT",
            ),
        ],
    )
    def test_renamed_nested_names_are_tripwired(self, old: str, new: str) -> None:
        """The v2 nested classify names retired by the rename must trip.

        Pinned explicitly rather than left to the parametrised sweep above:
        these are nested keys a block model would swallow via its own
        schema, so losing them from the mapping would be silent.
        """
        assert config._RETIRED_ENV_VARS[old] == new
        with pytest.raises(ValueError, match=new):
            config.check_legacy_env_vars({old: "x"})

    def test_clean_environment_passes(self) -> None:
        """A migrated environment raises nothing."""
        config.check_legacy_env_vars({"RETRIEVAL__TOP_K": "20", "PATH": "/usr/bin"})

    def test_cross_cutting_names_are_not_flagged(self) -> None:
        """Flat cross-cutting names are still valid and must not trip it."""
        config.check_legacy_env_vars(
            {"EMBED_MODEL": "x", "RAG_PROFILE": "documents", "PDF_READER": "pypdf"}
        )
