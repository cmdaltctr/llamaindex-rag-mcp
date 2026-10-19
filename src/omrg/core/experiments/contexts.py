"""Approved experiment contexts and their workspace path rules (design D10).

An operator approves one or more experiment roots. Below a root, the
operator registers an experiment workspace. Registration checks the
canonical path and returns an opaque context id. Notebook requests name
that id, never a store URI or a provider. The context's store lives in
``<workspace>/output/``.

This module is pure: it reads path metadata but starts no process, opens
no database and imports no web package. Composition creates directories
and Engines (``omrg.compose_experiments``).
"""

from __future__ import annotations

import os
import secrets
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .errors import ExperimentAdmissionError, ExperimentPathError

#: Store backend for a context that does not declare the store factor.
DEFAULT_STORE_BACKEND = "lancedb"
#: Declared factor that permits a store backend other than the default.
STORE_FACTOR = "store"
#: Actions a context can permit. ``ingest`` permits source commits.
EXPERIMENT_ACTIONS: frozenset[str] = frozenset({"read", "ingest"})
#: Directory below the workspace that holds the store and run outputs.
OUTPUT_DIR_NAME = "output"


@dataclass(frozen=True)
class ExperimentContext:
    """One approved experiment workspace and the record of its approval.

    Attributes:
        context_id: Opaque identifier that requests select.
        name: Operator label.
        root: Canonical approved root that contains the workspace.
        workspace: Canonical workspace directory.
        store_backend: Vector-store backend for the context store.
        declared_factors: Experiment factors the operator declared.
        actions: Permitted actions (subset of :data:`EXPERIMENT_ACTIONS`).
        approved_at: Registration time (UTC).
        revoked_at: Revocation time (UTC), or ``None`` while active.
    """

    context_id: str
    name: str
    root: Path
    workspace: Path
    store_backend: str
    declared_factors: frozenset[str]
    actions: frozenset[str]
    approved_at: datetime
    revoked_at: datetime | None = None

    @property
    def output_dir(self) -> Path:
        """Directory that holds the context store and outputs."""
        return self.workspace / OUTPUT_DIR_NAME

    @property
    def active(self) -> bool:
        """Whether the context accepts new admissions."""
        return self.revoked_at is None

    def record(self) -> dict[str, Any]:
        """Return the approval record as JSON-ready data."""
        return {
            "context_id": self.context_id,
            "name": self.name,
            "root": str(self.root),
            "workspace": str(self.workspace),
            "output_dir": str(self.output_dir),
            "store_backend": self.store_backend,
            "declared_factors": sorted(self.declared_factors),
            "actions": sorted(self.actions),
            "approved_at": self.approved_at.isoformat(),
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None,
            "status": "active" if self.active else "revoked",
        }


def _canonical_root(path: str | Path) -> Path:
    try:
        resolved = Path(path).resolve(strict=True)
    except (OSError, RuntimeError):
        resolved = None
    if resolved is None or not resolved.is_dir():
        raise ExperimentPathError(
            "root_not_approved", f"Approved experiment root {str(path)!r} is not a directory."
        )
    return resolved


def _check_output(workspace: Path) -> None:
    output = workspace / OUTPUT_DIR_NAME
    if output.is_symlink():
        raise ExperimentPathError(
            "symlink_escape", "The workspace 'output' directory must not be a symbolic link."
        )
    if output.exists() and not output.is_dir():
        raise ExperimentPathError(
            "not_a_directory", "The workspace 'output' entry must be a directory."
        )


