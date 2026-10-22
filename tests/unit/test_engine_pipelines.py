"""Engine graph validation and execution (task 4.3).

Covers ``Engine.validate_pipeline``, ``Engine.run_pipeline`` and
``Engine.resolve_settings``: validation without side effects, a small
retrieval graph on an in-memory store, lazy answering, the answer request
limits and profile resolution through the Engine's own resolver.
"""

from __future__ import annotations

import asyncio

import pytest
from tests.unit.test_engine_pipelines_support import (
    Factory,
    FakeLLM,
    FakeResolver,
    FakeStore,
    answer_graph,
    build_engine,
    chunks,
    identity_metadata,
    retrieval_graph,
)

from omrs.core.pipelines import (
    AdmissionSnapshot,
    PipelineDefinition,
    PipelineResult,
    PipelineValidationError,
    PreflightReport,
    RunStatus,
    parse_definition,
)
from omrs.core.vectordb.identity import EmbeddingIdentity

# ── Validation ────────────────────────────────────────────────────────


def test_validation_has_no_side_effects(effective_settings) -> None:
    """Validation reads no rows, writes nothing and builds no answer model."""
    store = FakeStore(chunks())
    answer, judge = Factory(FakeLLM()), Factory(None)
    engine = build_engine(
        effective_settings(), store, answer_llm_factory=answer, verify_llm_factory=judge
    )
    snapshot = engine.validate_pipeline(answer_graph(), inputs={"query": "text"})
    assert isinstance(snapshot, AdmissionSnapshot)
    assert snapshot.order[0] == "prepare"
    report = engine.validate_pipeline(answer_graph())
    assert isinstance(report, PreflightReport) and report.ok
    assert store.writes == [] and store.counted == []
    assert (answer.calls, judge.calls) == (0, 0)


def test_validation_accepts_a_definition_object(effective_settings) -> None:
    """A parsed ``PipelineDefinition`` and a plain dict validate the same way."""
    engine = build_engine(effective_settings())
    definition = parse_definition(retrieval_graph())
    assert isinstance(definition, PipelineDefinition)
    by_object = engine.validate_pipeline(definition, inputs={"query": "q"})
    by_dict = engine.validate_pipeline(retrieval_graph(), inputs={"query": "q"})
    assert by_object.graph_identity == by_dict.graph_identity


def test_invalid_graph_names_the_node(effective_settings) -> None:
    """An unknown operation fails with a node diagnostic."""
    graph = retrieval_graph()
    graph["nodes"][1]["operation"] = "retrieve.nothing"
    engine = build_engine(effective_settings())
    with pytest.raises(PipelineValidationError) as caught:
        engine.validate_pipeline(graph)
    assert "unknown_operation" in caught.value.codes
    assert caught.value.issues[0].node_id == "dense"


def test_invalid_run_input_raises_before_side_effects(effective_settings) -> None:
    """A missing required input fails before any store read."""
    store = FakeStore(chunks())
    engine = build_engine(effective_settings(), store)
    with pytest.raises(PipelineValidationError) as caught:
        asyncio.run(engine.run_pipeline(retrieval_graph(), inputs={}))
    assert "missing_graph_input" in caught.value.codes
    assert store.counted == [] and store.writes == []


def test_validation_uses_the_collection_argument(effective_settings) -> None:
    """``collection`` sets the default collection for nodes that name none."""
    engine = build_engine(effective_settings())
    snapshot = engine.validate_pipeline(retrieval_graph(), inputs={"query": "q"}, collection="kb")
    assert snapshot.node("prepare").collection == "kb"
    default = engine.validate_pipeline(retrieval_graph(), inputs={"query": "q"})
    assert default.node("prepare").collection == "documents"


def test_embedding_identity_mismatch_is_rejected(effective_settings) -> None:
    """A collection stamped by another model fails validation; the own model passes."""
    own = EmbeddingIdentity(provider="llamacpp", model="model-a")
    meta = {
        "same": identity_metadata("llamacpp", "model-a"),
        "other": identity_metadata("llamacpp", "model-b"),
    }
    engine = build_engine(effective_settings(), FakeStore(chunks(), metadata=meta, identity=own))
    engine.validate_pipeline(retrieval_graph(), inputs={"query": "q"}, collection="same")
    with pytest.raises(PipelineValidationError) as caught:
        engine.validate_pipeline(retrieval_graph(), inputs={"query": "q"}, collection="other")
    assert "embedding_identity_mismatch" in caught.value.codes
    assert "llamacpp/model-b" in str(caught.value.issues[0].message)


