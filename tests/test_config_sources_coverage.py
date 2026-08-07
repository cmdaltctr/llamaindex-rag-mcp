"""Degradation paths in the settings sources and Ollama knob resolution.

Task 12.2. These branches are the graceful-degradation contract: a missing
or malformed YAML file, and an unparseable env override, must fall back
rather than abort startup.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from rag_mcp.core.metadata.settings import MetadataSettings
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


class TestClassifyKnobResolution:
    """Settings-injection path for the shared classify retry/timeout knobs."""

    def _settings(self) -> EffectiveSettings:
        return EffectiveSettings(
            metadata=MetadataBlock(
                classify_max_attempts=7, classify_timeout=42.0
            )
        )

    def test_attempts_flow_through_helper(self) -> None:
        from rag_mcp.core.metadata._common import _get_classify_max_attempts

        assert _get_classify_max_attempts(self._settings()) == 7

    def test_timeout_flows_through_helper(self) -> None:
        from rag_mcp.core.metadata._common import _get_classify_timeout

        assert _get_classify_timeout(self._settings()) == 42.0


class TestClassifyKnobBounds:
    """Non-positive retry/timeout knobs are rejected, never clamped.

    Both the config-layer model (``MetadataSettings``) and the effective
    block (``MetadataBlock``) declare these knobs, so both are exercised:
    a bound added to one and forgotten on the other leaves a live hole.
    Rejecting rather than clamping is deliberate — silently rewriting an
    operator's ``0`` to ``1`` hides their mistake, which is the same
    silent-config failure the legacy-name tripwire exists to prevent.
    """

    @pytest.mark.parametrize("model", [MetadataBlock, MetadataSettings])
    @pytest.mark.parametrize("value", [0, -5])
    def test_non_positive_attempts_rejected(self, model, value: int) -> None:
        """A zero or negative attempt budget fails resolution loudly."""
        with pytest.raises(ValidationError, match="classify_max_attempts"):
            model(classify_max_attempts=value)

    @pytest.mark.parametrize("model", [MetadataBlock, MetadataSettings])
    @pytest.mark.parametrize("value", [0.0, -1.0])
    def test_non_positive_timeout_rejected(self, model, value: float) -> None:
        """A zero or negative timeout fails rather than reaching httpx."""
        with pytest.raises(ValidationError, match="classify_timeout"):
            model(classify_timeout=value)

    @pytest.mark.parametrize("model", [MetadataBlock, MetadataSettings])
    def test_positive_values_accepted(self, model) -> None:
        """The bound rejects only non-positive values."""
        instance = model(classify_max_attempts=1, classify_timeout=0.5)
        assert instance.classify_max_attempts == 1
        assert instance.classify_timeout == 0.5
