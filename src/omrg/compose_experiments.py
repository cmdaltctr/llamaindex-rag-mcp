"""Compose one Engine per approved experiment context (design D10).

:class:`ExperimentEngines` builds and caches a separate Engine for each
context id. The store lives in ``<workspace>/output/<backend>/``. The
backend is LanceDB unless the context declares the store as an
experiment factor. Each Engine gets its own embedder, because
``compose.EMBEDDING_PROVIDER_SCOPE`` is ``"engine"``.

A job borrows a context through :meth:`ExperimentEngines.admit`, which
holds a lease, validates the graph without side effects, runs the
admission guard, and returns the frozen snapshot. The job releases the
lease after execution. Revocation refuses later admissions; the Engine
closes when the last lease is released.

This module builds Engines through the existing ``compose.build_engine``
entry point with explicit settings. It reads no settings singleton and
no process default: callers pass the base ``Settings``.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .core.experiments import (
    BackendIdentity,
    ExperimentAdmissionError,
    ExperimentContext,
    ExperimentLease,
    ExperimentRegistry,
    check_credential_target,
    check_experiment_snapshot,
    verify_containment,
)
from .core.vectordb.identity import embedding_identity_from_settings

if TYPE_CHECKING:
    from .config import Settings
    from .engine import Engine


def _lancedb(store_dir: Path) -> dict[str, Any]:
    return {"vector_store": "lancedb", "lancedb_uri": str(store_dir)}


def _chroma(store_dir: Path) -> dict[str, Any]:
    return {"vector_store": "chroma", "chroma_mode": "local", "chroma_persist_dir": str(store_dir)}


#: Settings fields that place each supported backend in a directory.
STORE_LOCATIONS: Mapping[str, Callable[[Path], dict[str, Any]]] = {
    "lancedb": _lancedb,
    "chroma": _chroma,
}

#: The live-library location field for each backend.
_LIVE_LOCATION_FIELD: Mapping[str, str] = {
    "lancedb": "lancedb_uri",
    "chroma": "chroma_persist_dir",
}


def experiment_registry(approved_roots: Iterable[str | Path]) -> ExperimentRegistry:
    """Return a registry for *approved_roots* with the composable backends."""
    return ExperimentRegistry(approved_roots, store_backends=STORE_LOCATIONS)


def experiment_settings(base: Settings, context: ExperimentContext) -> tuple[Settings, Path]:
    """Return the context settings and store directory.

    Args:
        base: Operator settings for the live library.
        context: The experiment context.

    Returns:
        A copy of *base* whose store sits below the context ``output/``
        directory, and that store directory.
    """
    store_dir = context.output_dir / context.store_backend
    return base.model_copy(update=STORE_LOCATIONS[context.store_backend](store_dir)), store_dir


def _identity(settings: Settings, context_id: str | None, store_path: str) -> BackendIdentity:
    embedding = embedding_identity_from_settings(settings)
    return BackendIdentity(
        context_id=context_id,
        store_kind=settings.vector_store,
        store_path=str(Path(store_path).resolve()),
        embedding_provider=embedding.provider,
        embedding_model=embedding.model,
    )


def live_backend_identity(settings: Settings) -> BackendIdentity:
    """Return the backend identity of the live library for comparison."""
    location = getattr(settings, _LIVE_LOCATION_FIELD.get(settings.vector_store, ""), "")
    return _identity(settings, None, location or settings.vector_store)


@dataclass(frozen=True)
class ExperimentRunResult:
    """A finished experiment run and its provenance.

    Attributes:
        result: The ``PipelineResult`` from ``Engine.run_pipeline``.
        provenance: Context id, graph identity and backend identity.
    """

    result: Any
    provenance: dict[str, Any]


@dataclass
class ExperimentAdmission:
    """An admitted experiment graph that holds a context lease.

    Run ``engine.run_pipeline(snapshot)``, then call :meth:`release`
    (also on failure or cancellation). Use it as a context manager to
    release automatically.
    """

    context: ExperimentContext
    engine: Engine
    snapshot: Any
    identity: BackendIdentity
    lease: ExperimentLease = field(repr=False)

    def provenance(self) -> dict[str, Any]:
        """Return what the run records with its outputs."""
        return {
            "context_id": self.context.context_id,
            "graph_identity": self.snapshot.graph_identity,
            "backend": self.identity.provenance(),
        }

    def release(self) -> None:
        """Return the context lease; idempotent."""
        self.lease.release()

    def __enter__(self) -> ExperimentAdmission:
        """Hold the lease for a ``with`` block."""
        return self

    def __exit__(self, *exc: object) -> None:
        """Release the lease when the block ends."""
        self.release()


def _default_build_engine(settings: Settings) -> Engine:
    from .compose import build_engine

    return build_engine(settings)


class ExperimentEngines:
    """Builds, caches and closes one Engine per experiment context."""

    def __init__(
        self,
        registry: ExperimentRegistry,
        base_settings: Settings,
        *,
        build_engine: Callable[[Settings], Engine] | None = None,
    ) -> None:
        """Prepare lazy Engine construction.

        Args:
            registry: The approved context registry.
            base_settings: Live-library settings the contexts derive from.
            build_engine: Engine builder (default ``compose.build_engine``).
        """
        self.registry = registry
        self._base = base_settings
        self._build = build_engine or _default_build_engine
        self._engines: dict[str, Engine] = {}
        self._identities: dict[str, BackendIdentity] = {}
        self._lock = threading.Lock()
        registry.add_idle_listener(self._close_context)

    def engine(self, context_id: str) -> Engine:
        """Return the cached Engine for an active context; build it once.

        Raises:
            ExperimentAdmissionError: Unknown or revoked context.
            ExperimentPathError: The workspace moved or ``output`` is a link.
        """
        context = self.registry.require_active(context_id)
        with self._lock:
            if context_id not in self._engines:
                verify_containment(context)
                settings, store_dir = experiment_settings(self._base, context)
                context.output_dir.mkdir(exist_ok=True)
                verify_containment(context)
                self._engines[context_id] = self._build(settings)
                self._identities[context_id] = _identity(settings, context_id, str(store_dir))
            return self._engines[context_id]

    def identity(self, context_id: str) -> BackendIdentity:
        """Return the backend and index identity of a context store."""
        context = self.registry.get(context_id)
        settings, store_dir = experiment_settings(self._base, context)
        return _identity(settings, context_id, str(store_dir))

    def admit(
        self,
        context_id: str,
        definition: Any,
        *,
        inputs: Mapping[str, Any],
        bound_context: str | None = None,
        session: bool = False,
    ) -> ExperimentAdmission:
        """Borrow a context and admit a graph against its Engine.

        The credential check runs before any Engine is built. Validation
        has no side effects. The lease is released when any check fails.

        Args:
            context_id: The selected context.
            definition: Graph definition or mapping.
            inputs: Graph inputs.
            bound_context: Context bound to the bearer credential, if any.
            session: Whether the caller is the browser session.

        Raises:
            ExperimentAdmissionError: The credential, context state or
                graph fails the admission guard.
            PipelineValidationError: The graph or inputs are invalid.
        """
        check_credential_target(
            bound_context=bound_context, target_context=context_id, session=session
        )
        lease = self.registry.acquire(context_id)
        try:
            context = self.registry.get(context_id)
            engine = self.engine(context_id)
            snapshot = engine.validate_pipeline(definition, inputs=dict(inputs))
            identity = self._identities[context_id]
            check_experiment_snapshot(context, snapshot, identity)
        except BaseException:
            lease.release()
            raise
        return ExperimentAdmission(context, engine, snapshot, identity, lease)

    async def run(
        self,
        context_id: str,
        definition: Any,
        *,
        inputs: Mapping[str, Any],
        bound_context: str | None = None,
        session: bool = False,
        on_event: Any = None,
        cancellation: Any = None,
    ) -> ExperimentRunResult:
        """Admit, run and release one experiment graph.

        Returns:
            The pipeline result and its provenance record.
        """
        admission = self.admit(
            context_id, definition, inputs=inputs, bound_context=bound_context, session=session
        )
        return await self.execute(admission, on_event=on_event, cancellation=cancellation)

    async def execute(
        self, admission: ExperimentAdmission, *, on_event: Any = None, cancellation: Any = None
    ) -> ExperimentRunResult:
        """Run an admitted graph and always release its lease.

        A queued job whose context was revoked after admission fails here,
        before the Engine runs. A run that already started is not stopped
        by revocation; cancel it through the run service.

        Raises:
            ExperimentAdmissionError: The context was revoked while queued.
        """
        with admission:
            self.registry.require_active(admission.context.context_id)
            result = await admission.engine.run_pipeline(
                admission.snapshot, on_event=on_event, cancellation=cancellation
            )
            return ExperimentRunResult(result, admission.provenance())

    def revoke(self, context_id: str) -> ExperimentContext:
        """Revoke a context; its Engine closes when no job holds it."""
        return self.registry.revoke(context_id)

    def close(self) -> None:
        """Close every Engine at shutdown.

        Raises:
            RuntimeError: A context still has leases; nothing is closed.
        """
        busy = [cid for cid in self._engines if self.registry.active_leases(cid)]
        if busy:
            raise RuntimeError(
                f"Experiment contexts still borrowed: {', '.join(busy)}; "
                "wait for their jobs to finish, then close again."
            )
        for context_id in list(self._engines):
            self._close_context(context_id)

    def _close_context(self, context_id: str) -> None:
        with self._lock:
            engine = self._engines.pop(context_id, None)
            self._identities.pop(context_id, None)
        if engine is not None:
            engine.close()


__all__ = [
    "STORE_LOCATIONS",
    "ExperimentAdmission",
    "ExperimentAdmissionError",
    "ExperimentEngines",
    "ExperimentRunResult",
    "experiment_registry",
    "experiment_settings",
    "live_backend_identity",
]
