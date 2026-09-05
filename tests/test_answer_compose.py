"""Composition-root tests for the answer model builder (tasks 3.1-3.3 slice).

Pins ``compose.build_answer_llm``: ``None`` when answering is disabled, a
``ValueError`` naming an unknown provider, a real Ollama construction
honouring the answer block's model, the backwards-compatible
``answer_model`` override on every registered provider builder, and the
graceful-degradation contract (task 3.2): a missing optional provider
dependency resolves to ``None``, never an exception, while missing
credentials stay loud.
"""

from __future__ import annotations

import importlib.util
import inspect

import pytest

from omrg import compose

# Ollama constructs without network access; it is the local-first default
# provider, so the real builder is exercised rather than a stub.
_OLLAMA_MODEL = "qwen3:4b"


def test_build_answer_llm_returns_none_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Answering disabled resolves to no model, not an error."""
    monkeypatch.setenv("ANSWER__ENABLED", "false")

    assert compose.build_answer_llm() is None


def test_unknown_provider_raises_value_error_naming_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unregistered provider name fails fast, naming it."""
    monkeypatch.setenv("ANSWER__ENABLED", "true")
    monkeypatch.setenv("ANSWER__PROVIDER", "definitely-not-a-provider")

    with pytest.raises(ValueError, match="definitely-not-a-provider"):
        compose.build_answer_llm()


def test_ollama_builder_uses_the_answer_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """The ollama construction reflects the answer block's model, not another's."""
    monkeypatch.setenv("ANSWER__ENABLED", "true")
    monkeypatch.setenv("ANSWER__PROVIDER", "ollama")
    monkeypatch.setenv("ANSWER__MODEL", _OLLAMA_MODEL)

    llm = compose.build_answer_llm()

    assert llm is not None
    model = getattr(llm, "model", None) or getattr(llm, "model_name", "")
    assert model == _OLLAMA_MODEL


def test_every_registered_builder_accepts_answer_model_kwarg() -> None:
    """Every provider builder gains the backwards-compatible override."""
    from omrg.core.providers.llm import llamacpp, ollama, openrouter

    for module in (ollama, llamacpp, openrouter):
        params = inspect.signature(module.build).parameters
        assert "answer_model" in params, f"{module.__name__}.build must accept answer_model"
        assert params["answer_model"].default is None, (
            f"{module.__name__}.build's answer_model must default to None so "
            "existing callers stay source-compatible"
        )


# ── Graceful degradation (task 3.2, security finding F6) ──────────────
#
# Optional provider SDKs are imported lazily INSIDE the builder's
# ``build(...)`` call, so the missing-package signal arrives as
# ``ModuleNotFoundError`` from the build call, not from registry
# resolution.  A retrieval-only deployment must stay usable.


def _enable_llamacpp(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the answer block at the llamacpp provider (never built for real)."""
    monkeypatch.setenv("ANSWER__ENABLED", "true")
    monkeypatch.setenv("ANSWER__PROVIDER", "llamacpp")


def test_builder_missing_package_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """A ModuleNotFoundError from the builder resolves to ``None``."""
    from omrg.core.providers.llm import registry

    def _build_without_extra(*args: object, **kwargs: object) -> object:
        raise ModuleNotFoundError("No module named 'llama_index.llms.openai_like'")

    _enable_llamacpp(monkeypatch)
    monkeypatch.setattr(registry, "get", lambda name: _build_without_extra)

    assert compose.build_answer_llm() is None


def test_builder_missing_credentials_still_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """A configuration ImportError (missing credentials) stays loud."""
    from omrg.core.providers.llm import registry

    def _build_without_key(*args: object, **kwargs: object) -> object:
        raise ImportError("openrouter_api_key is required but not configured")

    _enable_llamacpp(monkeypatch)
    monkeypatch.setattr(registry, "get", lambda name: _build_without_key)

    with pytest.raises(ImportError, match="openrouter_api_key"):
        compose.build_answer_llm()


@pytest.mark.skipif(
    importlib.util.find_spec("llama_index.llms.openai_like") is not None,
    reason="the llamacpp optional extra is installed; live gap not reproducible",
)
def test_live_missing_extra_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """Live reproduction: llamacpp chosen without its extra yields ``None``.

    Exercises the real lazy import inside the real builder — the exact
    path that crashed retrieval-only deployments before the fix.
    """
    _enable_llamacpp(monkeypatch)

    assert compose.build_answer_llm() is None
