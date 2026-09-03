"""Slow end-to-end answer quality gate over the golden corpus (task 7.1).

Ingests the committed quality corpus, answers the first golden query with a
real local answer model (Ollama via the answer settings), and asserts the
result is grounded and cites a chunk from the expected source file. Skips
cleanly when no answer provider is configured or Ollama is not running.

Follow-up (task 7.2, deliberately out of scope here): now that a
generation step exists to hold constant, run a faithfulness /
answer-relevance / context-recall experiment through the experiments/
process against this same corpus — retrieval and generation quality can
finally be measured separately.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.quality.runner import CORPUS_DIR, load_golden_queries

from rag_mcp.compose import build_answer_llm
from rag_mcp.core.answer import answer
from rag_mcp.core.ingestion import ingest_path_async

pytestmark = pytest.mark.slow

_COLLECTION = "answer_quality_slow"

# Generation failures that describe an environment without a usable
# model (Ollama down, or the configured answer model not pulled) skip
# rather than fail — the gate is about citation quality, not setup.
_CONNECTION_MARKERS = ("connect", "connection", "refused", "unreachable", "not found")


async def test_golden_query_answer_cites_the_expected_source() -> None:
    """The first golden query is answered with a citation into the expected source."""
    golden = load_golden_queries()[0]

    llm = build_answer_llm()
    if llm is None:
        pytest.skip("No answer provider configured")

    ingested = await ingest_path_async(str(CORPUS_DIR), collection_name=_COLLECTION)
    assert ingested["status"] == "ok", ingested

    async def _complete(prompt: str) -> str:
        """Adapt the injected LLM to the answer operation's async seam."""
        completion = await llm.acomplete(prompt)
        return completion.text

    result = await answer(
        golden["query"],
        collection_name=_COLLECTION,
        similarity_threshold=0.0,
        top_k=10,
        complete=_complete,
    )

    if result["status"] == "error" and result["failure_stage"] == "generation":
        message = (result.get("error") or "").lower()
        if any(marker in message for marker in _CONNECTION_MARKERS):
            pytest.skip("Ollama not running")

    assert result["status"] == "ok", result
    assert result["citations"], "a grounded answer must carry at least one citation"
    cited_basenames = {Path(citation["source"]).name for citation in result["citations"]}
    assert cited_basenames & set(golden["expected_sources"]), (
        f"cited sources {sorted(cited_basenames)} do not include the expected "
        f"{golden['expected_sources']}"
    )
