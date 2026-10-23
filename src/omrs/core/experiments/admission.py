"""Admission guard for experiment-scoped runs (design D10).

Two checks run before any side effect:

1. :func:`check_credential_target` binds a credential to its context. An
   experiment credential reaches only its own context, never the live
   library. A plain notebook credential cannot select an experiment
   context. A browser session can select any context.
2. :func:`check_experiment_snapshot` checks the admitted graph against
   the context: the Engine store must sit below the context ``output/``
   directory, and every enabled ``SOURCE_COMMIT`` node needs the
   ``ingest`` action and a named destination collection in that store.

Graph validation (``Engine.validate_pipeline``) has no side effects, so a
caller validates, runs these checks, and only then runs the snapshot.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ..pipelines.catalogue import EffectClass
from .contexts import ExperimentContext
from .errors import ExperimentAdmissionError


@dataclass(frozen=True)
class BackendIdentity:
    """Backend and index identity recorded with experiment outputs.

    Attributes:
        context_id: Experiment context id, or ``None`` for the live library.
        store_kind: Vector-store backend name.
        store_path: Absolute store location.
        embedding_provider: Effective embedding provider.
        embedding_model: Embedding model identifier.
    """

    context_id: str | None
    store_kind: str
    store_path: str
    embedding_provider: str
    embedding_model: str

    @property
    def index_identity(self) -> str:
        """Short stable hash of the store location and embedding identity."""
        material = json.dumps(
            [self.store_kind, self.store_path, self.embedding_provider, self.embedding_model]
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]

    def as_record(self) -> dict[str, Any]:
        """Return the identity fields as JSON-ready data."""
        return asdict(self)

    def provenance(self) -> dict[str, Any]:
        """Return the identity fields plus the index identity."""
        return {**self.as_record(), "index_identity": self.index_identity}


def check_credential_target(
    *, bound_context: str | None, target_context: str | None, session: bool
) -> None:
    """Refuse a request whose credential may not reach the target.

    Args:
        bound_context: Context id bound to the bearer credential, if any.
        target_context: Context id the request selects; ``None`` is the
            live library.
        session: Whether the caller is the browser session.

    Raises:
        ExperimentAdmissionError: ``live_library_target`` when an
            experiment credential targets the live library,
            ``experiment_scope_mismatch`` for another context, or
            ``experiment_credential_required`` when a credential without a
            binding selects an experiment context.
    """
    if session or bound_context == target_context:
        return
    if bound_context is None:
        raise ExperimentAdmissionError(
            "experiment_credential_required",
            "Issue a credential bound to this experiment context.",
            target_context,
        )
    if target_context is None:
        raise ExperimentAdmissionError(
            "live_library_target",
            "An experiment credential cannot run graphs against the live library.",
            bound_context,
        )
    raise ExperimentAdmissionError(
        "experiment_scope_mismatch",
        "The credential is bound to a different experiment context.",
        target_context,
    )


def _inside(path: str, parent: Path) -> bool:
    return Path(os.path.realpath(path)).is_relative_to(Path(os.path.realpath(parent)))


def check_experiment_snapshot(
    context: ExperimentContext, snapshot: Any, identity: BackendIdentity
) -> None:
    """Refuse an admitted graph that would write outside its context.

    Args:
        context: The active context the run borrows.
        snapshot: The admitted graph (``AdmissionSnapshot``).
        identity: Backend identity of the Engine that will run it.

    Raises:
        ExperimentAdmissionError: ``commit_outside_context`` when the
            Engine store is not this context's store or a commit names no
            destination; ``action_not_permitted`` when the context does not
            permit ingestion.
    """
    if identity.context_id != context.context_id or not _inside(
        identity.store_path, context.output_dir
    ):
        raise ExperimentAdmissionError(
            "commit_outside_context",
            "The Engine store is not inside this experiment context.",
            context.context_id,
        )
    commits = [
        node
        for node in snapshot.nodes
        if node.enabled and node.effect == EffectClass.SOURCE_COMMIT.value
    ]
    if commits and "ingest" not in context.actions:
        raise ExperimentAdmissionError(
            "action_not_permitted",
            "This experiment context permits read-only graphs only.",
            context.context_id,
        )
    for node in commits:
        if not node.collection:
            raise ExperimentAdmissionError(
                "commit_outside_context",
                f"Commit node {node.node_id!r} names no experiment collection.",
                context.context_id,
            )
