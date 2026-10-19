"""Answer-family graph adapters reproduce the standard ``answer()`` path.

Task 3.6 of ``add-local-web-pipeline-workspace``. Each of the 18 cases
in ``tests/fixtures/pipeline_parity/answer/cases.json`` runs through the
four registered answer adapters, chained by hand in canonical order. The
result must equal the golden outcome that ``answer()`` produced before
the seam extraction (timings stripped, call counts kept).

One case needs a translation. The fixture gives a transport-supplied
judge reason. A graph host reports an unbuildable judge as a raising
``verify_llm`` factory, so that case compares with ``answer()`` called
with the reason ``Engine.answer`` derives from the same failure.
"""

from __future__ import annotations

from typing import Any

import pytest
from tests.fixtures.pipeline_parity.answer.harness import (
    CASE_NAMES,
    EXPECTED,
    case_by_name,
    case_rows,
    case_settings,
    observation,
    run_case_through_answer,
)
from tests.unit.test_answer_graph_adapters_support import (
    UNKNOWN_PROVIDER,
    case_resources,
    run_answer_chain,
)

_TRANSPORT_REASON_CASE = "verification_no_judge_transport_reason"


async def run_case_through_graph(case: dict[str, Any], base: Any) -> dict[str, Any]:
    """Run one fixture case through the hand-chained graph adapters."""
    resources, complete, judge = case_resources(case)
    result = await run_answer_chain(case_settings(base, case), case_rows(case), resources)
    return observation(result, complete, judge)


async def _expected(name: str, base: Any) -> dict[str, Any]:
    """Return the existing-path outcome a graph run must equal."""
    if name != _TRANSPORT_REASON_CASE:
        return EXPECTED[name]
    case = dict(case_by_name(name))
    case["verify_unavailable_reason"] = (
        f"verification provider unavailable: ValueError: {UNKNOWN_PROVIDER}"
    )
    return await run_case_through_answer(case, base)


@pytest.mark.parametrize("name", CASE_NAMES)
async def test_graph_chain_matches_standard_answer_path(name: str, effective_settings: Any) -> None:
    """Graph adapters give the same result, keys and model calls as ``answer()``."""
    base = effective_settings()
    observed = await run_case_through_graph(case_by_name(name), base)
    assert observed == await _expected(name, base)


def test_parity_covers_all_eighteen_cases() -> None:
    """The graph parity run covers every recorded case."""
    assert len(CASE_NAMES) == 18
    assert sorted(CASE_NAMES) == sorted(EXPECTED)
