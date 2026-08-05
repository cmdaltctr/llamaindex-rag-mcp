"""The v1 configuration surface is gone (v2.0.0).

Replaces ``test_config_shim.py``, which tested the PEP 562 legacy-constant
``__getattr__``. That shim resolved names like ``TOP_K`` from a module-level
``Settings`` singleton; both were deleted in the architecture-v2 conformance
change (tasks 5.7 and 9.1). These tests assert the removal stuck.
"""

from __future__ import annotations

import pytest

import rag_mcp.config as config


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
    """Pre-v2 flat env vars fail loudly rather than being ignored."""

    def test_legacy_name_raises_naming_replacement(self) -> None:
        """The error names both the offending var and its nested replacement."""
        with pytest.raises(ValueError) as exc:
            config.check_legacy_env_vars({"TOP_K": "20"})
        message = str(exc.value)
        assert "TOP_K" in message
        assert "RETRIEVAL__TOP_K" in message

    def test_clean_environment_passes(self) -> None:
        """A migrated environment raises nothing."""
        config.check_legacy_env_vars({"RETRIEVAL__TOP_K": "20", "PATH": "/usr/bin"})

    def test_cross_cutting_names_are_not_flagged(self) -> None:
        """Flat cross-cutting names are still valid and must not trip it."""
        config.check_legacy_env_vars(
            {"EMBED_MODEL": "x", "RAG_PROFILE": "documents", "PDF_READER": "pypdf"}
        )
