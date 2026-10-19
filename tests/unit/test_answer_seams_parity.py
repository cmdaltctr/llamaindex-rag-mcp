"""Answer-family parity fixtures through the standard ``answer()`` path.

Task 3.6 of ``add-local-web-pipeline-workspace``. Each case in
``tests/fixtures/pipeline_parity/answer/cases.json`` drives the existing
``omrg.core.answer.answer`` entry point with pre-retrieved rows and
scripted fake seams. ``expected.json`` holds the outcome each case
produced on the pre-extraction pipeline, so these tests prove the seam
extraction kept the public result shape, citation guarantees, failure
attribution and verification labels unchanged.

No test reaches a real model or network: every seam is a fake.
"""

from __future__ import annotations

from typing import Any

import pytest
from tests.fixtures.pipeline_parity.answer.harness import (
    CASE_NAMES,
    EXPECTED,
    case_by_name,
    run_case_through_answer,
)


def test_every_case_has_an_expected_outcome() -> None:
    """The golden file covers exactly the fixture cases."""
    assert sorted(EXPECTED) == sorted(CASE_NAMES)


@pytest.mark.parametrize("name", CASE_NAMES)
async def test_answer_path_matches_pre_extraction_outcome(
    name: str, effective_settings: Any
) -> None:
    """``answer()`` returns the same shape, labels and calls as before."""
    observed = await run_case_through_answer(case_by_name(name), effective_settings())
    assert observed == EXPECTED[name]


async def test_no_evidence_fixture_never_calls_the_model(effective_settings: Any) -> None:
    """Design D3: empty evidence returns ``no_evidence`` with no model call."""
    observed = await run_case_through_answer(
        case_by_name("no_evidence_with_model"), effective_settings()
    )
    assert observed["result"]["status"] == "no_evidence"
    assert observed["model_calls"] == 0
    assert observed["result"]["diagnostics"]["completion_calls"] == 0
