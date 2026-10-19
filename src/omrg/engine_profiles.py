"""Run a user profile's pipelines inside a request (unify-profiles-and-pipelines, D2, D14 to D17).

A collection that follows a user profile searches, answers and ingests through
the profile's current Search, Answer and Ingest graphs. The Engine calls these
functions after it finds a user binding. Built-in profiles never reach this
module: they keep the direct path.

The graphs run through ``Engine.run_pipeline`` in the request. They make no run
record and do not use the workspace run queue. A value the caller sets
replaces the matching step setting (D14). The result has the shape of the
built-in operation (D16).
"""

from __future__ import annotations

import asyncio
import copy
from collections.abc import Callable, Coroutine, Mapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar

from .core.pipelines import RunStatus
from .core.profiles.readiness import slot_title

if TYPE_CHECKING:
    from .core.pipelines import PipelineResult
    from .core.profiles.catalogue import ProfileBinding

T = TypeVar("T")

#: Request values that replace a step setting: request name to (operation, parameter).
_REQUEST_TARGETS: dict[str, tuple[str, str]] = {
    "top_k": ("retrieve.prepare_query", "top_k"),
    "similarity_threshold": ("retrieve.prepare_query", "similarity_threshold"),
    "rerank": ("retrieve.prepare_query", "rerank"),
    "fetch_k": ("retrieve.prepare_query", "fetch_k"),
    "metadata_filter": ("retrieve.prepare_query", "metadata_filter"),
    "expand_window": ("context.assemble", "expand_window"),
    "include_diagnostics": ("answer.synthesise", "include_diagnostics"),
}
#: Request values that replace the step settings of the matching chunking levers.
_LEVER_TARGETS: dict[str, str] = {
    "chunk_size": "chunking.chunk_size",
    "chunk_overlap": "chunking.chunk_overlap",
}
#: Request values that no step setting covers. The graph's wiring decides.
_NO_STEP_SETTING = ("hybrid", "technical_fraction")


class ProfileRunError(RuntimeError):
    """A pipeline of a user profile failed while it ran in a request."""


# ── Running a graph ───────────────────────────────────────────────────


