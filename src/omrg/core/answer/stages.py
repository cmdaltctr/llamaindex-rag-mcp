"""Answer stage seams: evidence, synthesis, citations and verification.

Each seam is one step of grounded answering that the standard
``answer()`` operation calls in order.  Graph adapters call the same
functions, so there is one implementation of each step (design D4).

The seams take every resource as an argument: the completion and judge
seams, the frozen answer settings block, and a credential-safe error
redactor.  They never read process-default settings and never build a
model (design D6: answer and judge resources stay lazy and are owned by
the caller).  Synthesis and citation resolution return an outcome with a
``failure_stage`` instead of raising, and verification never raises, so
an adapter keeps the existing failure attribution without new logic.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from .citations import build_citations, parse_citation_ordinals
from .evidence import _evidence_rows, _labelled_nodes
from .synthesis import CompletionSeam, run_synthesis
from .verify import VerificationFields, run_verification_stage

#: Failure-stage labels carried in ``failure_stage`` (spec contract).
FAILURE_STAGE_RETRIEVAL = "retrieval"
FAILURE_STAGE_GENERATION = "generation"

#: Shared no-op outcome for the disabled or skipped verification path.
NO_VERIFICATION = VerificationFields()

#: Redactor that turns an exception into a credential-safe detail string.
ErrorDetail = Callable[[BaseException], str]

#: Synthesis runner shape (``run_synthesis`` by default).
SynthesisRunner = Callable[..., Awaitable[tuple[str, int]]]


def safe_error_detail(exc: BaseException, settings: Any) -> str:
    """Format an exception for the result without leaking credentials.

    Provider and connection errors can echo key material (an OpenRouter
    key inside a URL, Chroma Cloud connection values); the same redaction
    helpers the MCP transport applies to tool errors are applied here so
    the error strings embedded in core results cannot bypass them.
    """
    from ..settings import provider_secret_values
    from ..vectordb.identity import redact_cloud_secrets, redact_secrets

    detail = str(exc)
    detail = redact_cloud_secrets(
        detail,
        getattr(settings, "chroma_cloud_api_key", ""),
        getattr(settings, "chroma_cloud_tenant", ""),
        getattr(settings, "chroma_cloud_database", ""),
    )
    return redact_secrets(detail, provider_secret_values(settings))


def error_detail_for(settings: Any) -> ErrorDetail:
    """Return a redactor bound to the injected *settings*."""
    return lambda exc: safe_error_detail(exc, settings)


def prepare_evidence(rows: Sequence[dict]) -> list[dict]:
    """Normalise ``search()`` rows into numbered evidence rows.

    An empty input gives an empty list: empty results are valid data,
    and the caller returns its no-evidence outcome without a model call.

    Args:
        rows: Authoritative ``search()`` rows, in rank order.

    Returns:
        Evidence rows with lineage, 1-based ``ordinal``, merged
        ``chunk_ids`` and text.  The input rows are not changed.
    """
    return _evidence_rows(list(rows))


@dataclass(frozen=True)
class SynthesisOutcome:
    """Result of the synthesis seam.

    Attributes:
        text: The answer text, or ``None`` when generation failed.
        completion_calls: Completion calls made (attempts before the
            failure when generation failed).
        ms: Wall-time of the synthesis run.
        error: Redacted, actionable message when generation failed.
    """

    text: str | None
    completion_calls: int
    ms: float
    error: str | None = None

    @property
    def failure_stage(self) -> str | None:
        """``"generation"`` when synthesis failed, else ``None``."""
        return FAILURE_STAGE_GENERATION if self.error is not None else None


async def synthesise_answer(
    query: str,
    evidence: list[dict],
    *,
    complete: CompletionSeam,
    answer_block: Any,
    error_detail: ErrorDetail,
    runner: SynthesisRunner = run_synthesis,
) -> SynthesisOutcome:
    """Synthesise an answer over *evidence* through the completion seam.

    Args:
        query: The user question.
        evidence: Evidence rows from :func:`prepare_evidence` (non-empty).
        complete: Injected async completion seam (``prompt -> reply``).
        answer_block: Frozen answer settings (``context_window``,
            ``max_output_tokens``, ``max_rounds``).
        error_detail: Credential-safe exception redactor.
        runner: Synthesis runner; the standard path passes its own
            module reference so existing patch targets keep working.

    Returns:
        The :class:`SynthesisOutcome`.  This seam never raises for a
        model failure; it reports ``failure_stage="generation"``.
    """
    nodes = _labelled_nodes(evidence)
    attempts = 0

    async def _counting_complete(prompt: str) -> str:
        # Counts every seam invocation so a failure reports the attempts
        # made before it (review F11); the count survives exceptions.
        nonlocal attempts
        attempts += 1
        return await complete(prompt)

    start = time.perf_counter()
    try:
        text, completion_calls = await runner(
            query,
            nodes,
            seam=_counting_complete,
            context_window=answer_block.context_window,
            max_output_tokens=answer_block.max_output_tokens,
            max_rounds=answer_block.max_rounds,
        )
    except Exception as exc:  # Generation failed after successful retrieval.
        # ``except Exception`` also catches an asyncio ``ExceptionGroup``
        # (a plain-``Exception`` subgroup), so a client seam that dies
        # mid-flight still maps to a generation failure.
        return SynthesisOutcome(
            text=None,
            completion_calls=attempts,
            ms=(time.perf_counter() - start) * 1000.0,
            error=f"Generation failed: {type(exc).__name__}: {error_detail(exc)}",
        )
    return SynthesisOutcome(
        text=text,
        completion_calls=completion_calls,
        ms=(time.perf_counter() - start) * 1000.0,
    )


@dataclass(frozen=True)
class CitationOutcome:
    """Result of the citation-resolution seam.

    Attributes:
        citations: Citations built from the supplied evidence lineage.
        grounded: True when the text is non-empty and cites evidence.
        error: Redacted message when citation assembly rejected the
            model output (attributed to generation).
    """

    citations: list[dict] = field(default_factory=list)
    grounded: bool = False
    error: str | None = None

    @property
    def failure_stage(self) -> str | None:
        """``"generation"`` when citation assembly failed, else ``None``."""
        return FAILURE_STAGE_GENERATION if self.error is not None else None


def resolve_citations(
    text: str, evidence: list[dict], *, error_detail: ErrorDetail
) -> CitationOutcome:
    """Resolve the answer's citation ordinals to supplied evidence lineage.

    Citations come from the evidence the system supplied, never from the
    model.  An absurd model output (for example a 5,000-digit ordinal)
    is a generation failure with evidence retained, never an exception
    escaping the operation (review F12).

    Args:
        text: The synthesised answer text.
        evidence: The evidence rows supplied as context.
        error_detail: Credential-safe exception redactor.

    Returns:
        The :class:`CitationOutcome`.
    """
    try:
        ordinals = parse_citation_ordinals(text, len(evidence))
        citations = build_citations(evidence, ordinals)
    except Exception as exc:
        return CitationOutcome(
            error=(
                "Generation failed: citation assembly rejected the model "
                f"output: {type(exc).__name__}: {error_detail(exc)}"
            )
        )
    return CitationOutcome(citations=citations, grounded=bool(text.strip()) and bool(citations))


async def verify_answer(
    text: str,
    evidence: list[dict],
    *,
    grounded: bool,
    answer_block: Any,
    verify_complete: CompletionSeam | None,
    unavailable_reason: str | None,
    error_detail: ErrorDetail,
) -> VerificationFields:
    """Run opt-in claim verification (ADR-059) for a grounded answer.

    Verification runs only when ``answer_block.verify_claims`` is on and
    the answer is grounded; otherwise the judge is never called.  The
    stage never raises: a missing or failing judge reports
    ``verification_skipped`` with the actual reason.

    Args:
        text: The synthesised answer text.
        evidence: The evidence rows supplied as context.
        grounded: Whether the answer is grounded (from citations).
        answer_block: Frozen answer settings (``verify_claims``).
        verify_complete: Injected judge seam, or ``None``.
        unavailable_reason: Why no judge seam could be built.
        error_detail: Credential-safe exception redactor.

    Returns:
        The :class:`~omrg.core.answer.verify.VerificationFields`.
    """
    if not (grounded and getattr(answer_block, "verify_claims", False)):
        return NO_VERIFICATION
    return await run_verification_stage(
        text,
        evidence,
        verify_complete=verify_complete,
        unavailable_reason=unavailable_reason,
        error_detail=error_detail,
    )
