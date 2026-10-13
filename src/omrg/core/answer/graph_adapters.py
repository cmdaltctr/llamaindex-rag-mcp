"""Graph adapters for the Answer / verify operation family.

Task 3.6 of ``add-local-web-pipeline-workspace`` (design D3, D4, D6).
Four operations wrap the answer seams in :mod:`.stages` and build every
answer value with the builders in :mod:`.results`. A graph answer
therefore has the same shape, status set and verification labels as
``Engine.answer``. The adapters hold no second copy of any rule.

Canonical order::

    answer.prepare_evidence -> answer.synthesise -> answer.cite -> verify.claims

Each ``answer`` port value is the public answer result dict. A later node
reads the dict and returns a new one. A node passes a value through
unchanged when there is no answer text (no evidence, no provider,
switched off, or a failed stage) or when the answer is already verified.

Resources come only from :meth:`NodeContext.resource`, and only when a
node needs them:

* ``answer_llm``: a callable with no arguments. It returns an LLM with
  ``async acomplete(prompt)``, an async ``prompt -> str`` seam, or
  ``None`` when no model is configured. A missing resource also means no
  model. Empty evidence never looks up this resource.
* ``verify_llm``: a callable that takes the answer settings block. It
  returns the same kinds of value. If it raises, verification is skipped
  with the redacted reason. It is looked up only for a grounded answer
  with ``answer.verify_claims`` on.

Settings come only from ``context.settings``. ``retrieval_ms`` is
``0.0`` in diagnostics, because retrieval nodes run before these nodes.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from pydantic import BaseModel, ConfigDict

from ..pipelines import (
    BypassSpec,
    EffectClass,
    NodeContext,
    NodeOutput,
    OperationCatalogue,
    OperationDescriptor,
    PortKind,
    PortSpec,
    PortType,
    Provenance,
)
from .results import (
    answered_result,
    disabled_result,
    generation_diagnostics,
    no_evidence_result,
    no_provider_result,
    stage_failure_result,
    zero_generation_diagnostics,
)
from .stages import (
    NO_VERIFICATION,
    error_detail_for,
    prepare_evidence,
    resolve_citations,
    safe_error_detail,
    synthesise_answer,
    verify_answer,
)
from .synthesis import CompletionSeam

#: Engine resource names (agreed for every graph adapter).
ANSWER_LLM_RESOURCE = "answer_llm"
VERIFY_LLM_RESOURCE = "verify_llm"

#: Graph answers are produced by the server-side model, as ``Engine.answer``.
COMPLETION_SOURCE = "server"

#: Same wording ``Engine.answer`` uses when the judge factory returns ``None``.
NO_JUDGE_REASON = "verification provider unavailable (no judge configured)"

_VERIFICATION_KEYS = ("verified", "verification_skipped", "unverified_claims")
_LINEAGE = frozenset({Provenance.CHUNK_LINEAGE})
_CONTEXT = PortType(PortKind.CONTEXT, provenance=_LINEAGE)
_QUERY = PortType(PortKind.QUERY)
#: Synthesised answer whose citations are not resolved yet.
_DRAFT = PortType(PortKind.ANSWER)
#: Answer whose citations resolve to the supplied chunk lineage.
_CITED = PortType(PortKind.ANSWER, provenance=_LINEAGE)


class _Params(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PrepareEvidenceParams(_Params):
    """``answer.prepare_evidence`` has no parameters."""


class SynthesiseParams(_Params):
    """Parameters of ``answer.synthesise``.

    Attributes:
        include_diagnostics: Add generation timings and call counts.
    """

    include_diagnostics: bool = False


class CiteParams(_Params):
    """``answer.cite`` has no parameters."""


class VerifyClaimsParams(_Params):
    """Parameters of ``verify.claims``.

    Attributes:
        verify_claims: Node override of the ``answer.verify_claims``
            lever. ``None`` inherits. Admission applies the value to the
            node settings, so the adapter reads only ``context.settings``.
    """

    verify_claims: bool | None = None


def _as_seam(target: Any) -> CompletionSeam | None:
    """Adapt an LLM or a completion seam to the async seam shape."""
    if target is None:
        return None
    if hasattr(target, "acomplete"):
        llm = target

        async def seam(prompt: str) -> str:
            completion = await llm.acomplete(prompt)
            return completion.text

        return seam
    return cast(CompletionSeam, target)


def _answer_seam(context: NodeContext) -> CompletionSeam | None:
    """Resolve the answer model now; a missing resource means no model."""
    try:
        factory = context.resource(ANSWER_LLM_RESOURCE)
    except LookupError:
        return None
    return None if factory is None else _as_seam(factory())


def _judge_seam(context: NodeContext) -> tuple[CompletionSeam | None, str | None]:
    """Resolve the judge now; return ``(seam, unavailable_reason)``."""
    try:
        factory = context.resource(VERIFY_LLM_RESOURCE)
    except LookupError:
        return None, None
    if factory is None:
        return None, None
    try:
        target = factory(context.settings.answer)
    except Exception as exc:  # A host that cannot build a judge degrades.
        detail = safe_error_detail(exc, context.settings)
        return None, f"verification provider unavailable: {type(exc).__name__}: {detail}"
    seam = _as_seam(target)
    return (seam, None) if seam is not None else (None, NO_JUDGE_REASON)


def _output(result: dict[str, Any], **summary: Any) -> NodeOutput:
    """Wrap an answer result dict as the node's ``answer`` output."""
    summary = {"status": result["status"], "failure_stage": result["failure_stage"], **summary}
    return NodeOutput(values={"answer": result}, summary=summary)


