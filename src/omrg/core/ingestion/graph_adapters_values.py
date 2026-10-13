"""Per-source port value and shared helpers of the ingestion graph adapters.

One :class:`SourceWork` value travels from ``source.identify`` to
``commit.source`` for exactly one source unit. Each adapter returns a new
value with ``dataclasses.replace``. A value whose ``status`` is not
``pending`` (an unchanged or binary source) passes through every node
without work, so the commit can report the same per-source outcome as
``ingest_path_async``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, TypeVar

from ..pipelines import NodeContext, PipelineCancelledError
from .backends.orchestrator import BackendRead
from .commit import PreparedSource
from .sources import SourceIdentity, SourceUnit

#: Engine resource names used by the ingestion adapters.
STORE_RESOURCE = "store"
EMBEDDER_RESOURCE = "embedder"
OCR_RESOURCE = "ocr"

PENDING = "pending"
UNCHANGED = "unchanged"
BINARY = "binary"

_T = TypeVar("_T")


@dataclass(frozen=True)
class SourceWork:
    """The state of one source unit between identify and commit.

    Attributes:
        unit: The discovered source unit.
        collection: Collection the reuse check ran against.
        status: ``pending``, ``unchanged`` (complete current version) or
            ``binary`` (detected binary; the commit removes its rows).
        identity: Canonical source and index identity (``None`` for binary).
        existing_chunks: Stored chunk count of an unchanged source.
        backend_read: Reader output with its declarations.
        nodes: Chunked nodes (specialised strategy or splitter).
        specialised: Whether a code/config strategy produced ``nodes``.
        effective_strategy: Strategy a code chunk result reports, if any.
        doc_metadata: File-level metadata from ``prepare.enrich``.
        metadata_degraded: Whether metadata came from a fallback tier.
        prepared: The prepared attempt record from ``embed.chunks``.
    """

    unit: SourceUnit
    collection: str
    status: str = PENDING
    identity: SourceIdentity | None = None
    existing_chunks: int = 0
    backend_read: BackendRead | None = None
    nodes: list | None = None
    specialised: bool = False
    effective_strategy: str | None = None
    doc_metadata: dict | None = None
    metadata_degraded: bool = False
    prepared: PreparedSource | None = None

    @property
    def pending(self) -> bool:
        """Return whether this source still needs work."""
        return self.status == PENDING

    def require_identity(self) -> SourceIdentity:
        """Return the identity of a pending source.

        Raises:
            ValueError: If ``source.identify`` did not run for this value.
        """
        if self.identity is None:
            raise ValueError(
                f"Source {self.unit.rel_path!r} has no identity. Connect source.identify "
                "before this node."
            )
        return self.identity


def single_unit(value: Any) -> SourceUnit:
    """Return the one source unit of a per-unit pass.

    The runner delivers one unit as a one-item tuple under a ``UnitSplit``.

    Raises:
        ValueError: If the value holds more or less than one source unit.
        TypeError: If the value is not a source unit.
    """
    if isinstance(value, SourceUnit):
        return value
    items = list(value) if isinstance(value, Sequence) and not isinstance(value, str) else None
    if items is None or len(items) != 1:
        count = "an unknown number of" if items is None else str(len(items))
        raise ValueError(
            f"source.identify takes one source unit per pass; it received {count}. Run the "
            "graph with a unit split on discover.sources so each source is processed alone."
        )
    if not isinstance(items[0], SourceUnit):
        raise TypeError(f"Expected a SourceUnit, not {type(items[0]).__name__}.")
    return items[0]


def work_value(value: Any) -> SourceWork:
    """Return *value* as :class:`SourceWork`.

    Raises:
        TypeError: If an upstream node produced another value type.
    """
    if not isinstance(value, SourceWork):
        raise TypeError(
            f"Expected the per-source value from source.identify, not {type(value).__name__}."
        )
    return value


def required(context: NodeContext, name: str) -> Any:
    """Return a host resource and refuse a ``None`` placeholder.

    Raises:
        LookupError: If the host did not supply the resource.
    """
    value = context.resource(name)
    if value is None:
        raise LookupError(f"Node {context.node_id!r} needs resource {name!r}, but it is None.")
    return value


def optional(context: NodeContext, name: str) -> Any:
    """Return a host resource, or ``None`` when the host did not supply it."""
    return context.resources.get(name)


def target_collection(context: NodeContext, params: Any) -> str:
    """Return the admitted collection of a collection-bound node.

    Raises:
        LookupError: If neither admission nor the parameters name one.
    """
    collection = context.collection or getattr(params, "collection", None)
    if not collection:
        raise LookupError(f"Node {context.node_id!r} has no target collection.")
    return collection


def stop_if_cancelled(context: NodeContext) -> None:
    """Stop at a safe boundary before a protected commit starts.

    Raises:
        PipelineCancelledError: If the run requested cancellation.
    """
    if context.cancellation.cancelled:
        raise PipelineCancelledError(
            f"The run was cancelled before node {context.node_id!r} started its commit."
        )


async def run_protected(call: Callable[[], _T]) -> _T:
    """Run a blocking protected operation to completion in a worker thread.

    The operation cannot stop part-way. If the awaiting task is cancelled,
    this function waits until the operation has finished its write,
    verification and cleanup, then re-raises the cancellation.
    """
    task = asyncio.ensure_future(asyncio.to_thread(call))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        while not task.done():
            try:
                await asyncio.wait({task})
            except asyncio.CancelledError:
                continue
        if not task.cancelled():
            task.exception()  # retrieved: the cancellation below is what we report
        raise
