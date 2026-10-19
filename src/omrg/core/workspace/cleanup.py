"""Previewed cleanup of workspace run records and run artefacts (design D7).

Cleanup has two steps. :meth:`WorkspaceCleanup.preview_cleanup` lists the
finished runs, events and artefact files that a selector matches, and
issues a single-use token. :meth:`WorkspaceCleanup.apply_cleanup` takes the
token, repeats the preview, and removes exactly the listed items only when
nothing changed.

Cleanup deletes rows in the workspace record database and regular files in
``<workspace>/artefacts/<run_id>/``. It never deletes pipelines, revisions,
plugin registrations, uploads, source documents, vector stores, notebooks
or experiment outputs. It never follows a symbolic link: a link in the
artefact tree is reported and left in place. Active runs (queued, running
or cancelling) are never selected.
"""

from __future__ import annotations

import hashlib
import math
import secrets
import threading
from collections import OrderedDict
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from omrg.core.workspace.cleanup_files import (
    CleanupFile,
    CleanupSkip,
    remove_run_files,
    scan_run_files,
)
from omrg.core.workspace.records import TERMINAL_RUN_STATUSES, RunRecord, canonical_json
from omrg.core.workspace.repository import WorkspaceRepository

DEFAULT_CLEANUP_TTL_SECONDS = 300.0
DEFAULT_MAX_PENDING_CLEANUPS = 64
INTERRUPTED_WARNING = (
    "The selection includes interrupted runs. An interrupted run can have changed a "
    "vector store before it stopped. Check source completeness before you remove its record."
)


def default_workspace() -> Path:
    """Return the default workspace directory, ``~/.omrg/workspace``."""
    return Path.home() / ".omrg" / "workspace"


@dataclass(frozen=True)
class WorkspaceLayout:
    """Fixed names inside one workspace directory.

    Attributes:
        root: The workspace directory (default ``~/.omrg/workspace``).
    """

    root: Path

    @property
    def records(self) -> Path:
        """The SQLite file with application records."""
        return self.root / "workspace.db"

    @property
    def lock(self) -> Path:
        """The advisory lock file that one web server holds for this workspace."""
        return self.root / ".lock"

    @property
    def artefacts(self) -> Path:
        """The private run artefacts, one directory per run."""
        return self.root / "artefacts"

    @property
    def uploads(self) -> Path:
        """Workspace-managed uploads. Cleanup never touches them."""
        return self.root / "uploads"


@dataclass(frozen=True)
class CleanupSelector:
    """Which finished runs a cleanup selects. Every given criterion must hold.

    Attributes:
        older_than_days: Runs that finished at least this many days ago.
        statuses: Runs with one of these finished statuses.
        run_id: One specific run.

    Raises:
        ValueError: If no criterion is given, a status is not a finished
            status, or the age is negative or not finite.
    """

    older_than_days: float | None = None
    statuses: tuple[str, ...] = ()
    run_id: str | None = None

    def __post_init__(self) -> None:
        """Validate and normalise the criteria."""
        statuses = tuple(sorted(set(self.statuses)))
        object.__setattr__(self, "statuses", statuses)
        if self.older_than_days is None and not statuses and self.run_id is None:
            raise ValueError("a cleanup selector needs at least one criterion")
        unknown = set(statuses) - TERMINAL_RUN_STATUSES
        if unknown:
            allowed = ", ".join(sorted(TERMINAL_RUN_STATUSES))
            raise ValueError(f"cleanup selects finished runs only ({allowed}), not {unknown}")
        days = self.older_than_days
        if days is not None and (not math.isfinite(days) or days < 0):
            raise ValueError(f"older_than_days must be a finite number >= 0, not {days}")
        if self.run_id is not None and not self.run_id:
            raise ValueError("run_id must not be empty")

    @classmethod
    def older_than(cls, days: float) -> CleanupSelector:
        """Select runs that finished at least ``days`` days ago."""
        return cls(older_than_days=days)

    @classmethod
    def by_status(cls, *statuses: str) -> CleanupSelector:
        """Select finished runs with one of ``statuses``."""
        return cls(statuses=statuses)

    @classmethod
    def run(cls, run_id: str) -> CleanupSelector:
        """Select one run."""
        return cls(run_id=run_id)

    def as_dict(self) -> dict[str, Any]:
        """Return the canonical, JSON-compatible form."""
        return {
            "older_than_days": self.older_than_days,
            "statuses": list(self.statuses),
            "run_id": self.run_id,
        }