def _has_answer_text(result: Mapping[str, Any]) -> bool:
    return result.get("answer") is not None


def _is_verified(result: Mapping[str, Any]) -> bool:
    return any(key in result for key in _VERIFICATION_KEYS)


def _diagnostics(result: Mapping[str, Any]) -> dict[str, Any] | None:
    diagnostics = result.get("diagnostics")
    return None if diagnostics is None else dict(diagnostics)


def _context_rows(value: Any) -> Any:
    """Return context rows from a retrieval bundle or a plain row sequence.

    ``context.assemble`` emits a bundle with ``public_rows()``, the same
    row shape ``search()`` returns to ``Engine.answer``. Duck typing keeps
    this module free of a retrieval import (answer-graph-adapters-stay-in-domain).
    """
    public_rows = getattr(value, "public_rows", None)
    return public_rows() if callable(public_rows) else value


async def prepare_evidence_adapter(
    context: NodeContext, inputs: Mapping[str, Any], params: BaseModel
) -> NodeOutput:
    """Number context rows and keep their chunk lineage (pure)."""
    evidence = prepare_evidence(_context_rows(inputs["context"]))
    return NodeOutput(values={"context": evidence}, summary={"evidence": len(evidence)})


async def synthesise_adapter(
    context: NodeContext, inputs: Mapping[str, Any], params: BaseModel
) -> NodeOutput:
    """Synthesise an answer over the context, or return the existing outcome.

    Order: master switch, evidence numbering, no-evidence short circuit,
    then the answer model. The model is resolved only after evidence is
    present. A generation failure is a ``failure_stage="generation"``
    result that keeps the evidence; it is not an exception.
    """
    options = cast(SynthesiseParams, params)
    query: str = inputs["query"]
    settings = context.settings
    block = settings.answer
    if not block.enabled:
        return _output(disabled_result(query, COMPLETION_SOURCE))
    # Idempotent: prepared rows stay the same, raw rows get numbered.
    evidence = prepare_evidence(_context_rows(inputs["context"]))
    no_generation = zero_generation_diagnostics(0.0) if options.include_diagnostics else None
    if not evidence:
        return _output(no_evidence_result(query, COMPLETION_SOURCE, diagnostics=no_generation))
    complete = _answer_seam(context)
    if complete is None:
        return _output(
            no_provider_result(query, COMPLETION_SOURCE, evidence, diagnostics=no_generation)
        )
    synthesis = await synthesise_answer(
        query,
        evidence,
        complete=complete,
        answer_block=block,
        error_detail=error_detail_for(settings),
    )
    diagnostics = (
        generation_diagnostics(0.0, synthesis.ms, synthesis.completion_calls)
        if options.include_diagnostics
        else None
    )
    calls = {"completion_calls": synthesis.completion_calls}
    if synthesis.text is None:
        failed = stage_failure_result(
            query,
            COMPLETION_SOURCE,
            failure_stage=synthesis.failure_stage,
            error=synthesis.error or "Generation failed: no answer text",
            evidence=evidence,
            diagnostics=diagnostics,
        )
        return _output(failed, **calls)
    draft = answered_result(
        query,
        COMPLETION_SOURCE,
        text=synthesis.text,
        citations=[],
        grounded=False,
        evidence=evidence,
        verification=NO_VERIFICATION,
        diagnostics=diagnostics,
    )
    return _output(draft, **calls)


async def cite_adapter(
    context: NodeContext, inputs: Mapping[str, Any], params: BaseModel
) -> NodeOutput:
    """Resolve citation ordinals to the supplied evidence lineage (pure).

    Absurd model output becomes a ``failure_stage="generation"`` result,
    as in ``answer()``.
    """
    result = inputs["answer"]
    if not _has_answer_text(result) or _is_verified(result):
        return _output(result, citations=len(result.get("citations") or []))
    text, evidence = result["answer"], result["evidence"]
    cites = resolve_citations(text, evidence, error_detail=error_detail_for(context.settings))
    query, source = result["query"], result["completion_source"]
    if cites.error is not None:
        failed = stage_failure_result(
            query,
            source,
            failure_stage=cites.failure_stage,
            error=cites.error,
            evidence=evidence,
            diagnostics=_diagnostics(result),
        )
        return _output(failed, citations=0)
    cited = answered_result(
        query,
        source,
        text=text,
        citations=cites.citations,
        grounded=cites.grounded,
        evidence=evidence,
        verification=NO_VERIFICATION,
        diagnostics=_diagnostics(result),
    )
    return _output(cited, citations=len(cites.citations))