def resolve_workspace(roots: Iterable[Path], workspace: str | Path) -> tuple[Path, Path]:
    """Return ``(root, canonical workspace)`` for a workspace below an approved root.

    Args:
        roots: Canonical approved roots.
        workspace: Absolute workspace path the operator gave.

    Returns:
        The approved root and the canonical (symlink-resolved) workspace.

    Raises:
        ExperimentPathError: The path is relative, has ``..`` parts, does
            not exist, is not a directory, is a root itself, resolves
            outside every root, or has a linked ``output`` directory.
    """
    raw = Path(workspace)
    if not raw.is_absolute():
        raise ExperimentPathError(
            "not_absolute", "Give the experiment workspace as an absolute path."
        )
    if ".." in raw.parts:
        raise ExperimentPathError("traversal", "The workspace path must not contain '..' parts.")
    try:
        real = raw.resolve(strict=True)
    except (OSError, RuntimeError):
        raise ExperimentPathError("not_found", "The experiment workspace does not exist.") from None
    if not real.is_dir():
        raise ExperimentPathError(
            "not_a_directory", "The experiment workspace must be a directory."
        )
    roots = list(roots)
    if real in roots:
        raise ExperimentPathError(
            "is_root", "Register a directory below the approved root, not the root itself."
        )
    root = next((r for r in roots if real.is_relative_to(r)), None)
    if root is None:
        # The parent sits below a root but the path resolves outside it:
        # a link in the last component escapes the approved root.
        parent = Path(os.path.normpath(raw)).parent.resolve()
        inside = any(parent.is_relative_to(r) for r in roots)
        code = "symlink_escape" if inside else "outside_root"
        raise ExperimentPathError(code, "The workspace is outside every approved experiment root.")
    _check_output(real)
    return root, real


def verify_containment(context: ExperimentContext) -> None:
    """Check again that the context workspace and output stay in place.

    Composition calls this immediately before it builds the store, so a
    link planted after registration cannot move the store.

    Raises:
        ExperimentPathError: The workspace moved, or ``output`` is a link.
    """
    try:
        real = context.workspace.resolve(strict=True)
    except (OSError, RuntimeError):
        real = None
    if real != context.workspace or not real.is_relative_to(context.root):
        raise ExperimentPathError(
            "symlink_escape", "The experiment workspace no longer resolves to its approved path."
        )
    _check_output(real)


@dataclass
class ExperimentLease:
    """A borrowed context. Release it once the job ends; release is idempotent."""

    context_id: str
    _release: Callable[[ExperimentLease], None] = field(repr=False)
    released: bool = False

    def release(self) -> None:
        """Return the context to the registry."""
        if not self.released:
            self.released = True
            self._release(self)

    def __enter__(self) -> ExperimentLease:
        """Hold the lease for a ``with`` block."""
        return self

    def __exit__(self, *exc: object) -> None:
        """Release the lease when the block ends, also on error."""
        self.release()


