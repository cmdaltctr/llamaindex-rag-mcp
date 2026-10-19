"""Terminal run records, runner events and completed-effect evidence.

The recorder writes every run outcome through the event log, so each status
change and its event commit together before subscribers wake. A run that is
already terminal is never changed again.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from omrg.core.pipelines import PipelineEvent, PipelineResult
from omrg.core.workspace.artefacts import ArtefactStore, bound_preview, preview, to_jsonable
from omrg.core.workspace.events import STATUS_EVENT, RunEventLog
from omrg.core.workspace.jobs import ARTEFACT_ROOT_KEY, RunJob
from omrg.core.workspace.records import TERMINAL_RUN_STATUSES, RunRecord
from omrg.core.workspace.redaction import redact, redact_text
from omrg.core.workspace.repository import WorkspaceRepository

logger = logging.getLogger(__name__)

EFFECT_EVENT = "effect_committed"
_RESULT_STATUS = {s: s for s in ("succeeded", "failed", "cancelled", "interrupted")}
_OUTPUT_PREVIEW_BYTES = 12 * 1024
_ERROR_PREVIEW_CHARS = 2000


def _error_text(error: Any) -> str | None:
    if error is None:
        return None
    return redact_text(str(error))[:_ERROR_PREVIEW_CHARS]


def plain(value: Mapping[str, Any]) -> dict[str, Any]:
    """Return a redacted, JSON-compatible copy of a mapping."""
    return redact(to_jsonable(dict(value)))


def run_artefacts(run: Mapping[str, Any], default: ArtefactStore) -> ArtefactStore:
    """Return the artefact store of *run*: its recorded root, else *default*."""
    root = (run.get("resources") or {}).get(ARTEFACT_ROOT_KEY)
    return ArtefactStore(Path(root)) if root else default


class RunRecorder:
    """Write runner events and terminal run states.

    Args:
        repository: Workspace records.
        log: Event log that commits updates and wakes subscribers.
        artefacts: Private store for results and large previews.
    """

    def __init__(
        self, repository: WorkspaceRepository, log: RunEventLog, artefacts: ArtefactStore
    ) -> None:
        """Bind the recorder to its stores."""
        self._repository = repository
        self._log = log
        self._artefacts = artefacts
        self._stores: dict[str, ArtefactStore] = {}

    def _store(self, run_id: str) -> ArtefactStore:
        """Return the artefact store of a run; read its record once."""
        if run_id not in self._stores:
            run = self._repository.get_run(run_id)
            self._stores[run_id] = run_artefacts(run, self._artefacts)
        return self._stores[run_id]

    def fail_safely(self, run_id: str) -> None:
        """Record a service failure; log instead of raising if that fails too."""
        detail = {"reason": "failed", "error": "the run service could not record the result"}
        try:
            self.end(run_id, "failed", detail)
        except Exception:
            logger.exception("run %s: the failure could not be recorded", run_id)

    async def event(self, run_id: str, event: PipelineEvent) -> None:
        """Commit one runner event with a bounded, redacted summary."""
        kind = getattr(event.kind, "value", str(event.kind))
        raw = {"message": event.message, "data": event.data, "at": event.timestamp.isoformat()}
        name = f"event-{uuid.uuid4().hex[:16]}"
        summary = self._store(run_id).safe_summary(run_id, name, raw)
        try:
            self._log.record(
                run_id, kind=kind, summary=summary, node_id=event.node_id, unit_id=event.unit_id
            )
        except ValueError:
            self._stores.pop(run_id, None)
            logger.warning("run %s: event %s arrived after the run ended", run_id, kind)

    def fail(self, run_id: str, error: str, *, wall: float | None = None) -> None:
        """Record a failed run from an executor error."""
        self.end(run_id, "failed", {"reason": "failed", "error": _error_text(error)}, wall=wall)

    def finish(self, job: RunJob, result: Any, wall: float) -> None:
        """Record the terminal state of a job from its executor result.

        The full redacted result goes to the ``result`` artefact. The event
        holds bounded previews, the measured end-to-end wall time, and each
        node duration separately. Node durations are never summed. A node
        summary that has to be cut keeps its full value in the artefact
        ``node-<index>-summary``, as an event summary does.
        """
        if not isinstance(result, PipelineResult):
            self.fail(job.run_id, f"the executor returned {type(result).__name__}", wall=wall)
            return
        status = _RESULT_STATUS.get(getattr(result.status, "value", ""), "failed")
        data = to_jsonable(result)
        store = self._store(job.run_id)
        for index, outcome in enumerate(data.get("nodes") or []):
            summary = outcome.get("summary") or {}
            outcome["summary"] = store.safe_summary(job.run_id, f"node-{index}-summary", summary)
        ref = store.write_json(job.run_id, "result", {**data, "wall_time_s": wall})
        outputs, outputs_cut = preview(data["outputs"], max_bytes=_OUTPUT_PREVIEW_BYTES)
        durations, _ = bound_preview(
            {n.node_id: n.duration_s for n in result.nodes if n.duration_s is not None}
        )
        error = _error_text(result.error)
        if status != result.status:
            error = error or f"the executor returned the non-terminal status {result.status}"
        effects = list(result.completed_effects)
        effects += [e for e in self.stored_effects(job.run_id) if e not in effects]
        detail = {
            "reason": status,
            "failed_node": result.failed_node,
            "error": error,
            "completed_effects": preview(effects)[0],
        }
        extra = {
            "runner_wall_time_s": result.wall_time_s,
            "node_durations_s": durations,
            "outputs": outputs,
            "outputs_truncated": outputs_cut,
        }
        self.end(job.run_id, status, detail, wall=wall, result_ref=ref, extra=extra)

    def end(
        self,
        run_id: str,
        status: str,
        detail: Mapping[str, Any],
        *,
        wall: float | None = None,
        result_ref: str | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> bool:
        """Record a terminal status once; return ``False`` if already terminal."""
        if self._repository.get_run(run_id)["status"] in TERMINAL_RUN_STATUSES:
            logger.warning("run %s: already terminal; %s not recorded", run_id, status)
            return False
        detail = dict(detail)
        if status != "succeeded" and "completed_effects" not in detail:
            detail["completed_effects"] = preview(self.stored_effects(run_id))[0]
        summary: dict[str, Any] = {"status": status, **detail, **dict(extra or {})}
        if wall is not None:
            summary["wall_time_s"] = round(wall, 6)
        if result_ref is not None:
            summary["result_ref"] = result_ref
        safe = self._store(run_id).safe_summary(run_id, f"status-{status}", summary)
        safe["status"] = status
        if result_ref is not None:
            safe["result_ref"] = result_ref
        failure = None if status == "succeeded" else plain(detail)
        self._log.record(
            run_id,
            kind=STATUS_EVENT,
            summary=safe,
            status=status,
            failure=failure,
            result_ref=result_ref,
        )
        self._stores.pop(run_id, None)
        return True

    def stored_effects(self, run_id: str) -> list[Any]:
        """Return the effects that committed events of a run report."""
        effects: list[Any] = []
        for event in self._repository.list_events(run_id):
            if event["kind"] != EFFECT_EVENT:
                continue
            data = event["summary"].get("data") or {}
            effect = data.get("effect") or event["unit_id"] or event["node_id"]
            if effect is not None and effect not in effects:
                effects.append(effect)
        return effects

    def interrupt_stale(self, run: RunRecord) -> str:
        """Record a run left unfinished by an earlier process as interrupted."""
        detail = {
            "reason": "interrupted",
            "previous_status": run["status"],
            "error": "the process stopped before the run finished; it was not repeated",
        }
        self.end(run["run_id"], "interrupted", detail)
        return run["run_id"]