def _verification_label(result: Mapping[str, Any]) -> str:
    if "unverified_claims" in result:
        return "failing"
    if "verification_skipped" in result:
        return "skipped"
    return "verified" if result.get("verified") else "not_run"


async def verify_claims_adapter(
    context: NodeContext, inputs: Mapping[str, Any], params: BaseModel
) -> NodeOutput:
    """Run opt-in claim verification on a cited, grounded answer.

    The judge is resolved only when ``answer.verify_claims`` is on and
    the answer is grounded (status ``ok``). A missing or failing judge is
    an explicit ``verification_skipped`` outcome with the actual reason,
    reported as the node fallback. It is never an exception.
    """
    result = inputs["answer"]
    block = context.settings.answer
    grounded = result.get("status") == "ok"
    runs = _has_answer_text(result) and not _is_verified(result)
    if not (runs and grounded and getattr(block, "verify_claims", False)):
        return _output(result, verification=_verification_label(result))
    judge, reason = _judge_seam(context)
    verification = await verify_answer(
        result["answer"],
        result["evidence"],
        grounded=grounded,
        answer_block=block,
        verify_complete=judge,
        unavailable_reason=reason,
        error_detail=error_detail_for(context.settings),
    )
    checked = answered_result(
        result["query"],
        result["completion_source"],
        text=result["answer"],
        citations=result["citations"],
        grounded=grounded,
        evidence=result["evidence"],
        verification=verification,
        diagnostics=_diagnostics(result),
    )
    output = _output(checked, verification=_verification_label(checked))
    return NodeOutput(
        values=output.values, summary=output.summary, fallback=verification.skipped_reason
    )


def _port(name: str, port_type: PortType, description: str) -> PortSpec:
    return PortSpec(name=name, type=port_type, description=description)


PREPARE_EVIDENCE = OperationDescriptor(
    operation_id="answer.prepare_evidence",
    version=1,
    title="Prepare evidence",
    family="answer",
    description="Number context rows for citation and keep their chunk lineage.",
    parameters=PrepareEvidenceParams,
    inputs=(_port("context", _CONTEXT, "Context rows in rank order."),),
    outputs=(_port("context", _CONTEXT, "Numbered evidence rows."),),
    effect=EffectClass.PURE,
)

SYNTHESISE = OperationDescriptor(
    operation_id="answer.synthesise",
    version=1,
    title="Synthesise answer",
    family="answer",
    description=(
        "Write an answer from the context with the answer model. Empty context "
        "returns the no-evidence outcome without a model call."
    ),
    parameters=SynthesiseParams,
    inputs=(
        _port("query", _QUERY, "The question."),
        _port("context", _CONTEXT, "Context or prepared evidence rows."),
    ),
    outputs=(_port("answer", _DRAFT, "Answer result; citations not resolved yet."),),
    effect=EffectClass.MODEL_CALL,
)

CITE = OperationDescriptor(
    operation_id="answer.cite",
    version=1,
    title="Resolve citations",
    family="answer",
    description="Map citation numbers in the answer to the supplied chunk lineage.",
    parameters=CiteParams,
    inputs=(_port("answer", _DRAFT, "Synthesised answer result."),),
    outputs=(_port("answer", _CITED, "Answer result with resolved citations."),),
    effect=EffectClass.PURE,
)

VERIFY_CLAIMS = OperationDescriptor(
    operation_id="verify.claims",
    version=1,
    title="Verify claims",
    family="verify",
    description=(
        "Opt-in claim check with the judge model. A missing or failing judge "
        "reports verification_skipped with its reason."
    ),
    parameters=VerifyClaimsParams,
    inputs=(_port("answer", _CITED, "Answer result with resolved citations."),),
    outputs=(_port("answer", _CITED, "Answer result with verification labels."),),
    effect=EffectClass.MODEL_CALL,
    bypass=BypassSpec(input_port="answer", output_port="answer"),
    lever_params={"verify_claims": "answer.verify_claims"},
)


def register_answer_operations(catalogue: OperationCatalogue) -> None:
    """Register the Answer / verify operations in *catalogue*.

    Args:
        catalogue: The catalogue the composition root builds.

    Raises:
        ValueError: If an answer operation version is already registered.
    """
    catalogue.register(PREPARE_EVIDENCE, prepare_evidence_adapter)
    catalogue.register(SYNTHESISE, synthesise_adapter)
    catalogue.register(CITE, cite_adapter)
    catalogue.register(VERIFY_CLAIMS, verify_claims_adapter)