def test_explicit_engine_cannot_load_named_profile(effective_settings) -> None:
    """Without a resolver, a named graph profile fails with an actionable message."""
    graph = retrieval_graph()
    graph["profile"] = "codebase"
    engine = build_engine(effective_settings())
    with pytest.raises(PipelineValidationError) as caught:
        engine.validate_pipeline(graph, inputs={"query": "q"})
    assert caught.value.codes == ("profile_resolution_failed",)
    message = caught.value.issues[0].message
    assert "codebase" in message and "profile resolver" in message


def test_unavailable_reranker_is_a_capability_issue(effective_settings) -> None:
    """A rerank node on an Engine without a reranker names the capability."""
    graph = retrieval_graph()
    graph["nodes"].append({"id": "rerank", "operation": "select.rerank"})
    graph["edges"][1]["target"] = {"node": "rerank", "port": "evidence"}
    graph["edges"].append(
        {
            "source": {"node": "rerank", "port": "evidence"},
            "target": {"node": "select", "port": "evidence"},
        }
    )
    engine = build_engine(effective_settings())
    with pytest.raises(PipelineValidationError) as caught:
        engine.validate_pipeline(graph)
    assert caught.value.codes == ("capability_unavailable",)
    assert caught.value.issues[0].node_id == "rerank"


# ── Execution ─────────────────────────────────────────────────────────


def test_retrieval_graph_runs_on_the_engine_store(effective_settings) -> None:
    """The graph reads the Engine's store and embedder and returns its context."""
    store = FakeStore(chunks())
    events = []

    async def sink(event) -> None:
        events.append(event.kind)

    engine = build_engine(effective_settings(), store)
    result = asyncio.run(
        engine.run_pipeline(retrieval_graph(top_k=2), inputs={"query": "text"}, on_event=sink)
    )
    assert isinstance(result, PipelineResult)
    assert result.status is RunStatus.SUCCEEDED, result.error
    rows = result.outputs["context"].public_rows()
    assert [r["source_id"] for r in rows] == ["doc-s0", "doc-s1"]
    assert store.counted == ["documents"] and store.writes == []
    assert events[-1] == "run_completed"


def test_caller_cancellation_is_run_scoped(effective_settings) -> None:
    """A cancelled caller token cancels that run only."""
    from omrs.core.pipelines import RunCancellation

    engine = build_engine(effective_settings())
    token = RunCancellation()
    token.cancel("user request")

    async def both() -> tuple[PipelineResult, PipelineResult]:
        first = await engine.run_pipeline(
            retrieval_graph(), inputs={"query": "q"}, cancellation=token
        )
        second = await engine.run_pipeline(retrieval_graph(), inputs={"query": "q"})
        return first, second

    first, second = asyncio.run(both())
    assert first.status is RunStatus.CANCELLED
    assert second.status is RunStatus.SUCCEEDED


# ── Lazy answering ────────────────────────────────────────────────────


def test_retrieval_graph_never_builds_answer_models(effective_settings) -> None:
    """A retrieval-only graph leaves the answer and judge factories untouched."""
    answer, judge = Factory(error=AssertionError("built")), Factory(error=AssertionError("built"))
    engine = build_engine(effective_settings(), answer_llm_factory=answer, verify_llm_factory=judge)
    result = asyncio.run(engine.run_pipeline(retrieval_graph(), inputs={"query": "q"}))
    assert result.status is RunStatus.SUCCEEDED
    assert (answer.calls, judge.calls) == (0, 0)


def test_empty_evidence_answer_graph_never_builds_answer_models(
    effective_settings,
) -> None:
    """An answer graph over an empty collection returns no-evidence without a model."""
    answer, judge = Factory(error=AssertionError("built")), Factory(error=AssertionError("built"))
    engine = build_engine(
        effective_settings(),
        FakeStore([]),
        answer_llm_factory=answer,
        verify_llm_factory=judge,
    )
    result = asyncio.run(engine.run_pipeline(answer_graph(), inputs={"query": "q"}))
    assert result.status is RunStatus.SUCCEEDED, result.error
    assert result.outputs["answer"]["status"] == "no_evidence"
    assert (answer.calls, judge.calls) == (0, 0)


