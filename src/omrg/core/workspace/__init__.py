"""Workspace application records and the local run service.

This package defines plain-data records, the repository protocol, the
bounded single-consumer run service, redaction, private artefacts and
previewed cleanup of finished runs. It
does not import a storage engine, a web framework or domain implementations;
composition injects the repository, the executor and the admission checks.

The service names (``RunService``, ``ShutdownReport``, ``RETRYABLE_STATUSES``)
load on first use, so importing the record contracts does not import the
pipeline package.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from omrg.core.workspace.artefacts import (
    MAX_ARTEFACT_BYTES,
    MAX_PREVIEW_ROWS,
    MAX_SUMMARY_BYTES,
    MAX_TEXT_BYTES,
    ArtefactStore,
    bound_preview,
    preview,
    to_jsonable,
)
from omrg.core.workspace.cleanup import (
    DEFAULT_CLEANUP_TTL_SECONDS,
    CleanupPreview,
    CleanupRejected,
    CleanupResult,
    CleanupRun,
    CleanupSelector,
    WorkspaceCleanup,
    WorkspaceLayout,
)
from omrg.core.workspace.cleanup_files import CleanupFile, CleanupSkip
from omrg.core.workspace.events import STATUS_EVENT, RunEventLog
from omrg.core.workspace.jobs import (
    DEFAULT_MAX_WAITING,
    Admission,
    Admitter,
    JobQueue,
    QueueFullError,
    RunExecutor,
    RunJob,
    RunStateError,
    ServiceClosedError,
    UnsafeInputError,
    WorkspaceRunError,
)
from omrg.core.workspace.records import (
    NONTERMINAL_RUN_STATUSES,
    PLUGIN_COMPATIBILITY,
    RUN_ORIGINS,
    RUN_STATUSES,
    TERMINAL_RUN_STATUSES,
    PipelineRecord,
    PluginCompatibility,
    PluginRecord,
    RevisionRecord,
    RunEventRecord,
    RunOrigin,
    RunRecord,
    RunStatus,
    canonical_json,
    content_hash,
)
from omrg.core.workspace.redaction import (
    REDACTED,
    contains_secret,
    is_secret_key,
    redact,
    redact_text,
)
from omrg.core.workspace.repository import WorkspaceRepository

__all__ = [
    "DEFAULT_CLEANUP_TTL_SECONDS",
    "DEFAULT_MAX_WAITING",
    "MAX_ARTEFACT_BYTES",
    "MAX_PREVIEW_ROWS",
    "MAX_SUMMARY_BYTES",
    "MAX_TEXT_BYTES",
    "NONTERMINAL_RUN_STATUSES",
    "PLUGIN_COMPATIBILITY",
    "REDACTED",
    "RETRYABLE_STATUSES",
    "RUN_ORIGINS",
    "RUN_STATUSES",
    "STATUS_EVENT",
    "TERMINAL_RUN_STATUSES",
    "Admission",
    "Admitter",
    "ArtefactStore",
    "CleanupFile",
    "CleanupPreview",
    "CleanupRejected",
    "CleanupResult",
    "CleanupRun",
    "CleanupSelector",
    "CleanupSkip",
    "JobQueue",
    "PipelineRecord",
    "PluginCompatibility",
    "PluginRecord",
    "QueueFullError",
    "RevisionRecord",
    "RunEventLog",
    "RunEventRecord",
    "RunExecutor",
    "RunJob",
    "RunOrigin",
    "RunRecord",
    "RunService",
    "RunStateError",
    "RunStatus",
    "ServiceClosedError",
    "ShutdownReport",
    "UnsafeInputError",
    "WorkspaceCleanup",
    "WorkspaceLayout",
    "WorkspaceRepository",
    "WorkspaceRunError",
    "bound_preview",
    "canonical_json",
    "contains_secret",
    "content_hash",
    "is_secret_key",
    "preview",
    "redact",
    "redact_text",
    "to_jsonable",
]

_LAZY_SERVICE_NAMES = frozenset({"RETRYABLE_STATUSES", "RunService", "ShutdownReport"})

if TYPE_CHECKING:
    from omrg.core.workspace.service import RETRYABLE_STATUSES, RunService, ShutdownReport


def __getattr__(name: str) -> Any:
    """Import the run service on first use (PEP 562)."""
    if name in _LAZY_SERVICE_NAMES:
        from omrg.core.workspace import service

        return getattr(service, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
