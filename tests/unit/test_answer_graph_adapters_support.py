"""Shared helpers for the answer graph-adapter tests (task 3.6).

No graph runner exists yet, so these helpers chain the registered
adapters by hand in the canonical order: ``answer.prepare_evidence`` ->
``answer.synthesise`` -> ``answer.cite`` -> ``verify.claims``. Model
resources are fakes that count each lazy resolution. This module holds
no tests.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from tests.fixtures.pipeline_parity.answer.harness import QUERY, ScriptedSeam, make_seam

from omrs.core.answer.graph_adapters import (
    ANSWER_LLM_RESOURCE,
    VERIFY_LLM_RESOURCE,
    register_answer_operations,
)
from omrs.core.pipelines import CancellationFlag, NodeContext, NodeOutput, OperationCatalogue

PREPARE = "answer.prepare_evidence"
SYNTHESISE = "answer.synthesise"
CITE = "answer.cite"
VERIFY = "verify.claims"


@dataclass(frozen=True)
class FakeCompletion:
    """Completion response double with the ``text`` attribute only."""

    text: str


class FakeLLM:
    """LLM double: ``acomplete`` forwards the prompt to a scripted seam."""

    def __init__(self, seam: ScriptedSeam) -> None:
        """Wrap *seam*; nothing runs until ``acomplete`` is awaited."""
        self.seam = seam

    async def acomplete(self, prompt: str) -> FakeCompletion:
        """Return the scripted reply as a completion response."""
        return FakeCompletion(await self.seam(prompt))


class CountingFactory:
    """Lazy LLM resource double that records every resolution.

    Args:
        llm: Value to return, or ``None`` for "no model configured".
        error: Exception to raise on each call instead, if set.
    """

    def __init__(self, llm: Any, *, error: BaseException | None = None) -> None:
        """Store the return value or error; record no call yet."""
        self.llm = llm
        self.error = error
        self.calls: list[tuple[Any, ...]] = []

    def __call__(self, *args: Any) -> Any:
        """Record the call, then raise or return the configured LLM."""
        self.calls.append(args)
        if self.error is not None:
            raise self.error
        return self.llm


def build_catalogue() -> OperationCatalogue:
    """Return a catalogue that holds only the answer family."""
    catalogue = OperationCatalogue()
    register_answer_operations(catalogue)
    return catalogue


CATALOGUE = build_catalogue()


def node_context(settings: Any, resources: Mapping[str, Any], node_id: str) -> NodeContext:
    """Build an explicit node context for one hand-run node."""
    return NodeContext(
        run_id="run-test",
        node_id=node_id,
        settings=settings,
        resources=resources,
        cancellation=CancellationFlag(),
    )


async def run_node(
    operation_id: str,
    settings: Any,
    resources: Mapping[str, Any],
    inputs: Mapping[str, Any],
    **params: Any,
) -> NodeOutput:
    """Run one registered answer operation through its adapter."""
    entry = CATALOGUE.get(operation_id)
    assert entry is not None, operation_id
    model = entry.descriptor.parameters(**params)
    context = node_context(settings, resources, operation_id.replace(".", "_"))
    return await entry.adapter(context, inputs, model)


async def run_answer_chain(
    settings: Any,
    rows: list[dict],
    resources: Mapping[str, Any],
    *,
    query: str = QUERY,
    include_diagnostics: bool = True,
    with_prepare: bool = True,
) -> dict[str, Any]:
    """Chain the four answer operations by hand and return the final result."""
    outputs = await run_answer_chain_outputs(
        settings,
        rows,
        resources,
        query=query,
        include_diagnostics=include_diagnostics,
        with_prepare=with_prepare,
    )
    return dict(outputs[VERIFY].values["answer"])


async def run_answer_chain_outputs(
    settings: Any,
    rows: list[dict],
    resources: Mapping[str, Any],
    *,
    query: str = QUERY,
    include_diagnostics: bool = True,
    with_prepare: bool = True,
) -> dict[str, NodeOutput]:
    """Chain the answer operations by hand and return every node output."""
    outputs: dict[str, NodeOutput] = {}
    context_value: Any = rows
    if with_prepare:
        outputs[PREPARE] = await run_node(PREPARE, settings, resources, {"context": rows})
        context_value = outputs[PREPARE].values["context"]
    outputs[SYNTHESISE] = await run_node(
        SYNTHESISE,
        settings,
        resources,
        {"query": query, "context": context_value},
        include_diagnostics=include_diagnostics,
    )
    outputs[CITE] = await run_node(
        CITE, settings, resources, {"answer": outputs[SYNTHESISE].values["answer"]}
    )
    outputs[VERIFY] = await run_node(
        VERIFY, settings, resources, {"answer": outputs[CITE].values["answer"]}
    )
    return outputs


def case_resources(
    case: dict[str, Any],
) -> tuple[dict[str, Any], ScriptedSeam | None, ScriptedSeam | None]:
    """Build lazy resources for a parity case.

    A case with ``verify_unavailable_reason`` gets a judge factory that
    raises, which is how a host reports a provider it cannot build.

    Returns:
        ``(resources, complete_seam, judge_seam)``.
    """
    complete = make_seam(case.get("complete"))
    judge = make_seam(case.get("judge"))
    judge_factory = CountingFactory(FakeLLM(judge) if judge else None)
    if case.get("verify_unavailable_reason"):
        judge_factory = CountingFactory(None, error=ValueError(UNKNOWN_PROVIDER))
    resources = {
        ANSWER_LLM_RESOURCE: CountingFactory(FakeLLM(complete) if complete else None),
        VERIFY_LLM_RESOURCE: judge_factory,
    }
    return resources, complete, judge


#: Error text the raising judge factory uses for the transport-reason case.
UNKNOWN_PROVIDER = "unknown provider 'nope'"
