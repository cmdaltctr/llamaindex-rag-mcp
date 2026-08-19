"""Shared preflight assertions for experiment validity (Stage 4, task 4.2).

These helpers evaluate a runtime manifest (``design.md`` D13) before measured
work begins.  They operate on plain dictionaries only: no model, corpus,
storage, or production imports, so unit tests can exercise every rule with
tiny fixtures (``design.md`` D15).

A failed preflight is an *experimental event*, not a data point: runners let
:class:`PreflightError` propagate to abort the cell (or run) rather than
recording measurements from a configuration that never took effect.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

__all__ = [
    "PreflightError",
    "assert_controlled_constant",
    "assert_distinct_values",
    "assert_manifest",
    "assert_no_fallback",
    "assert_parser_invoked_before_embeddings",
    "assert_policy_rerank_mode",
    "evaluate_assertions",
    "manifest_field",
]


class PreflightError(AssertionError):
    """Raised when a preflight assertion fails.

    Runners let this propagate to abort the cell or run: measured work from a
    configuration that failed preflight must never be recorded as data.
    """


def manifest_field(manifest: Mapping[str, Any], dotted_path: str) -> Any:
    """Resolve a dotted path such as ``"retrieval.fetch_k"`` against a manifest.

    Missing keys (or non-mapping intermediates) resolve to ``None``: a field
    the runner failed to record is indistinguishable from an explicit ``null``
    for assertion purposes, and assertions such as ``not_null`` catch it.

    Args:
        manifest: JSON-serialisable runtime manifest dictionary.
        dotted_path: Dot-separated key path.

    Returns:
        The value at the path, or ``None`` when any segment is absent.
    """
    value: Any = manifest
    for segment in dotted_path.split("."):
        if not isinstance(value, Mapping) or segment not in value:
            return None
        value = value[segment]
    return value


def evaluate_assertions(
    manifest: Mapping[str, Any],
    assertions: Iterable[Mapping[str, Any]],
) -> list[str]:
    """Evaluate preflight assertions against a manifest.

    Each assertion is a mapping with ``manifest_field``, ``operator``, and
    ``expected`` (an optional ``reason`` string may explain intent).  Unknown
    operators produce a failure string rather than passing silently.

    Args:
        manifest: Runtime manifest dictionary.
        assertions: Assertion payload entries (see ``ExperimentPlan``).

    Returns:
        Human-readable failure strings; an empty list means all assertions
        passed.
    """
    failures: list[str] = []
    for assertion in assertions:
        field = str(assertion.get("manifest_field", "<unspecified>"))
        operator = str(assertion.get("operator", ""))
        expected = assertion.get("expected")
        reason = assertion.get("reason")
        observed = manifest_field(manifest, field)
        suffix = f" (reason: {reason})" if reason else ""

        if operator == "eq":
            if observed != expected:
                failures.append(f"{field} eq {expected!r} failed: observed {observed!r}{suffix}")
        elif operator == "ne":
            if observed == expected:
                failures.append(f"{field} ne {expected!r} failed: observed {observed!r}{suffix}")
        elif operator == "in":
            if not _container_contains(expected, observed):
                failures.append(f"{field} in {expected!r} failed: observed {observed!r}{suffix}")
        elif operator == "not_in":
            if _container_contains(expected, observed):
                failures.append(
                    f"{field} not_in {expected!r} failed: observed {observed!r}{suffix}"
                )
        elif operator == "not_null":
            if observed is None:
                failures.append(f"{field} not_null failed: observed None{suffix}")
        elif operator == "is_null":
            if observed is not None:
                failures.append(f"{field} is_null failed: observed {observed!r}{suffix}")
        elif operator == "contains":
            if not _container_contains(observed, expected):
                failures.append(
                    f"{field} contains {expected!r} failed: observed {observed!r}{suffix}"
                )
        else:
            failures.append(
                f"{field}: unknown operator {operator!r} "
                f"(valid: eq, ne, in, not_in, not_null, is_null, contains){suffix}"
            )
    return failures


def _container_contains(container: Any, member: Any) -> bool:
    """Return whether ``container`` holds ``member``; uncontainable is False.

    A ``None`` or scalar "container" cannot contain anything, so membership
    fails cleanly instead of raising ``TypeError`` inside an assertion.
    """
    try:
        return member in container  # type: ignore[operator]
    except TypeError:
        return False


def assert_manifest(
    manifest: Mapping[str, Any],
    assertions: Iterable[Mapping[str, Any]],
) -> None:
    """Raise :class:`PreflightError` listing every failed assertion.

    Args:
        manifest: Runtime manifest dictionary.
        assertions: Assertion payload entries.

    Raises:
        PreflightError: With one line per failure when any assertion fails.
    """
    failures = evaluate_assertions(manifest, assertions)
    if failures:
        raise PreflightError("\n".join(failures))


def assert_no_fallback(manifest: Mapping[str, Any]) -> None:
    """Raise when any manipulated backend silently fell back (D14).

    A fallback is an experimental event: the cell the protocol declared was
    not the cell that ran.  The four watched conditions are requested-vs-
    effective mismatches for the reranker, document backend, and embedding
    provider, plus any recorded chunker fallback reason.

    Args:
        manifest: Runtime manifest dictionary.

    Raises:
        PreflightError: Naming the exact field and both values.
    """
    failures: list[str] = []

    requested = manifest_field(manifest, "reranker.requested_backend")
    effective = manifest_field(manifest, "reranker.effective_backend")
    if requested is not None and effective != requested:
        failures.append(
            f"reranker fallback: reranker.requested_backend={requested!r} but "
            f"reranker.effective_backend={effective!r}"
        )

    fallback_reason = manifest_field(manifest, "chunker.fallback_reason")
    if fallback_reason is not None:
        failures.append(
            f"chunker fallback: chunker.fallback_reason={fallback_reason!r} "
            f"(chunker.requested={manifest_field(manifest, 'chunker.requested')!r}, "
            f"chunker.effective={manifest_field(manifest, 'chunker.effective')!r})"
        )

    requested = manifest_field(manifest, "document_backend.requested")
    effective = manifest_field(manifest, "document_backend.effective")
    if requested is not None and effective != requested:
        failures.append(
            f"document backend fallback: document_backend.requested={requested!r} "
            f"but document_backend.effective={effective!r}"
        )

    requested = manifest_field(manifest, "embedding.requested_provider")
    effective = manifest_field(manifest, "embedding.effective_provider")
    if requested is not None and effective != requested:
        failures.append(
            f"embedding fallback: embedding.requested_provider={requested!r} but "
            f"embedding.effective_provider={effective!r}"
        )

    if failures:
        raise PreflightError("\n".join(failures))


def assert_distinct_values(
    values_by_label: Mapping[str, Any],
    field_name: str,
) -> None:
    """Assert no two labels resolved to the same value (task 4.2.4).

    Intended for manipulated numeric factors such as ``fetch_k``: if the
    runner's effective resolution collapses two declared levels onto one
    value, the cell matrix no longer manipulates that factor.  ``None``
    values count as collisions too.

    Args:
        values_by_label: Labels (for example cell ids) to resolved values.
        field_name: Field name used in the error message.

    Raises:
        PreflightError: Listing every colliding group of labels.
    """
    groups: dict[str, tuple[Any, list[str]]] = {}
    for label, value in values_by_label.items():
        key = repr(value)
        _, labels = groups.setdefault(key, (value, []))
        labels.append(label)

    collisions = [(value, sorted(labels)) for value, labels in groups.values() if len(labels) > 1]
    if collisions:
        lines = [
            f"{field_name} collision: value {value!r} shared by labels {labels}"
            for value, labels in sorted(collisions, key=lambda item: item[1])
        ]
        raise PreflightError("\n".join(lines))


def assert_controlled_constant(
    manifests_by_cell: Mapping[str, Mapping[str, Any]],
    dotted_fields: Iterable[str],
) -> None:
    """Assert controlled fields hold one observed constant across cells (4.2.3).

    Every cell's manifest must resolve each controlled field to the same
    non-``None`` value: a controlled variable that differs between cells was
    manipulated, and one that was never observed is absent, not controlled.

    Args:
        manifests_by_cell: Cell id to that cell's runtime manifest.
        dotted_fields: Controlled manifest fields to pin.

    Raises:
        PreflightError: Naming the field and the per-cell values or the cells
            where it was not observed.
    """
    for field in dotted_fields:
        values_by_cell = {
            cell: manifest_field(manifest, field) for cell, manifest in manifests_by_cell.items()
        }
        unobserved = sorted(cell for cell, value in values_by_cell.items() if value is None)
        distinct = {repr(value) for value in values_by_cell.values() if value is not None}

        if unobserved and not distinct:
            raise PreflightError(
                f"controlled variable {field!r} was not observed in any cell "
                f"(cells: {unobserved}); a controlled variable must be observed, "
                "not absent"
            )
        if unobserved:
            observed = sorted(f"{cell}={value!r}" for cell, value in values_by_cell.items())
            raise PreflightError(
                f"controlled variable {field!r} was not observed in cells "
                f"{unobserved}; per-cell values: {observed}"
            )
        if len(distinct) > 1:
            observed = sorted(f"{cell}={value!r}" for cell, value in values_by_cell.items())
            raise PreflightError(f"controlled variable {field!r} differs across cells: {observed}")


def _event_timestamp(event: Mapping[str, Any], index: int, kind: str) -> float:
    """Extract a numeric timestamp from an event or raise ``PreflightError``."""
    timestamp = event.get("timestamp")
    if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)):
        raise PreflightError(f"event {index} ({kind}) has a non-numeric timestamp {timestamp!r}")
    return float(timestamp)


def assert_parser_invoked_before_embeddings(
    events: Iterable[Mapping[str, Any]],
    parsers: Iterable[str],
) -> None:
    """Assert every declared parser ran before embedding started (4.2.5, D19).

    ``events`` is a chronological list of ``{"event", "parser", "timestamp"}`
    records with at least the ``parse_start``, ``parse_end``, and
    ``embed_start`` kinds.  When no ``embed_start`` has been recorded yet the
    ordering check is vacuous (preflight may run before embeddings begin,
    per D19) and only parser invocation and declaration are checked.

    Args:
        events: Chronological event records.
        parsers: Parser backends the protocol declares.

    Raises:
        PreflightError: With the precise violated rule.
    """
    declared = set(parsers)
    first_parse_start: dict[str, float] = {}
    embed_starts: list[float] = []

    for index, event in enumerate(events):
        kind = event.get("event")
        if not isinstance(kind, str):
            raise PreflightError(f"event {index} lacks a string 'event' kind")

        if kind.startswith("parse"):
            parser = event.get("parser")
            if parser not in declared:
                raise PreflightError(
                    f"event {index} ({kind}) references undeclared parser "
                    f"{parser!r}; declared parsers: {sorted(declared)}"
                )
            if kind == "parse_start":
                timestamp = _event_timestamp(event, index, kind)
                if parser not in first_parse_start or timestamp < first_parse_start[parser]:
                    first_parse_start[parser] = timestamp
        elif kind == "embed_start":
            embed_starts.append(_event_timestamp(event, index, kind))

    missing = sorted(declared - set(first_parse_start))
    if missing:
        raise PreflightError(f"declared parser(s) never recorded a parse_start event: {missing}")

    if embed_starts:
        first_embed = min(embed_starts)
        late = sorted(
            parser
            for parser, started_at in first_parse_start.items()
            if not started_at < first_embed
        )
        if late:
            raise PreflightError(
                f"parser(s) first invoked at or after the first embed_start ({first_embed}): {late}"
            )


def assert_policy_rerank_mode(manifest: Mapping[str, Any]) -> None:
    """Assert a threshold-policy cell exercises the policy resolver (4.2.6).

    The manifest must record ``retrieval.rerank_requested`` as ``None``: a
    recorded ``True``/``False`` means the runner force-overrode the policy the
    experiment exists to calibrate, and an absent key means the runner failed
    to record the request at all.

    Args:
        manifest: Runtime manifest dictionary.

    Raises:
        PreflightError: When the field is absent or not ``None``.
    """
    retrieval = manifest.get("retrieval")
    if not isinstance(retrieval, Mapping) or "rerank_requested" not in retrieval:
        raise PreflightError(
            "threshold-policy experiment must record retrieval.rerank_requested "
            "as None for policy cells; the key is absent from the manifest"
        )
    requested = retrieval["rerank_requested"]
    if requested is not None:
        raise PreflightError(
            "threshold-policy experiment must exercise the policy resolver: "
            f"retrieval.rerank_requested={requested!r}; the runner must record "
            "rerank_requested=None for policy cells, not a force override"
        )
