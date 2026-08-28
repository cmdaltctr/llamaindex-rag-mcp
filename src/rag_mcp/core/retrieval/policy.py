"""Rerank threshold and policy resolution for the retrieval pipeline.

Holds the ÷30 threshold scaling, fetch_k resolution, technical query
classifier, and tri-state rerank policy resolver.  The ÷30 factor is
empirically calibrated — do not change without re-running experiment
``1-reranker-threshold-calibration-2026-05-12``.  Extracted from the
original ``retrieval.py`` monolith as part of Phase 1.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..settings import EffectiveSettings

import logging

logger = logging.getLogger(__name__)


def _resolve_fetch_k(
    top_k: int,
    rerank: bool,
    collection_count: int,
    settings: EffectiveSettings,
    fetch_k_override: int | None = None,
) -> int:
    """Compute the candidate pool size, applying the reranker fetch rules.

    When ``fetch_k_override`` is provided, it is used directly instead of
    the formula.  This is the escape hatch that prevents experiment
    pool-size sweeps from collapsing to the same effective value (the
    bug that voided Experiment 10 — see TDR-015 and OpenSpec change
    ``calibrate-rag-retrieval-defaults``).

    When ``fetch_k_override`` is None and ``rerank`` is False, ``fetch_k``
    equals ``top_k`` (the original behaviour).  When ``fetch_k_override``
    is None and ``rerank`` is True, the pool follows the
    "Wide Net, Tight Filter" pattern:

        fetch_k = max(RERANK_MAX_FETCH, top_k * RERANK_FETCH_MULTIPLIER)

    The result is always clamped to ``min(fetch_k, collection_count)`` so
    an unbounded value on a small collection does not produce a fetch
    larger than the collection itself.  See ADR-016 / OpenSpec change
    ``rag-retrieval-quality-improvements`` Decision 2.

    Args:
        top_k: Final number of results requested by the caller.
        rerank: Whether the cross-encoder reranker is active.
        collection_count: ``collection.count()`` for the target
            ChromaDB collection.
        fetch_k_override: When set, bypasses the formula and uses this
            value directly.  Intended for experiment runners that need
            genuinely distinct pool sizes.  Production callers leave this
            as None.

    Returns:
        The effective candidate pool size to fetch from the vector store.
    """
    if fetch_k_override is not None:
        fetch_k = fetch_k_override
    elif rerank:
        fetch_k = max(
            settings.retrieval.rerank_max_fetch,
            top_k * settings.retrieval.rerank_fetch_multiplier,
        )
    else:
        fetch_k = top_k

    if collection_count > 0:
        fetch_k = min(fetch_k, collection_count)
    # Always fetch at least 1 candidate so an empty result set is the
    # only zero-result scenario.
    return max(fetch_k, 1)


def _effective_threshold(
    similarity_threshold: float,
    rerank: bool,
) -> float:
    """Compute the effective score threshold, accounting for reranker scores.

    Cross-encoder sigmoid scores occupy a different range than cosine
    similarity.  Valid reranker results can score as low as 0.01–0.05,
    while cosine similarity rarely goes below 0.3 for relevant matches.

    When reranking is active, the threshold is scaled down by 30× so
    that a ``similarity_threshold=0.3`` becomes 0.01 — roughly equivalent
    to "keep anything the reranker considers a match, filter clear noise".

    The 30× factor was calibrated from experiment data:
    - Strong reranker matches: 0.79–1.0
    - Weak but correct matches: 0.015 (Colosseum query)
    - Clear noise: < 0.003

    Args:
        similarity_threshold: User-supplied threshold (0.0 = no filtering).
        rerank: Whether the cross-encoder reranker is active.

    Returns:
        The effective threshold to apply to scores.
    """
    if similarity_threshold <= 0.0:
        return 0.0
    return similarity_threshold / 30 if rerank else similarity_threshold


def _classify_query_technical(query: str) -> float:
    """Estimate the technical fraction of a query (0.0–1.0).

    Uses deterministic identifier-heavy rules from Experiment 9a/10:
    - Backticks: `identifier`
    - Slash paths: /path/to/file
    - Dotted paths: module.class.method
    - camelCase identifiers
    - snake_case identifiers
    - ALL_CAPS constants
    - Exception/Error tokens
    - Version strings: v1.2.3, 1.0.0
    - Package/API names

    Args:
        query: The search query string.

    Returns:
        Float in [0.0, 1.0] representing the fraction of tokens that are
        identifier-heavy technical content.
    """
    import re

    if not query.strip():
        return 0.0

    tokens = query.split()
    if not tokens:
        return 0.0

    technical_count = 0
    for token in tokens:
        # Backtick-quoted identifiers
        if "`" in token:
            technical_count += 1
            continue
        # Slash paths (Unix-style)
        if "/" in token and len(token) > 1:
            technical_count += 1
            continue
        # Dotted paths (Python-style: module.class.method)
        if "." in token and re.search(r"[a-zA-Z_]\.[a-zA-Z_]", token):
            technical_count += 1
            continue
        # camelCase (lowercase followed by uppercase)
        if re.search(r"[a-z][A-Z]", token):
            technical_count += 1
            continue
        # snake_case (lowercase with underscores)
        if re.search(r"[a-z]_[a-z]", token):
            technical_count += 1
            continue
        # ALL_CAPS constants (at least 2 uppercase letters with underscores)
        if re.search(r"[A-Z]{2,}", token) and "_" in token:
            technical_count += 1
            continue
        # Exception/Error tokens
        if re.search(r"(Exception|Error|err|exc)", token, re.IGNORECASE):
            technical_count += 1
            continue
        # Version strings (v1.2.3 or 1.0.0). Guard with "." in token to
        # avoid O(n²) backtracking on digit-only tokens (ReDoS hardening).
        if "." in token and re.search(r"v?\d+\.\d+(\.\d+)?", token):
            technical_count += 1
            continue
        # Explicit package/API/tooling terms and HTTP-ish API tokens.
        if token.lower().strip(".,:;()[]{}") in {
            "api", "sdk", "cli", "package", "module", "import",
            "endpoint", "http", "json", "yaml", "pip", "npm",
        }:
            technical_count += 1

    return technical_count / len(tokens)


def _resolve_rerank_policy(
    rerank: bool | None,
    query: str,
    settings: EffectiveSettings,
    technical_fraction: float | None = None,
    profile_reranker_enabled: bool | None = None,
) -> tuple[bool, str]:
    """Resolve effective rerank behaviour from explicit intent and policy.

    Implements tri-state rerank logic:
    - ``rerank=True``: force reranking (explicit opt-in)
    - ``rerank=False``: force no reranking (explicit opt-out)
    - ``rerank=None``: apply policy defaults

    Policy resolution for omitted rerank (precedence high → low):
    1. If ``profile_reranker_enabled`` is provided (Phase 4 profiles),
       it takes precedence over the global default.  ``documents`` profile
       enables reranking; ``codebase`` profile disables it.  The semantic
       policy does NOT override a profile decision.
    2. If ``RERANK_ENABLED=True``, rerank by default.
    3. If ``RERANK_ENABLED=False`` and ``RERANK_ENABLED_FOR_SEMANTIC=False``,
       do not rerank.
    4. If ``RERANK_ENABLED=False`` and ``RERANK_ENABLED_FOR_SEMANTIC=True``:
       - Classify the query as technical or semantic.
       - If technical fraction >= ``HARD_TECHNICAL_THRESHOLD``, do not rerank.
       - Otherwise, enable reranking (semantic workload override).

    Args:
        rerank: Explicit rerank value (True/False) or None for policy.
        query: The search query (used for technical classification).
        technical_fraction: Optional pre-computed technical fraction. If
            None, the query is classified on demand.
        profile_reranker_enabled: When provided (Phase 4), the resolved
            profile's reranker default takes precedence over the global
            ``RERANK_ENABLED`` setting.  Explicit ``rerank`` flags still
            bypass this.

    Returns:
        Tuple of ``(effective_rerank, reason)`` where ``effective_rerank``
        is the resolved boolean and ``reason`` is a diagnostic string.
    """
    # Explicit override: True forces reranking.
    if rerank is True:
        return (True, "explicit rerank=True override")

    # Explicit override: False disables reranking.
    if rerank is False:
        return (False, "explicit rerank=False override")

    # Omitted/None: apply policy.

    # Phase 4: profile-resolved enablement takes precedence over the
    # global default.  When a profile is active, its reranker decision
    # is the answer — the semantic policy does not override it.
    if profile_reranker_enabled is not None:
        if profile_reranker_enabled:
            return (True, "profile-resolved reranker enabled")
        return (False, "profile-resolved reranker disabled")

    # Step 1: Check global default.
    if settings.retrieval.rerank_enabled:
        return (True, "global default RERANK_ENABLED=true")

    # Step 2: Global is off. Check semantic policy.
    if not settings.retrieval.rerank_enabled_for_semantic:
        return (False, "disabled by default (RERANK_ENABLED_FOR_SEMANTIC=false)")

    # Step 3: Semantic policy is enabled. Classify the query.
    if technical_fraction is None:
        technical_fraction = _classify_query_technical(query)

    threshold = settings.retrieval.hard_technical_threshold
    if technical_fraction >= threshold:
        return (
            False,
            f"disabled by technical policy (fraction={technical_fraction:.2f} "
            f">= threshold={threshold})",
        )

    # Below threshold: semantic workload override.
    return (
        True,
        f"enabled by semantic policy (fraction={technical_fraction:.2f} "
        f"< threshold={threshold})",
    )
