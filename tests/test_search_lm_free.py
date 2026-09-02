"""Task 1.1: ``search()`` makes no language-model call.

Regression guard for ``add-grounded-answer-synthesis-3``: answering adds the
project's first query-time generation path, but ``search()`` must stay a pure
retrieval operation. Two independent guards:

1. A poison LLM installed on the shared LlamaIndex settings whose every
   attribute access, truth test, or call raises ``AssertionError``.
2. An LLM provider registry whose ``get`` raises, so any provider resolution
   inside the search path fails loudly.

Both tests must PASS today and stay green after the answering capability
lands. If either fails, ``search()`` has grown an LLM dependency and the
"answering is a distinct operation" requirement is violated.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from llama_index.core import Settings
from llama_index.core.llms.mock import MockLLM

from rag_mcp.core.ingestion import ingest_path_async
from rag_mcp.core.retrieval import search


class _PoisonLLM(MockLLM):
    """A language-model stand-in that fails on every generative touch.

    Subclasses ``MockLLM`` because LlamaIndex's ``Settings.llm`` setter runs
    ``resolve_llm``, which rejects values that are not ``LLM`` instances.
    The poison therefore hides behind a valid ``LLM`` type while every
    generation entry point raises.
    """

    max_tokens: int | None = 256

    def __getattr__(self, name: str):
        raise AssertionError(f"search() touched an LLM attribute: {name!r}")

    def __bool__(self) -> bool:
        raise AssertionError("search() truth-tested an LLM instance")

    def complete(self, *args, **kwargs):
        raise AssertionError("search() called LLM.complete")

    async def acomplete(self, *args, **kwargs):
        raise AssertionError("search() called LLM.acomplete")

    def stream_complete(self, *args, **kwargs):
        raise AssertionError("search() called LLM.stream_complete")

    async def astream_complete(self, *args, **kwargs):
        raise AssertionError("search() called LLM.astream_complete")

    def chat(self, *args, **kwargs):
        raise AssertionError("search() called LLM.chat")

    async def achat(self, *args, **kwargs):
        raise AssertionError("search() called LLM.achat")

    def predict(self, *args, **kwargs):
        raise AssertionError("search() called LLM.predict")

    async def apredict(self, *args, **kwargs):
        raise AssertionError("search() called LLM.apredict")


@pytest.fixture
def poison_llm():
    """Install the poison LLM on the shared settings, then restore it."""
    original = Settings.llm
    Settings.llm = _PoisonLLM()
    yield Settings.llm
    Settings.llm = original


async def _ingest_small_doc(tmp_path: Path) -> Path:
    """Ingest one small document into the default test collection."""
    source = tmp_path / "lm-free-doc.txt"
    source.write_text(
        "The retrieval pipeline is purely numerical. "
        "No language model participates in scoring, ranking, or assembly. " * 8,
        encoding="utf-8",
    )
    result = await ingest_path_async(str(source))
    assert result["status"] == "ok", result
    return source


async def test_search_succeeds_with_poison_llm_installed(
    tmp_path: Path, poison_llm, effective_settings
) -> None:
    """``search()`` over an ingested document never touches the poisoned LLM."""
    await _ingest_small_doc(tmp_path)

    results = search(
        "retrieval pipeline scoring",
        top_k=5,
        similarity_threshold=0.0,
        hybrid=False,
        rerank=False,
        effective_settings=effective_settings(),
    )

    assert results, "the ingested document must remain retrievable"


async def test_search_never_resolves_llm_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, effective_settings
) -> None:
    """``search()`` must not resolve any LLM provider through the registry."""

    def _boom(name: str):
        raise AssertionError(f"search() resolved an LLM provider: {name!r}")

    await _ingest_small_doc(tmp_path)

    from rag_mcp.core.providers.llm import registry as llm_registry

    monkeypatch.setattr(llm_registry, "get", _boom)

    results = search(
        "retrieval pipeline scoring",
        top_k=5,
        similarity_threshold=0.0,
        hybrid=False,
        rerank=False,
        effective_settings=effective_settings(),
    )

    assert results, "the ingested document must remain retrievable"
