"""Shared harness for the answer-family parity fixtures (task 3.6).

Loads ``cases.json`` and ``expected.json``, builds scripted fake seams,
and runs one case through the standard ``answer()`` path. The expected
file was captured from the pre-extraction pipeline; timing diagnostics
(``*_ms``) are stripped because they are not deterministic.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from omrg.core.settings import AnswerBlock, EffectiveSettings

_HERE = Path(__file__).resolve().parent
CASES: dict[str, Any] = json.loads((_HERE / "cases.json").read_text(encoding="utf-8"))
EXPECTED: dict[str, Any] = json.loads((_HERE / "expected.json").read_text(encoding="utf-8"))
CASE_NAMES: list[str] = [case["name"] for case in CASES["cases"]]
QUERY = "parity question"
SOURCE = "server"


class ScriptedSeam:
    """Fake async completion seam driven by a fixture spec.

    A ``{"replies": [...]}`` spec returns each reply in turn and repeats
    the last one. A ``{"raise": "message"}`` spec raises
    ``ConnectionError(message)`` on every call. Every call is recorded.
    """

    def __init__(self, spec: dict[str, Any]) -> None:
        """Store the spec; nothing runs until the seam is awaited."""
        self._replies = list(spec.get("replies") or [])
        self._raise = spec.get("raise")
        self._last = self._replies[0] if self._replies else ""
        self.prompts: list[str] = []

    async def __call__(self, prompt: str) -> str:
        """Record the prompt, then reply or raise per the spec."""
        self.prompts.append(prompt)
        if self._raise is not None:
            raise ConnectionError(self._raise)
        if self._replies:
            self._last = self._replies.pop(0)
        return self._last


def case_by_name(name: str) -> dict[str, Any]:
    """Return the fixture case called *name*."""
    return next(case for case in CASES["cases"] if case["name"] == name)


def case_rows(case: dict[str, Any]) -> list[dict[str, Any]]:
    """Expand a case's row keys into fresh ``search()``-shaped row dicts."""
    return [json.loads(json.dumps(CASES["rows"][key])) for key in case["rows"]]


def case_settings(base: EffectiveSettings, case: dict[str, Any]) -> EffectiveSettings:
    """Overlay the case's answer block onto the conftest base settings."""
    block = case.get("answer_block") or {}
    return base.model_copy(update={"answer": AnswerBlock(**block)})


def make_seam(spec: dict[str, Any] | None) -> ScriptedSeam | None:
    """Build a fake seam from a fixture spec, or ``None`` for no model."""
    return None if spec is None else ScriptedSeam(spec)


def strip_timings(result: dict[str, Any]) -> dict[str, Any]:
    """Drop non-deterministic ``*_ms`` diagnostics; keep everything else."""
    clean = json.loads(json.dumps(result))
    diagnostics = clean.get("diagnostics")
    if isinstance(diagnostics, dict):
        clean["diagnostics"] = {k: v for k, v in diagnostics.items() if not k.endswith("_ms")}
    return clean


def observation(
    result: dict[str, Any], complete: ScriptedSeam | None, judge: ScriptedSeam | None
) -> dict[str, Any]:
    """Package a result and its seam call counts for golden comparison."""
    return {
        "result": strip_timings(result),
        "result_keys": list(result),
        "model_calls": len(complete.prompts) if complete else 0,
        "judge_calls": len(judge.prompts) if judge else 0,
    }


async def run_case_through_answer(case: dict[str, Any], base: EffectiveSettings) -> dict[str, Any]:
    """Run one fixture case through the standard ``answer()`` path."""
    from omrg.core.answer import answer

    complete = make_seam(case.get("complete"))
    judge = make_seam(case.get("judge"))
    result = await answer(
        QUERY,
        complete=complete,
        verify_complete=judge,
        verify_unavailable_reason=case.get("verify_unavailable_reason"),
        completion_source=SOURCE,
        rows=case_rows(case),
        include_diagnostics=True,
        effective_settings=case_settings(base, case),
    )
    return observation(result, complete, judge)
