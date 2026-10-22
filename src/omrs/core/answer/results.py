"""Answer result shapes shared by every answering path.

The standard ``answer()`` operation and later graph adapters build their
result dicts through these functions, so the public shape (key set, key
order, status taxonomy and verification labels) has one implementation.
Split from ``pipeline.py`` for the add-local-web-pipeline-workspace
answer seams (task 3.6).
"""

from __future__ import annotations

from typing import Any

from .verify import VerificationFields

#: Actionable message for the no-provider case (spec scenario).  Names
#: the settings AND the MCP-client alternative so both options surface.
NO_PROVIDER_MESSAGE = (
    "No answer model is configured for grounded answering. Set "
    "ANSWER__PROVIDER (and ANSWER__MODEL) to configure a server-side "
    "model, or use an MCP client that supports sampling so the client's "
    "model can complete the answer."
)

#: Actionable message when the master switch is off.  Every transport
#: (MCP, CLI, HTTP) inherits this through ``answer()``; the MCP
#: transport also returns it before issuing any client sample.
DISABLED_MESSAGE = (
    "Grounded answering is disabled. Set ANSWER__ENABLED=true to enable "
    "it, or use search_documents for ranked chunks without a "
    "language-model call."
)


def base_result(
    query: str,
    completion_source: str,
    status: str = "error",
    answer: str | None = None,
    failure_stage: str | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    """Build the result skeleton shared by every status."""
    return {
        "status": status,
        "query": query,
        "answer": answer,
        "citations": [],
        "evidence": [],
        "failure_stage": failure_stage,
        "error": error,
        "completion_source": completion_source,
    }


def disabled_result(query: str, completion_source: str) -> dict[str, Any]:
    """Build the actionable master-switch-off response (review F4).

    Shared by every transport so the disabled shape is identical
    whether it is produced here or by the MCP transport's early gate.

    Args:
        query: The question that was asked.
        completion_source: Label for the result (``"none"`` when the
            transport gates before selecting a source).

    Returns:
        The standard error result naming ``ANSWER__ENABLED``.
    """
    return base_result(
        query,
        completion_source,
        status="error",
        failure_stage=None,
        error=DISABLED_MESSAGE,
    )


def zero_generation_diagnostics(retrieval_ms: float) -> dict[str, Any]:
    """Diagnostics for paths where no generation round ran."""
    return {
        "retrieval_ms": retrieval_ms,
        "generation_ms": 0.0,
        "completion_calls": 0,
    }


def generation_diagnostics(
    retrieval_ms: float, generation_ms: float, completion_calls: int
) -> dict[str, Any]:
    """Diagnostics for paths where at least one generation round started."""
    return {
        "retrieval_ms": retrieval_ms,
        "generation_ms": generation_ms,
        "completion_calls": completion_calls,
    }


def _with_diagnostics(result: dict[str, Any], diagnostics: dict[str, Any] | None) -> dict[str, Any]:
    """Attach a copy of *diagnostics* when the caller asked for them."""
    if diagnostics is not None:
        result["diagnostics"] = dict(diagnostics)
    return result


def no_evidence_result(
    query: str, completion_source: str, *, diagnostics: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Build the no-evidence outcome; no model is ever called for it."""
    return _with_diagnostics(
        base_result(query, completion_source, status="no_evidence"), diagnostics
    )


def no_provider_result(
    query: str,
    completion_source: str,
    evidence: list[dict],
    *,
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the provider-absent error; the evidence is retained."""
    result = base_result(
        query,
        completion_source,
        status="error",
        failure_stage=None,
        error=NO_PROVIDER_MESSAGE,
    )
    result["evidence"] = evidence
    return _with_diagnostics(result, diagnostics)


def stage_failure_result(
    query: str,
    completion_source: str,
    *,
    failure_stage: str | None,
    error: str,
    evidence: list[dict] | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an attributed stage failure (``retrieval`` or ``generation``).

    Args:
        query: The question that was asked.
        completion_source: Label echoed in the result.
        failure_stage: The stage that failed.
        error: The already-redacted, actionable error message.
        evidence: Evidence retrieved before the failure (kept on a
            generation failure; empty on a retrieval failure).
        diagnostics: Optional diagnostics block.

    Returns:
        The standard error result.
    """
    result = base_result(
        query,
        completion_source,
        status="error",
        failure_stage=failure_stage,
        error=error,
    )
    if evidence is not None:
        result["evidence"] = evidence
    return _with_diagnostics(result, diagnostics)


def answer_status(grounded: bool, verification: VerificationFields) -> str:
    """Map grounding and verification to the result status.

    Failing claims give ``unverified_claims``; otherwise a grounded
    answer is ``ok`` and an ungrounded one ``generation_unverified``.
    """
    if verification.failing:
        return "unverified_claims"
    return "ok" if grounded else "generation_unverified"


def answered_result(
    query: str,
    completion_source: str,
    *,
    text: str,
    citations: list[dict],
    grounded: bool,
    evidence: list[dict],
    verification: VerificationFields,
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the result for a completed generation.

    Verification fields keep their actual guarantee: ``verified`` only
    when every claim passed, ``verification_skipped`` with the actual
    reason, and ``unverified_claims`` for failing claims.  Judge cost is
    added to the diagnostics only when the judge ran.

    Args:
        query: The question that was asked.
        completion_source: Label echoed in the result.
        text: The synthesised answer text.
        citations: Citations resolved from the supplied evidence.
        grounded: True when the text is non-empty and cites evidence.
        evidence: The evidence supplied as context.
        verification: The verification stage outcome.
        diagnostics: Optional retrieval/generation diagnostics block.

    Returns:
        The answer result dict.
    """
    status = answer_status(grounded, verification)
    result = base_result(query, completion_source, status=status, answer=text)
    result["citations"] = citations
    result["evidence"] = evidence
    if verification.verified:
        result["verified"] = True
    if verification.skipped_reason is not None:
        result["verification_skipped"] = verification.skipped_reason
    if verification.failing:
        result["unverified_claims"] = list(verification.failing)
    _with_diagnostics(result, diagnostics)
    if diagnostics is not None and verification.ran:
        # The judge's cost is reported separately from retrieval and
        # generation (spec: cost disclosure), only when it ran.
        result["diagnostics"]["verification_ms"] = verification.ms
        result["diagnostics"]["verification_calls"] = verification.calls
    return result