class ExperimentRegistry:
    """In-memory registry of approved experiment contexts for one launch."""

    def __init__(
        self,
        approved_roots: Iterable[str | Path],
        *,
        store_backends: Iterable[str] = (DEFAULT_STORE_BACKEND,),
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        """Approve the given roots.

        Args:
            approved_roots: Directories below which workspaces may be registered.
            store_backends: Backends composition can place in a workspace.
            clock: Time source (tests pass a fixed clock).

        Raises:
            ExperimentPathError: A root is not an existing directory.
        """
        self._roots = tuple(_canonical_root(r) for r in approved_roots)
        self._backends = frozenset(store_backends)
        self._clock = clock or (lambda: datetime.now(UTC))
        self._contexts: dict[str, ExperimentContext] = {}
        self._leases: dict[str, int] = {}
        self._listeners: list[Callable[[str], None]] = []
        self._lock = threading.Lock()

    @property
    def approved_roots(self) -> tuple[Path, ...]:
        """Canonical approved roots."""
        return self._roots

    def register(
        self,
        workspace: str | Path,
        *,
        name: str = "",
        actions: Iterable[str] = ("read", "ingest"),
        store_backend: str = DEFAULT_STORE_BACKEND,
        declared_factors: Iterable[str] = (),
    ) -> ExperimentContext:
        """Approve a workspace and return its new context.

        Raises:
            ExperimentPathError: The path check fails, the workspace overlaps
                an active context, an action is unknown, or the store backend
                is unknown or not a declared factor.
        """
        wanted = frozenset(actions)
        factors = frozenset(declared_factors)
        if not wanted or not wanted <= EXPERIMENT_ACTIONS:
            raise ExperimentPathError(
                "action_unknown", f"Actions must be among: {', '.join(sorted(EXPERIMENT_ACTIONS))}."
            )
        if store_backend not in self._backends:
            raise ExperimentPathError(
                "store_unknown", f"Store backend {store_backend!r} is not available here."
            )
        if store_backend != DEFAULT_STORE_BACKEND and STORE_FACTOR not in factors:
            raise ExperimentPathError(
                "store_not_declared",
                f"Use {DEFAULT_STORE_BACKEND} or declare '{STORE_FACTOR}' as an experiment factor.",
            )
        root, real = resolve_workspace(self._roots, workspace)
        with self._lock:
            for other in self._contexts.values():
                if other.active and (
                    real.is_relative_to(other.workspace) or other.workspace.is_relative_to(real)
                ):
                    raise ExperimentPathError(
                        "overlaps_context", "The workspace overlaps an active experiment context."
                    )
            context = ExperimentContext(
                context_id="exp_" + secrets.token_hex(8),
                name=name[:80],
                root=root,
                workspace=real,
                store_backend=store_backend,
                declared_factors=factors,
                actions=wanted,
                approved_at=self._clock(),
            )
            self._contexts[context.context_id] = context
            self._leases[context.context_id] = 0
        return context

    def contexts(self) -> list[ExperimentContext]:
        """Return every context, active and revoked, in registration order."""
        return list(self._contexts.values())

    def get(self, context_id: str) -> ExperimentContext:
        """Return a context by id.

        Raises:
            ExperimentAdmissionError: ``experiment_context_unknown``.
        """
        context = self._contexts.get(context_id)
        if context is None:
            raise ExperimentAdmissionError(
                "experiment_context_unknown", "No experiment context has this id.", context_id
            )
        return context

    def require_active(self, context_id: str) -> ExperimentContext:
        """Return an active context.

        Raises:
            ExperimentAdmissionError: Unknown or revoked context.
        """
        context = self.get(context_id)
        if not context.active:
            raise ExperimentAdmissionError(
                "experiment_context_revoked",
                "The experiment context was revoked; register the workspace again.",
                context_id,
            )
        return context

    def revoke(self, context_id: str) -> ExperimentContext:
        """Revoke a context. Held leases stay valid until their jobs release them.

        Returns:
            The revoked context record.
        """
        with self._lock:
            context = self.get(context_id)
            if context.active:
                context = replace(context, revoked_at=self._clock())
                self._contexts[context_id] = context
            idle = self._leases[context_id] == 0
        if idle:
            self._notify_idle(context_id)
        return context

    def acquire(self, context_id: str) -> ExperimentLease:
        """Borrow an active context for one job.

        Raises:
            ExperimentAdmissionError: Unknown or revoked context.
        """
        with self._lock:
            self.require_active(context_id)
            self._leases[context_id] += 1
        return ExperimentLease(context_id, self._release)

    def active_leases(self, context_id: str) -> int:
        """Return the number of unreleased leases on a context."""
        return self._leases.get(context_id, 0)

    def add_idle_listener(self, listener: Callable[[str], None]) -> None:
        """Call *listener* with the id when a revoked context has no leases."""
        self._listeners.append(listener)

    def _release(self, lease: ExperimentLease) -> None:
        with self._lock:
            self._leases[lease.context_id] -= 1
            idle = self._leases[lease.context_id] == 0
            revoked = not self._contexts[lease.context_id].active
        if idle and revoked:
            self._notify_idle(lease.context_id)

    def _notify_idle(self, context_id: str) -> None:
        for listener in list(self._listeners):
            listener(context_id)
