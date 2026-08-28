"""Degradation paths in the settings sources and Ollama knob resolution.

Task 12.2. These branches are the graceful-degradation contract: a missing
or malformed YAML file, and an unparseable env override, must fall back
rather than abort startup.
"""

from __future__ import annotations

import pytest

from rag_mcp.core.settings import EffectiveSettings, MetadataBlock


class TestYamlSourceDegradation:
    """A missing or malformed defaults.yaml must not abort resolution."""

    def test_missing_file_yields_empty_defaults(self, monkeypatch) -> None:
        import rag_mcp.config.sources as sources

        def _missing(_pkg):
            raise FileNotFoundError("no defaults.yaml")

        monkeypatch.setattr(sources, "files", _missing)
        from rag_mcp.config import Settings

        # Model field defaults still apply.
        assert Settings(_env_file=None).retrieval.top_k in (5, 10)

    def test_non_mapping_yaml_is_ignored(self, monkeypatch, tmp_path) -> None:
        """A YAML list where a mapping is expected degrades to no defaults."""
        import rag_mcp.config.sources as sources

        bad = tmp_path / "defaults.yaml"
        bad.write_text("- just\n- a\n- list\n")

        class _Anchor:
            def __truediv__(self, _part):
                return bad

        monkeypatch.setattr(sources, "files", lambda _pkg: _Anchor())
        src = sources._YamlDefaultsSource.__new__(sources._YamlDefaultsSource)
        assert src._load_yaml() == {}


class TestProfileBundleDegradation:
    """A malformed or missing bundle degrades to an empty override set."""

    def test_missing_bundle_returns_empty(self, monkeypatch) -> None:
        import rag_mcp.config.sources as sources

        def _missing(_pkg):
            raise FileNotFoundError("no bundle")

        monkeypatch.setattr(sources, "files", _missing)
        assert sources._load_profile_bundle("documents") == {}

    def test_invalid_yaml_returns_empty(self, monkeypatch, tmp_path) -> None:
        """Broken YAML is logged and ignored, not raised."""
        import rag_mcp.config.sources as sources

        bad = tmp_path / "documents.yaml"
        bad.write_text("retrieval: [unclosed\n")

        class _Anchor:
            def __truediv__(self, part):
                return self if part == "profiles" else bad

        monkeypatch.setattr(sources, "files", lambda _pkg: _Anchor())
        assert sources._load_profile_bundle("documents") == {}

    def test_non_mapping_bundle_returns_empty(self, monkeypatch, tmp_path) -> None:
        import rag_mcp.config.sources as sources

        bad = tmp_path / "documents.yaml"
        bad.write_text("- a\n- b\n")

        class _Anchor:
            def __truediv__(self, part):
                return self if part == "profiles" else bad

        monkeypatch.setattr(sources, "files", lambda _pkg: _Anchor())
        assert sources._load_profile_bundle("documents") == {}

    def test_hybrid_with_unknown_default_falls_back_to_documents(
        self, monkeypatch, tmp_path
    ) -> None:
        """An invalid default_profile resolves to documents, not an error."""
        import rag_mcp.config.sources as sources

        (tmp_path / "hybrid.yaml").write_text("default_profile: nonsense\n")
        (tmp_path / "documents.yaml").write_text("retrieval:\n  top_k: 10\n")

        class _Anchor:
            def __truediv__(self, part):
                return self if part == "profiles" else tmp_path / str(part)

        monkeypatch.setattr(sources, "files", lambda _pkg: _Anchor())
        bundle = sources._load_profile_bundle("hybrid")
        assert bundle["retrieval"]["top_k"] == 10


class TestOllamaKnobResolution:
    """Env overrides win, but a malformed value falls back to settings."""

    def _settings(self) -> EffectiveSettings:
        return EffectiveSettings(
            metadata=MetadataBlock(
                ollama_classify_max_attempts=7, ollama_classify_timeout=42.0
            )
        )

    def test_attempts_use_settings_when_env_unset(self, monkeypatch) -> None:
        from rag_mcp.core.metadata.ollama import _get_ollama_max_attempts

        monkeypatch.delenv("OLLAMA_CLASSIFY_MAX_ATTEMPTS", raising=False)
        assert _get_ollama_max_attempts(self._settings()) == 7

    def test_attempts_env_override_wins(self, monkeypatch) -> None:
        from rag_mcp.core.metadata.ollama import _get_ollama_max_attempts

        monkeypatch.setenv("OLLAMA_CLASSIFY_MAX_ATTEMPTS", "3")
        assert _get_ollama_max_attempts(self._settings()) == 3

    def test_malformed_attempts_falls_back(self, monkeypatch) -> None:
        from rag_mcp.core.metadata.ollama import _get_ollama_max_attempts

        monkeypatch.setenv("OLLAMA_CLASSIFY_MAX_ATTEMPTS", "not-a-number")
        assert _get_ollama_max_attempts(self._settings()) == 7

    def test_attempts_floor_is_one(self, monkeypatch) -> None:
        """Zero or negative attempts would skip the call entirely."""
        from rag_mcp.core.metadata.ollama import _get_ollama_max_attempts

        monkeypatch.setenv("OLLAMA_CLASSIFY_MAX_ATTEMPTS", "0")
        assert _get_ollama_max_attempts(self._settings()) == 1

    def test_timeout_uses_settings_when_env_unset(self, monkeypatch) -> None:
        from rag_mcp.core.metadata.ollama import _get_ollama_timeout

        monkeypatch.delenv("OLLAMA_CLASSIFY_TIMEOUT", raising=False)
        assert _get_ollama_timeout(self._settings()) == 42.0

    def test_timeout_env_override_wins(self, monkeypatch) -> None:
        from rag_mcp.core.metadata.ollama import _get_ollama_timeout

        monkeypatch.setenv("OLLAMA_CLASSIFY_TIMEOUT", "2.5")
        assert _get_ollama_timeout(self._settings()) == 2.5

    def test_malformed_timeout_falls_back(self, monkeypatch) -> None:
        from rag_mcp.core.metadata.ollama import _get_ollama_timeout

        monkeypatch.setenv("OLLAMA_CLASSIFY_TIMEOUT", "soon")
        assert _get_ollama_timeout(self._settings()) == 42.0
