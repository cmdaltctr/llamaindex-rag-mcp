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

from omrs.core.workspace.artefacts import (
    MAX_ARTEFACT_BYTES,
    MAX_PREVIEW_ROWS,
    MAX_SUMMARY_BYTES,
    MAX_TEXT_BYTES,
    ArtefactStore,
    bound_preview,
    preview,
    to_jsonable,
)
from omrs.core.workspace.cleanup import (
    DEFAULT_CLEANUP_TTL_SECONDS,
    CleanupPreview,
    CleanupRejected,
    CleanupResult,
    CleanupRun,
    CleanupSelector,
    WorkspaceCleanup,
    WorkspaceLayout,
    default_workspace,
)
from omrs.core.workspace.cleanup_files import CleanupFile, CleanupSkip
from omrs.core.workspace.events import STATUS_EVENT, RunEventLog
from omrs.core.workspace.jobs import (
    ARTEFACT_ROOT_KEY,
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
from omrs.core.workspace.records import (
    NONTERMINAL_RUN_STATUSES,
    PLUGIN_COMPATIBILITY,
    PROFILE_BASES,
    PROFILE_ID_PATTERN,
    PROFILE_SLOTS,
    RESERVED_PROFILE_IDS,
    RUN_ORIGINS,
    RUN_STATUSES,
    TASK_LAYOUT_KEY,
    TERMINAL_RUN_STATUSES,
    PipelineRecord,
    PluginCompatibility,
    PluginRecord,
    ProfileRecord,
    RevisionRecord,
    RunEventRecord,
    RunOrigin,
    RunRecord,
    RunStatus,
    canonical_json,
    content_hash,
)
from omrs.core.workspace.redaction import (
    REDACTED,
    contains_secret,
    is_secret_key,
    redact,
    redact_text,
)
from omrs.core.workspace.repository import ProfileRepository, WorkspaceRepository

__all__ = [
    "ARTEFACT_ROOT_KEY",
    "DEFAULT_CLEANUP_TTL_SECONDS",
    "DEFAULT_MAX_WAITING",
    "MAX_ARTEFACT_BYTES",
    "MAX_PREVIEW_ROWS",
    "MAX_SUMMARY_BYTES",
    "MAX_TEXT_BYTES",
    "NONTERMINAL_RUN_STATUSES",
    "PLUGIN_COMPATIBILITY",
    "PROFILE_BASES",
    "PROFILE_ID_PATTERN",
    "PROFILE_SLOTS",
    "REDACTED",
    "RESERVED_PROFILE_IDS",
    "RETRYABLE_STATUSES",
    "RUN_ORIGINS",
    "RUN_STATUSES",
    "STATUS_EVENT",
    "TASK_LAYOUT_KEY",
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
    "ProfileRecord",
    "ProfileRepository",
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
    "default_workspace",
    "is_secret_key",
    "preview",
    "redact",
    "redact_text",
    "to_jsonable",
]

_LAZY_SERVICE_NAMES = frozenset({"RETRYABLE_STATUSES", "RunService", "ShutdownReport"})

if TYPE_CHECKING:
    from omrs.core.workspace.service import RETRYABLE_STATUSES, RunService, ShutdownReport


def __getattr__(name: str) -> Any:
    """Import the run service on first use (PEP 562)."""
    if name in _LAZY_SERVICE_NAMES:
        from omrs.core.workspace import service

        return getattr(service, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
