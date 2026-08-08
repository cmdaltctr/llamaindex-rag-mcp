"""``OpenAILike`` providers must pass the timeout under the name it accepts.

``OpenAILike`` exposes ``timeout``; ``request_timeout`` is the spelling used by
``llama_index.llms.ollama.Ollama``.  Because ``OpenAILike`` is a pydantic model
that accepts ``**kwargs`` and ignores extras, passing ``request_timeout`` raises
nothing — the value is silently discarded and the client keeps its 60-second
default.  A three-fold timeout reduction with no error is exactly the failure a
test has to pin, so these tests assert the keyword name, not just the value.

The real package is an optional extra and is usually absent, so the tests inject
a recording stub into ``sys.modules`` rather than skipping.  That keeps the
guarantee enforced in every environment.
"""

from __future__ import annotations

import sys
import types
from typing import Any, ClassVar

import pytest


class _RecordingOpenAILike:
    """Stand-in for ``OpenAILike`` that records its construction kwargs."""

    last_kwargs: ClassVar[dict[str, Any]] = {}

    def __init__(self, **kwargs: Any) -> None:
        type(self).last_kwargs = kwargs


@pytest.fixture
def recorded_openai_like(monkeypatch: pytest.MonkeyPatch) -> type[_RecordingOpenAILike]:
    """Install a recording stub at ``llama_index.llms.openai_like.OpenAILike``.

    Returns:
        The stub class; read ``last_kwargs`` after triggering construction.
    """
    _RecordingOpenAILike.last_kwargs = {}
    module = types.ModuleType("llama_index.llms.openai_like")
    module.OpenAILike = _RecordingOpenAILike  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "llama_index.llms.openai_like", module)
    return _RecordingOpenAILike


def _assert_timeout_keyword(kwargs: dict[str, Any]) -> None:
    """Assert the timeout reached ``OpenAILike`` under a name it honours."""
    assert "request_timeout" not in kwargs, (
        "OpenAILike has no 'request_timeout' parameter — it is swallowed by "
        "**kwargs and the client silently keeps its 60s default."
    )
    assert kwargs.get("timeout") == 180.0, (
        f"expected timeout=180.0 to reach OpenAILike, got {kwargs.get('timeout')!r}"
    )


class TestOpenAILikeTimeoutKeyword:
    """Every OpenAILike construction site must use the honoured keyword."""

    def test_llamacpp_provider_passes_timeout(
        self,
        recorded_openai_like: type[_RecordingOpenAILike],
        effective_settings,
    ) -> None:
        from rag_mcp.core.providers.llm.llamacpp import build

        # Pass an explicit timeout so the assertion pins the keyword the value
        # arrives under, independent of the provider's default (which now
        # resolves from ``metadata.classify_timeout``, not a hardcoded 180s).
        build(effective_settings(), timeout=180.0)
        _assert_timeout_keyword(recorded_openai_like.last_kwargs)

    def test_openai_like_ignores_request_timeout(self) -> None:
        """Pin the upstream behaviour this test exists to defend against.

        If a future ``OpenAILike`` starts accepting ``request_timeout``, this
        test fails and the guard above can be reconsidered.
        """
        openai_like = pytest.importorskip(
            "llama_index.llms.openai_like",
            reason="optional extra; the stub-based tests cover the contract",
        )
        import inspect

        params = inspect.signature(openai_like.OpenAILike.__init__).parameters
        assert "request_timeout" not in params
        assert "timeout" in params
