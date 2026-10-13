"""Standard ``search()`` reproduces the recorded retrieval parity fixtures.

Task 3.1 (``add-local-web-pipeline-workspace``): the fixtures under
``tests/fixtures/pipeline_parity/retrieval/`` were recorded from
``search()`` before the sizing, policy, filtering and fallback seams were
extracted. This test proves the standard path still reproduces them,
including score kinds, rank provenance, tie ordering and the public
result shape. The canonical graph template test (task 3.2 onwards)
reuses the same harness and cases.
"""

from __future__ import annotations

import pytest
from tests.fixtures.pipeline_parity.retrieval import harness

_CASES = harness.load_cases()


def test_parity_cases_cover_the_required_rules() -> None:
    """The recorded set covers every rule the seams own."""
    names = {case["name"] for case in _CASES}
    assert {
        "dense_rerank_success_div30",
        "dense_rerank_failure_dense_threshold",
        "hybrid_no_rerank_dense_eligibility",
        "hybrid_rerank_failure_fallback",
        "fetch_k_override_pool",
        "policy_default_technical_disables",
        "public_shape_hybrid",
        "empty_collection",
    } <= names


@pytest.mark.parametrize("case", _CASES, ids=[c["name"] for c in _CASES])
def test_search_reproduces_recorded_parity_case(case, monkeypatch, effective_settings) -> None:
    """``search()`` returns the recorded rows, score kinds and order."""
    corpus = harness.load_corpus()
    rows = harness.run_search(
        case, corpus, monkeypatch=monkeypatch, settings_factory=effective_settings
    )

    expected = case["expected"]
    assert harness.public_keys(rows) == expected["keys"]
    actual = harness.project(rows)
    assert len(actual) == len(expected["rows"])
    for got, want in zip(actual, expected["rows"], strict=True):
        assert got.keys() == want.keys()
        for key, value in want.items():
            if isinstance(value, float):
                assert got[key] == pytest.approx(value, rel=1e-12, abs=0.0), key
            else:
                assert got[key] == value, key
