"""The async adapter protocol that domain packages implement.

An adapter wraps one existing domain operation. It receives every resource
and setting explicitly through :class:`NodeContext`; it must never read a
process-default store, settings object or provider. Domain adapters live in
their owning domain package and register with an
:class:`~omrg.core.pipelines.catalogue.OperationCatalogue` built by the
composition root.

Input values arrive keyed by input port name. A ``MANY`` port receives a
tuple in edge declaration order. An ``OPTIONAL`` port that has no
connection is absent from the mapping.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from pydantic import BaseModel

if TYPE_CHECKING:
    from ..settings import EffectiveSettings


@runtime_checkable
class CancellationToken(Protocol):
    """Run-scoped cooperative cancellation signal."""

    @property
    def cancelled(self) -> bool:
        """Return whether cancellation was requested for this run."""
        ...


class CancellationFlag:
    """Simple in-process :class:`CancellationToken` implementation."""

    def __init__(self) -> None:
        """Create an unset flag."""
        self._cancelled = False

    @property
    def cancelled(self) -> bool:
        """Return whether :meth:`cancel` was called."""
        return self._cancelled

    def cancel(self) -> None:
        """Request cancellation."""
        self._cancelled = True


def _discard_progress(message: str, data: Mapping[str, Any]) -> None:
    return None


@dataclass(frozen=True)
class NodeContext:
    """Everything an adapter may use, passed explicitly.

    Attributes:
        run_id: Run identifier.
        node_id: Node identifier.
        settings: Frozen effective settings for this node (profile,
            graph and node overrides already applied).
        resources: Engine-owned resources by name, for example
            ``store``, ``embedder``, ``reranker``, ``ocr``, ``completion``.
            Read-only mapping; adapters borrow and never close them.
        cancellation: Run-scoped cancellation token. Check it before a
            protected commit starts.
        collection: Collection the node is bound to, if any.
        unit_id: Execution unit, for example one source in a directory.
        controls: Effective lever values for this node.
        progress: Callback for safe progress summaries.
    """

    run_id: str
    node_id: str
    settings: EffectiveSettings
    resources: Mapping[str, Any]
    cancellation: CancellationToken
    collection: str | None = None
    unit_id: str | None = None
    controls: Mapping[str, Any] = field(default_factory=dict)
    progress: Callable[[str, Mapping[str, Any]], None] = _discard_progress

    def __post_init__(self) -> None:
        """Freeze the mappings so adapters cannot rewrite shared state."""
        object.__setattr__(self, "resources", MappingProxyType(dict(self.resources)))
        object.__setattr__(self, "controls", MappingProxyType(dict(self.controls)))

    def resource(self, name: str) -> Any:
        """Return a required resource.

        Raises:
            LookupError: If the host did not supply ``name``.
        """
        try:
            return self.resources[name]
        except KeyError:
            raise LookupError(
                f"Node {self.node_id!r} needs resource {name!r}, which the host did not supply."
            ) from None


@dataclass(frozen=True)
class NodeOutput:
    """What an adapter returns.

    Attributes:
        values: Output port name to value.
        effects: Completed effects, for example ``"committed:<source_id>"``.
        fallback: Reason a declared domain fallback applied, if any.
        summary: Small JSON-safe summary for events (counts, score kinds).
    """

    values: Mapping[str, Any]
    effects: tuple[str, ...] = ()
    fallback: str | None = None
    summary: Mapping[str, Any] = field(default_factory=dict)


class OperationAdapter(Protocol):
    """Async callable that executes one operation."""

    async def __call__(
        self, context: NodeContext, inputs: Mapping[str, Any], params: BaseModel
    ) -> NodeOutput:
        """Run the operation.

        Args:
            context: Explicit resources, settings and run state.
            inputs: Input port name to value.
            params: Validated parameter model instance.

        Returns:
            The output values and completed effects.
        """
        ...