def run_blocking(make_coroutine: Callable[[], Coroutine[Any, Any, T]]) -> T:
    """Run a coroutine from synchronous code on a private event loop.

    Without a running loop in this thread, ``asyncio.run`` is enough. Inside a
    running loop (a notebook), the private loop runs in a short-lived helper
    thread and this thread waits for it. Read-only graphs never take the
    Engine lock, so no lock crosses event loops (D15).
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(make_coroutine())
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(make_coroutine())).result()


def slot_graph(resolver: Any, binding: ProfileBinding, slot: str) -> dict[str, Any]:
    """Return a copy of the current graph of one slot of a user profile.

    Raises:
        ValueError: If the slot has no saved graph.
    """
    catalogue = getattr(resolver, "catalogue", None)
    document = catalogue.slot_document(binding.name, slot) if catalogue is not None else None
    if document is None:
        raise ValueError(
            f"The {slot_title(slot)} pipeline of the profile {binding.name!r} has no saved "
            f"graph. Open it in Studio and build one."
        )
    return copy.deepcopy(dict(document))


def apply_request(
    graph: dict[str, Any], collection: str, values: Mapping[str, Any], catalogue: Any
) -> tuple[dict[str, Any], list[str]]:
    """Return the graph for one request, and the request values that had no effect.

    The graph names the request collection. Each value the caller set (not
    ``None``) replaces the matching step setting on every step that declares
    it. ``hybrid`` and ``technical_fraction`` have no step setting.

    Args:
        graph: A graph document. It is changed in place.
        collection: The collection of the request.
        values: Request values by name; ``None`` means "not set".
        catalogue: The operation catalogue that tells which step declares which setting.

    Returns:
        The graph and the sorted names of the unused request values.
    """
    graph["collection"] = collection
    unused = [name for name in _NO_STEP_SETTING if values.get(name) is not None]
    for name, value in values.items():
        if value is None or name in _NO_STEP_SETTING:
            continue
        applied = False
        for node in graph["nodes"]:
            entry = catalogue.get(node["operation"], node.get("version"))
            if entry is None:
                continue
            param = _param_for(name, node["operation"], entry.descriptor)
            if param is not None:
                node.setdefault("params", {})[param] = value
                applied = True
        if not applied:
            unused.append(name)
    return graph, sorted(unused)


def _param_for(name: str, operation: str, descriptor: Any) -> str | None:
    """Return the parameter of a step that a request value replaces, if any."""
    target = _REQUEST_TARGETS.get(name)
    if target is not None:
        return target[1] if target[0] == operation else None
    lever = _LEVER_TARGETS.get(name)
    if lever is not None:
        return next((p for p, path in descriptor.lever_params.items() if path == lever), None)
    return None


def _run(
    engine: Any,
    binding: ProfileBinding,
    slot: str,
    inputs: Mapping[str, Any],
    collection: str,
    values: Mapping[str, Any],
) -> tuple[PipelineResult, list[str]]:
    """Run the current graph of one slot with the request values applied."""
    graph = slot_graph(engine._resolver(), binding, slot)
    catalogue = engine._pipelines.catalogue()
    graph, unused = apply_request(graph, collection, values, catalogue)
    result = run_blocking(lambda: engine.run_pipeline({"graph": graph}, inputs=dict(inputs)))
    return result, unused


async def _run_async(
    engine: Any,
    binding: ProfileBinding,
    slot: str,
    inputs: Mapping[str, Any],
    collection: str,
    values: Mapping[str, Any],
) -> tuple[PipelineResult, list[str]]:
    graph = slot_graph(engine._resolver(), binding, slot)
    graph, unused = apply_request(graph, collection, values, engine._pipelines.catalogue())
    return await engine.run_pipeline({"graph": graph}, inputs=dict(inputs)), unused


def _failure(binding: ProfileBinding, slot: str, result: PipelineResult) -> ProfileRunError:
    where = f" at step '{result.failed_node}'" if result.failed_node else ""
    reason = f": {result.error}" if result.error else ""
    return ProfileRunError(
        f"The {slot_title(slot)} pipeline of the profile {binding.name!r} "
        f"did not finish ({result.status.value}){where}{reason}"
    )


def _require_success(binding: ProfileBinding, slot: str, result: PipelineResult) -> None:
    if result.status is not RunStatus.SUCCEEDED:
        raise _failure(binding, slot, result)


# ── Search ────────────────────────────────────────────────────────────


def search(
    engine: Any,
    binding: ProfileBinding,
    query: str,
    collection: str,
    *,
    include_diagnostics: bool,
    values: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Search through the Search pipeline of a user profile.

    Returns:
        The rows of ``Engine.search``: the public shape, or the diagnostic rows.
        With diagnostics, every row lists the request values that had no effect.
    """
    result, unused = _run(engine, binding, "search", {"query": query}, collection, values)
    _require_success(binding, "search", result)
    bundle = result.outputs["results"]
    rows = [dict(row) for row in bundle.rows] if include_diagnostics else bundle.public_rows()
    if include_diagnostics and unused:
        for row in rows:
            row["unused_request_values"] = list(unused)
    return rows


# ── Answer ────────────────────────────────────────────────────────────


def refuse_caller_inputs(binding: ProfileBinding, client_completion: Any, rows: Any) -> None:
    """Refuse a client completion or pre-fetched rows for a user profile (D17).

    Raises:
        ValueError: If either is set.
    """
    if client_completion is not None or rows is not None:
        raise ValueError(
            f"The Answer pipeline of the profile {binding.name!r} does its own retrieval and "
            f"uses the server model. A client completion or pre-fetched rows cannot be used "
            f"with it. Leave them out, or use a collection that follows a built-in profile."
        )


async def answer(
    engine: Any,
    binding: ProfileBinding,
    question: str,
    collection: str,
    *,
    values: Mapping[str, Any],
) -> dict[str, Any]:
    """Answer through the Answer pipeline of a user profile.

    Returns:
        The result dict of ``Engine.answer``. With diagnostics it lists the
        request values that had no effect under ``unused_request_values``.
    """
    result, unused = await _run_async(
        engine, binding, "answer", {"query": question}, collection, values
    )
    _require_success(binding, "answer", result)
    answer_result = dict(result.outputs["answer"])
    if values.get("include_diagnostics") and unused:
        answer_result["unused_request_values"] = list(unused)
    return answer_result