@dataclass(frozen=True)
class CleanupRun:
    """One finished run a cleanup removes, with its event count and files."""

    run_id: str
    status: str
    finished_at: str | None
    events: int
    files: tuple[CleanupFile, ...]


@dataclass(frozen=True)
class CleanupPreview:
    """What a confirmed cleanup will remove. Nothing changed yet."""

    token: str
    selector: CleanupSelector
    expires_at: str
    runs: tuple[CleanupRun, ...]
    skipped: tuple[CleanupSkip, ...]
    warnings: tuple[str, ...]

    @property
    def totals(self) -> dict[str, int]:
        """Counts of runs, events and files, and the file bytes, to remove."""
        files = [file for run in self.runs for file in run.files]
        return {
            "runs": len(self.runs),
            "events": sum(run.events for run in self.runs),
            "files": len(files),
            "bytes": sum(file.bytes for file in files),
        }

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible form for a transport."""
        runs = [
            {**asdict(run), "files": [{"ref": f.ref, "bytes": f.bytes} for f in run.files]}
            for run in self.runs
        ]
        return {
            "token": self.token,
            "selector": self.selector.as_dict(),
            "expires_at": self.expires_at,
            "runs": runs,
            "skipped": [asdict(skip) for skip in self.skipped],
            "warnings": list(self.warnings),
            "totals": self.totals,
        }


@dataclass(frozen=True)
class CleanupResult:
    """What a confirmed cleanup removed, and what it could not remove."""

    runs_removed: int
    events_removed: int
    files_removed: int
    bytes_removed: int
    failed: tuple[CleanupSkip, ...]
    skipped: tuple[CleanupSkip, ...]


class CleanupRejected(Exception):
    """A cleanup token cannot be applied. Nothing was removed.

    Attributes:
        reason: ``unknown``, ``expired``, ``selector`` or ``stale``.
    """

    def __init__(self, reason: str, message: str) -> None:
        """Store the reason code and the message."""
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class _Pending:
    selector: CleanupSelector
    cutoff: datetime
    marker: str
    expires: datetime


def _finished(run: RunRecord) -> datetime | None:
    stamp = run["finished_at"]
    return None if stamp is None else datetime.fromisoformat(stamp)


class WorkspaceCleanup:
    """Preview and apply cleanup of finished runs in one workspace.

    Args:
        repository: The workspace records.
        artefacts_root: The run artefact directory (``WorkspaceLayout.artefacts``).
        clock: Returns the current time; injected in tests.
        ttl_seconds: Seconds a preview token stays valid.
        max_pending: Unapplied previews kept; the oldest go first.
    """

    def __init__(
        self,
        repository: WorkspaceRepository,
        artefacts_root: Path,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        ttl_seconds: float = DEFAULT_CLEANUP_TTL_SECONDS,
        max_pending: int = DEFAULT_MAX_PENDING_CLEANUPS,
    ) -> None:
        """Create a service with no pending previews."""
        self._repository = repository
        self._root = Path(artefacts_root)
        self._clock = clock
        self._ttl = timedelta(seconds=ttl_seconds)
        self.max_pending = max_pending
        self._pending: OrderedDict[str, _Pending] = OrderedDict()
        self._lock = threading.Lock()
        self._apply_lock = threading.Lock()

    @classmethod
    def for_layout(
        cls, repository: WorkspaceRepository, layout: WorkspaceLayout, **options: Any
    ) -> WorkspaceCleanup:
        """Create a service for the artefact directory of ``layout``."""
        return cls(repository, layout.artefacts, **options)

    def preview_cleanup(self, selector: CleanupSelector) -> CleanupPreview:
        """List what a cleanup would remove and issue a single-use token.

        Raises:
            KeyError: If ``selector.run_id`` names an unknown run.
        """
        now = self._clock()
        cutoff = now - timedelta(days=selector.older_than_days or 0)
        runs, skipped, marker = self._plan(selector, cutoff)
        token = "wc_" + secrets.token_urlsafe(24)
        expires = now + self._ttl
        with self._lock:
            self._pending[token] = _Pending(selector, cutoff, marker, expires)
            while len(self._pending) > self.max_pending:
                self._pending.popitem(last=False)
        warnings = (INTERRUPTED_WARNING,) if any(r.status == "interrupted" for r in runs) else ()
        return CleanupPreview(token, selector, expires.isoformat(), runs, skipped, warnings)

    def apply_cleanup(
        self, token: str, *, selector: CleanupSelector | None = None
    ) -> CleanupResult:
        """Remove exactly the items that the token's preview listed.

        Records go first, in one transaction; files go after. A file that
        cannot be removed safely stays and is reported in ``failed``.

        Args:
            token: The token from :meth:`preview_cleanup`. It is spent on
                every call, accepted or not.
            selector: When given, it must equal the previewed selector.

        Raises:
            CleanupRejected: For an unknown, used, expired, mismatched or
                stale token. Nothing is removed.
        """
        with self._lock:
            pending = self._pending.pop(token, None)
        if pending is None:
            raise CleanupRejected("unknown", "Unknown or used cleanup token. Preview again.")
        if self._clock() > pending.expires:
            raise CleanupRejected("expired", "The cleanup preview expired. Preview again.")
        if selector is not None and selector != pending.selector:
            raise CleanupRejected("selector", "The selection differs from the preview.")
        with self._apply_lock:
            runs, skipped, marker = self._plan(pending.selector, pending.cutoff)
            if marker != pending.marker:
                raise CleanupRejected("stale", "The workspace changed. Preview again.")
            try:
                counts = self._repository.delete_runs([run.run_id for run in runs])
            except (KeyError, ValueError) as exc:
                raise CleanupRejected("stale", f"Records changed: {exc}. Preview again.") from exc
            removed, failed = remove_run_files(self._root, [(r.run_id, r.files) for r in runs])
        return CleanupResult(
            runs_removed=counts["runs"],
            events_removed=counts["events"],
            files_removed=len(removed),
            bytes_removed=sum(file.bytes for file in removed),
            failed=tuple(failed),
            skipped=skipped,
        )

    # --- planning ----------------------------------------------------------

    def _plan(
        self, selector: CleanupSelector, cutoff: datetime
    ) -> tuple[tuple[CleanupRun, ...], tuple[CleanupSkip, ...], str]:
        everything = self._repository.list_runs()
        if selector.run_id is not None:
            candidates = [self._repository.get_run(selector.run_id)]
        else:
            candidates = everything
        skipped: list[CleanupSkip] = []
        chosen: dict[str, RunRecord] = {}
        for run in candidates:
            if run["status"] not in TERMINAL_RUN_STATUSES:
                if selector.run_id is not None:
                    reason = f"run is active ({run['status']}); cleanup never touches active runs"
                    skipped.append(CleanupSkip(f"run {run['run_id']}", reason))
                continue
            if self._matches(selector, cutoff, run):
                chosen[run["run_id"]] = run
        skipped.extend(self._drop_referenced(chosen, everything))
        files, file_skips = scan_run_files(self._root, sorted(chosen))
        skipped.extend(file_skips)
        runs = tuple(
            CleanupRun(
                run_id=run["run_id"],
                status=run["status"],
                finished_at=run["finished_at"],
                events=run["last_sequence"],
                files=files.get(run["run_id"], ()),
            )
            for run in sorted(chosen.values(), key=lambda r: (r["created_at"], r["run_id"]))
        )
        state = {
            "selector": selector.as_dict(),
            "cutoff": cutoff.isoformat(),
            "runs": [{**asdict(run), "files": [asdict(f) for f in run.files]} for run in runs],
            "skipped": [asdict(skip) for skip in skipped],
        }
        marker = hashlib.sha256(canonical_json(state).encode("utf-8")).hexdigest()
        return runs, tuple(skipped), marker

    @staticmethod
    def _matches(selector: CleanupSelector, cutoff: datetime, run: RunRecord) -> bool:
        if selector.run_id is not None and run["run_id"] != selector.run_id:
            return False
        if selector.statuses and run["status"] not in selector.statuses:
            return False
        if selector.older_than_days is not None:
            finished = _finished(run)
            return finished is not None and finished <= cutoff
        return True

    @staticmethod
    def _drop_referenced(
        chosen: dict[str, RunRecord], everything: Iterable[RunRecord]
    ) -> list[CleanupSkip]:
        """Keep every selected run that a kept run names as its retry source."""
        runs = list(everything)
        skipped: list[CleanupSkip] = []
        changed = True
        while changed:
            changed = False
            for run in runs:
                source = run["source_run_id"]
                if source in chosen and run["run_id"] not in chosen:
                    del chosen[source]
                    reason = f"kept run {run['run_id']} refers to it as its retry source"
                    skipped.append(CleanupSkip(f"run {source}", reason))
                    changed = True
        return skipped
