"""Answer stage progress: stage names and a context reporter.

A stage is reported where its work starts (add-answer-stage-progress,
design D3).  The shared steps in ``stages.py`` and the direct pipeline call
:func:`report_stage`; it does nothing unless a caller installed a reporter
with :func:`reporting`.  The reporter lives in a ``ContextVar``, so each
request task sees only its own reporter, and graph nodes started with
``asyncio.create_task`` inherit it.

A callback receives :class:`AnswerStage` values only, never text.  A broken
callback is logged and swallowed, so it can never fail an answer.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Generator
from contextlib import contextmanager
from contextvars import ContextVar
from enum import StrEnum

logger = logging.getLogger(__name__)


class AnswerStage(StrEnum):
    """The stages of one answer, in the order they run."""

    SEARCHING = "searching"
    WRITING = "writing"
    CITING = "citing"
    VERIFYING = "verifying"


#: Callback that receives each stage as its work starts.
StageCallback = Callable[[AnswerStage], None]

_RANK = {stage: index for index, stage in enumerate(AnswerStage)}


class StageReporter:
    """Forward stages to a callback, in order, each at most once.

    A repeat of the current stage and a stage that ranks below one already
    sent are dropped, so the order the callback sees is monotonic.
    """

    def __init__(self, callback: StageCallback) -> None:
        """Store the callback.

        Args:
            callback: Called on the event loop with each new stage.
        """
        self._callback = callback
        self._rank = -1

    def enter(self, stage: AnswerStage) -> None:
        """Report ``stage`` unless it repeats or goes backwards.

        Args:
            stage: The stage whose work starts now.
        """
        rank = _RANK[stage]
        if rank <= self._rank:
            return
        self._rank = rank
        try:
            self._callback(stage)
        except Exception:  # noqa: BLE001 - a consumer must never fail an answer
            logger.warning("Answer stage callback failed for %s", stage.value, exc_info=True)


_ACTIVE: ContextVar[StageReporter | None] = ContextVar("omrg_answer_stage_reporter", default=None)


@contextmanager
def reporting(on_stage: StageCallback | None) -> Generator[None]:
    """Install a stage reporter for the enclosed block.

    Args:
        on_stage: The callback to report to.  With ``None`` nothing is
            installed and any outer reporter stays active.

    Yields:
        None.
    """
    if on_stage is None:
        yield
        return
    token = _ACTIVE.set(StageReporter(on_stage))
    try:
        yield
    finally:
        _ACTIVE.reset(token)


def report_stage(stage: AnswerStage) -> None:
    """Report ``stage`` to the active reporter, if there is one.

    Args:
        stage: The stage whose work starts now.
    """
    reporter = _ACTIVE.get()
    if reporter is not None:
        reporter.enter(stage)