# ── Ingest ────────────────────────────────────────────────────────────


def _sum_timings(details: list[dict[str, Any]], total_seconds: float) -> dict[str, float]:
    totals: dict[str, float] = {}
    for detail in details:
        for key, value in (detail.get("timings") or {}).items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                totals[key] = totals.get(key, 0.0) + float(value)
    totals["total_seconds"] = total_seconds
    return totals


def _unit_detail(unit: Any) -> dict[str, Any]:
    """Return the file detail of one finished or failed unit."""
    summary = unit.outputs.get("summary")
    if isinstance(summary, dict):
        return dict(summary)
    return {
        "file": unit.unit_id,
        "status": "failed",
        "chunks": 0,
        "error": unit.error or "",
        "failure_stage": unit.failed_node or "run",
    }


def ingest_summary(result: PipelineResult, collection: str) -> dict[str, Any]:
    """Map the units of an Ingest run to the result of ``Engine.ingest`` (D16)."""
    details = [_unit_detail(unit) for unit in result.units]
    counts = {"indexed": 0, "skipped_unchanged": 0, "skipped": 0, "failed": 0}
    chunks_created = chunks_removed = degraded = 0
    for detail in details:
        counts[detail.get("status", "failed")] = counts.get(detail.get("status", "failed"), 0) + 1
        chunks_removed += int(detail.get("chunks_removed", 0) or 0)
        if detail.get("status") == "indexed":
            chunks_created += int(detail.get("chunks", 0) or 0)
        degraded += bool(detail.get("metadata_degraded"))
    summary: dict[str, Any] = {
        "files_indexed": counts["indexed"],
        "files_skipped_unchanged": counts["skipped_unchanged"],
        "files_skipped_binary": counts["skipped"],
        "chunks_created": chunks_created,
        "chunks_removed": chunks_removed,
        "collection": collection,
        "file_details": details,
        "metadata_degraded": degraded,
        "timings": _sum_timings(details, result.wall_time_s or 0.0),
        "peak_rss_bytes": None,
    }
    if counts["indexed"] or counts["skipped_unchanged"] or counts["skipped"]:
        out: dict[str, Any] = {"status": "ok", **summary}
    else:
        out = {
            "status": "error",
            "error_type": "unknown",
            "message": (
                f"All {len(details)} file(s) failed to index. See file_details for per-file errors."
            ),
            **summary,
        }
    errors = [f"{d['file']}: {d['error']}" for d in details if d.get("status") == "failed"]
    if errors:
        out["warnings"] = errors
    return out


def missing_path_result(path: str, collection: str) -> dict[str, Any] | None:
    """Return the built-in error result for a path that does not exist, else ``None``."""
    if Path(path).expanduser().resolve().exists():
        return None
    return {
        "status": "error",
        "error_type": "file",
        "message": f"Path not found: {path}",
        "file_details": [],
        "collection": collection,
        "chunks_removed": 0,
        "metadata_degraded": 0,
    }


async def ingest(
    engine: Any,
    binding: ProfileBinding,
    path: str,
    collection: str,
    *,
    progress_callback: Callable[[str, int, int], None] | None,
    values: Mapping[str, Any],
) -> dict[str, Any]:
    """Ingest through the Ingest pipeline of a user profile.

    ``progress_callback(phase, current, total)`` is called once per source
    after the run, in the order of the units.
    """
    if (missing := missing_path_result(path, collection)) is not None:
        return missing
    result, _ = await _run_async(engine, binding, "ingest", {"path": path}, collection, values)
    if result.status is not RunStatus.SUCCEEDED and not result.units:
        raise _failure(binding, "ingest", result)
    summary = ingest_summary(result, collection)
    if progress_callback is not None:
        total = len(result.units)
        for index in range(total):
            progress_callback("read", index + 1, total)
    return summary