def test_answer_model_is_built_once_and_shared_with_engine_answer(
    effective_settings,
) -> None:
    """The graph builds the answer model on first use and caches it per Engine."""
    llm = FakeLLM()
    answer = Factory(llm)
    engine = build_engine(effective_settings(), answer_llm_factory=answer)

    async def twice() -> list[PipelineResult]:
        return [
            await engine.run_pipeline(answer_graph(), inputs={"query": "text"}) for _ in range(2)
        ]

    results = asyncio.run(twice())
    assert [r.status for r in results] == [RunStatus.SUCCEEDED] * 2
    assert results[0].outputs["answer"]["answer"]
    assert answer.calls == 1 and len(llm.prompts) == 2
    assert engine._answer_llm is llm


def test_answer_chain_accepts_assembled_context_without_a_bridge(effective_settings) -> None:
    """context.assemble -> answer.prepare_evidence runs without a test bridge."""
    engine = build_engine(effective_settings(), answer_llm_factory=Factory(FakeLLM()))
    result = asyncio.run(engine.run_pipeline(answer_graph(), inputs={"query": "text"}))
    assert result.status is RunStatus.SUCCEEDED, result.error


def test_verify_resource_builds_each_judge_once(effective_settings) -> None:
    """The verify_llm resource caches the judge per answer block, like answer_llm."""
    judge_model = object()
    judge = Factory(judge_model)
    engine = build_engine(effective_settings(), verify_llm_factory=judge)
    build = engine._graph_host(None).resources["verify_llm"]
    block = effective_settings().answer
    assert build(block) is judge_model and build(block) is judge_model
    assert judge.calls == 1
    assert "answer_llm" not in engine._graph_host(None).resources


# ── Request limits ────────────────────────────────────────────────────


def test_answer_query_length_limit(effective_settings) -> None:
    """An answer graph rejects a query over the answer() character limit."""
    store = FakeStore(chunks())
    answer = Factory(FakeLLM())
    engine = build_engine(effective_settings(), store, answer_llm_factory=answer)
    with pytest.raises(PipelineValidationError) as caught:
        asyncio.run(engine.run_pipeline(answer_graph(), inputs={"query": "x" * 4097}))
    assert caught.value.codes == ("invalid_parameter",)
    assert "4096" in caught.value.issues[0].message
    assert store.counted == [] and answer.calls == 0
    engine.validate_pipeline(answer_graph(), inputs={"query": "x" * 4096})


def test_answer_top_k_limit_on_node_and_graph_override(effective_settings) -> None:
    """``top_k`` above the answer() limit fails on a node or graph-wide."""
    engine = build_engine(effective_settings())
    with pytest.raises(PipelineValidationError) as caught:
        engine.validate_pipeline(answer_graph(top_k=101))
    issue = caught.value.issues[0]
    assert (issue.code, issue.node_id) == ("invalid_parameter", "prepare")
    assert "between 1 and 100" in issue.message
    graph = answer_graph()
    graph["overrides"] = {"retrieval.top_k": 500}
    with pytest.raises(PipelineValidationError) as caught:
        engine.validate_pipeline(graph, inputs={"query": "q"})
    issue = caught.value.issues[0]
    assert (issue.code, issue.lever) == ("invalid_override", "retrieval.top_k")
    engine.validate_pipeline(answer_graph(top_k=100), inputs={"query": "q"})


def test_retrieval_graph_keeps_search_limits(effective_settings) -> None:
    """The answer limits apply to answering graphs only, as for Engine.search()."""
    engine = build_engine(effective_settings())
    engine.validate_pipeline(retrieval_graph(top_k=150), inputs={"query": "x" * 5000})


# ── Public settings accessor ──────────────────────────────────────────


def test_resolve_settings_uses_the_engine_resolver(effective_settings) -> None:
    """Each collection gets its own resolved profile; the default uses settings."""
    base = effective_settings(collection_name="docs")
    docs = effective_settings(profile_name="documents", top_k=7)
    code = effective_settings(profile_name="codebase", top_k=3)
    resolver = FakeResolver({"docs": docs, "code": code})
    engine = build_engine(base, profile_resolver=resolver)
    assert engine.resolve_settings("docs") is docs
    assert engine.resolve_settings("code") is code
    assert engine.resolve_settings() is docs
    plain = build_engine(base)
    assert plain.resolve_settings("anything") is base
