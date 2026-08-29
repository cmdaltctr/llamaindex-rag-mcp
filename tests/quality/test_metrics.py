"""Tests for retrieval-quality metrics, fixtures, imports, and baseline schema."""

from __future__ import annotations

import ast

import pytest
from tests.quality import metrics
from tests.quality.metrics import _recall_mrr
from tests.quality.runner import (
    CORPUS_DIR,
    QUALITY_DIR,
    assert_metric_floors,
    fixture_identities,
    load_baseline,
    load_golden_queries,
    validate_baseline,
)


@pytest.mark.parametrize(
    ("rows", "expected"),
    [
        (
            [{"sources": ["source-a.txt"], "expected_sources": ["source-a.txt"]}],
            (1.0, 1.0),
        ),
        (
            [{"sources": ["decoy.txt", "source-a.txt"], "expected_sources": ["source-a.txt"]}],
            (1.0, 0.5),
        ),
        (
            [{"sources": ["decoy.txt"], "expected_sources": ["source-a.txt"]}],
            (0.0, 0.0),
        ),
        (
            [
                {
                    "sources": ["/tmp/source-b.txt"],
                    "expected_sources": ["source-a.txt", "source-b.txt"],
                }
            ],
            (1.0, 1.0),
        ),
        ([], (0.0, 0.0)),
    ],
    ids=["rank-one", "rank-two", "miss", "multiple-expected", "empty"],
)
def test_recall_mrr_cases(rows: list[dict], expected: tuple[float, float]) -> None:
    """The copied metric handles its required ranking cases."""
    assert _recall_mrr(rows, 10) == expected


def test_metric_cases_detect_a_deliberate_source_match_break(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A deliberately broken matcher changes the known rank-one result."""
    monkeypatch.setattr(metrics, "_src_match", lambda _source, _expected: False)
    rows = [{"sources": ["source-a.txt"], "expected_sources": ["source-a.txt"]}]
    assert metrics._recall_mrr(rows, 10) != (1.0, 1.0)


def test_recall_mrr_rank_two_and_miss_scenario() -> None:
    """One rank-two hit and one miss produce Recall 0.5 and MRR 0.25."""
    rows = [
        {
            "sources": ["decoy.txt", "source-a.txt"],
            "expected_sources": ["source-a.txt"],
        },
        {"sources": ["decoy.txt"], "expected_sources": ["source-b.txt"]},
    ]
    assert _recall_mrr(rows, 10) == (0.5, 0.25)


def test_fixed_fixtures_are_complete_and_deterministic() -> None:
    """The corpus and golden mappings satisfy their committed contract."""
    paths = sorted(CORPUS_DIR.glob("*.txt"))
    queries = load_golden_queries()
    assert len(paths) == 20
    assert len(queries) == 12

    source_names = {path.name for path in paths}
    source_ids = {
        path.read_text(encoding="utf-8")
        .splitlines()[0]
        .removeprefix("Source identifier: ")
        .removesuffix(".")
        for path in paths
    }
    assert len(source_names) == len(source_ids) == 20
    assert len({query["id"] for query in queries}) == 12
    for query in queries:
        assert query["query"].strip()
        assert query["expected_sources"]
        assert set(query["expected_sources"]) <= source_names

    first = fixture_identities()
    second = fixture_identities()
    assert first == second
    assert all(len(value) == 64 for value in first)


def test_quality_modules_never_import_experiments() -> None:
    """Quality modules must remain independent of the experiment tree."""
    violations: list[str] = []
    for path in sorted(QUALITY_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            if any(name == "experiments" or name.startswith("experiments.") for name in names):
                violations.append(f"{path.name}:{node.lineno}")
    assert violations == []


def test_pending_baseline_schema_and_fixture_identity_are_valid() -> None:
    """Pending Tier 2 measurements remain explicit and identities stay pinned."""
    validate_baseline(
        load_baseline(),
        require_tier1=False,
        require_tier2=False,
    )


def test_baseline_schema_rejects_fixture_identity_drift() -> None:
    """A committed fixture change requires an explicit new measurement."""
    baseline = load_baseline()
    baseline["corpus_id"] = "0" * 64
    with pytest.raises(ValueError, match="corpus_id does not match fixtures"):
        validate_baseline(baseline, require_tier1=False, require_tier2=False)


def test_baseline_schema_rejects_unknown_version() -> None:
    """The quality runner fails closed on an unknown baseline schema."""
    baseline = load_baseline()
    baseline["schema_version"] = 2
    with pytest.raises(ValueError, match="schema_version must be 1"):
        validate_baseline(baseline, require_tier1=False, require_tier2=False)


def test_floor_failure_reports_baseline_floor_and_actual() -> None:
    """A quality failure includes all values needed to diagnose the gate."""
    baseline = {
        "tier1": {
            "measured": {"recall@10": 0.9, "mrr@10": 0.8},
            "floor": {"recall@10": 0.85, "mrr@10": 0.75},
        }
    }
    with pytest.raises(
        AssertionError,
        match=(
            r"measured baseline=0\.900000, required floor=0\.850000, "
            r"actual=0\.500000"
        ),
    ):
        assert_metric_floors(
            tier="tier1",
            actual={"recall@10": 0.5, "mrr@10": 0.8},
            baseline=baseline,
        )
