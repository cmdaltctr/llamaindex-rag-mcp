"""An invalid sparse-search backend must be corrected, not just warned about.

``_validate_provider_selections`` clamps unknown provider values to a safe
default.  Six of its seven clamps target root fields, so writing to ``self`` is
correct for them.  ``hybrid_sparse_backend`` moved into the ``retrieval`` block
with the v2 nesting: the *read* was updated to ``self.retrieval.…`` but the
*write* was not, so the clamp assigned a root attribute that nothing reads.  The
warning still fired, which made the failure invisible — the log claimed a
fallback that never happened and the invalid value reached retrieval.

These tests assert the resolved value, never the log line, because the log was
the part that was already correct.
"""

from __future__ import annotations

import pytest

# This file constructs `config.Settings` directly, on purpose: it exercises
# the env-var-parsing leaf-layer validator (`_validate_provider_selections`).
# `EffectiveSettings`/the `effective_settings` fixture never runs that
# validator, so it cannot stand in here.
from rag_mcp.config import Settings

_VALID_BACKENDS = ("auto", "native", "bm25")


class TestSparseBackendFallback:
    """The nested sparse-backend clamp must correct the value it validates."""

    @pytest.mark.parametrize("bad", ["total_nonsense", "BM25", "", "sparse", "none"])
    def test_invalid_backend_falls_back_to_bm25(
        self, monkeypatch: pytest.MonkeyPatch, bad: str
    ) -> None:
        monkeypatch.setenv("RETRIEVAL__HYBRID_SPARSE_BACKEND", bad)
        settings = Settings(_env_file=None)
        assert settings.retrieval.hybrid_sparse_backend == "bm25"

    @pytest.mark.parametrize("good", _VALID_BACKENDS)
    def test_valid_backend_is_preserved(
        self, monkeypatch: pytest.MonkeyPatch, good: str
    ) -> None:
        monkeypatch.setenv("RETRIEVAL__HYBRID_SPARSE_BACKEND", good)
        settings = Settings(_env_file=None)
        assert settings.retrieval.hybrid_sparse_backend == good

    def test_clamp_does_not_create_a_root_attribute(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Pin the specific defect: the write must not land on the root model.

        A root ``hybrid_sparse_backend`` attribute is the signature of the bug —
        it means the clamp wrote somewhere no consumer reads.
        """
        monkeypatch.setenv("RETRIEVAL__HYBRID_SPARSE_BACKEND", "total_nonsense")
        settings = Settings(_env_file=None)
        assert not hasattr(settings, "hybrid_sparse_backend")

    def test_warning_names_the_nested_variable(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The operator must be told the name they can actually set."""
        monkeypatch.setenv("RETRIEVAL__HYBRID_SPARSE_BACKEND", "total_nonsense")
        with caplog.at_level("WARNING"):
            Settings(_env_file=None)
        assert "RETRIEVAL__HYBRID_SPARSE_BACKEND" in caplog.text
