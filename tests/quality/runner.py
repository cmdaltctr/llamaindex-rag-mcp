"""Small-corpus retrieval quality gate helpers.

The gate detects configuration and formula regressions in dense score
conversion, reciprocal rank fusion, threshold handling, and final ranking.
It cannot detect subtle embedding-model quality drift. Use the experiments
process for broader model evaluation and production-corpus calibration.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .metrics import _recall_mrr

QUALITY_DIR = Path(__file__).resolve().parent
CORPUS_DIR = QUALITY_DIR / "corpus"
GOLDEN_PATH = QUALITY_DIR / "golden_queries.json"
BASELINE_PATH = QUALITY_DIR / "baseline.json"


def _normalise_text(text: str) -> str:
    """Normalise line endings and trailing whitespace for fixture identity."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return "\n".join(line.rstrip() for line in lines).strip() + "\n"


def load_golden_queries() -> list[dict[str, Any]]:
    """Load the committed golden-query manifest."""
    data = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("golden_queries.json must contain a JSON list")
    return data


def fixture_identities() -> tuple[str, str]:
    """Return deterministic SHA-256 identities for corpus and query fixtures."""
    corpus_hash = hashlib.sha256()
    for path in sorted(CORPUS_DIR.glob("*.txt")):
        corpus_hash.update(path.name.encode())
        corpus_hash.update(b"\0")
        corpus_hash.update(_normalise_text(path.read_text(encoding="utf-8")).encode())
        corpus_hash.update(b"\0")

    queries = load_golden_queries()
    canonical_queries = json.dumps(
        queries,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return corpus_hash.hexdigest(), hashlib.sha256(canonical_queries).hexdigest()


def load_baseline() -> dict[str, Any]:
    """Load the committed quality baseline."""
    data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("baseline.json must contain a JSON object")
    return data


def validate_baseline(
    baseline: dict[str, Any],
    *,
    require_tier1: bool,
    require_tier2: bool,
) -> None:
    """Validate baseline schema, fixture identity, and required measurements."""
    if baseline.get("schema_version") != 1:
        raise ValueError("baseline schema_version must be 1")

    corpus_id, query_set_id = fixture_identities()
    for field, actual in (("corpus_id", corpus_id), ("query_set_id", query_set_id)):
        if baseline.get(field) != actual:
            raise ValueError(
                f"baseline {field} does not match fixtures; "
                "run an explicit baseline measurement"
            )

    for tier, required in (("tier1", require_tier1), ("tier2", require_tier2)):
        payload = baseline.get(tier)
        if not isinstance(payload, dict):
            raise ValueError(f"baseline {tier} must be an object")
        for field in ("measurement_date", "measured", "floor"):
            if field not in payload:
                raise ValueError(f"baseline {tier}.{field} is required")
        required_fields = ("measurement_date", "measured", "floor")
        if required and any(payload.get(field) is None for field in required_fields):
            raise ValueError(
                f"baseline {tier} measurement is pending; "
                "run and commit an explicit baseline measurement"
            )
        if payload.get("measured") is not None:
            _validate_metric_pair(payload["measured"], f"{tier}.measured")
        if payload.get("floor") is not None:
            _validate_metric_pair(payload["floor"], f"{tier}.floor")


def _validate_metric_pair(metrics: Any, label: str) -> None:
    """Validate one Recall@10 and MRR@10 pair."""
    if not isinstance(metrics, dict):
        raise ValueError(f"baseline {label} must be an object")
    for name in ("recall@10", "mrr@10"):
        value = metrics.get(name)
        if not isinstance(value, (int, float)) or not 0.0 <= float(value) <= 1.0:
            raise ValueError(f"baseline {label}.{name} must be between 0 and 1")


def measure_rows(rows: list[dict[str, Any]]) -> dict[str, float]:
    """Measure Recall@10 and MRR@10 for query result rows."""
    recall, mrr = _recall_mrr(rows, 10)
    return {"recall@10": recall, "mrr@10": mrr}


def assert_metric_floors(
    *,
    tier: str,
    actual: dict[str, float],
    baseline: dict[str, Any],
) -> None:
    """Assert both metric floors with diagnostic failure messages."""
    payload = baseline[tier]
    for name in ("recall@10", "mrr@10"):
        measured = float(payload["measured"][name])
        floor = float(payload["floor"][name])
        observed = float(actual[name])
        assert observed >= floor, (
            f"{tier} {name} regression: measured baseline={measured:.6f}, "
            f"required floor={floor:.6f}, actual={observed:.6f}"
        )


def measurement_record(
    rows: list[dict[str, Any]],
    *,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return metrics and per-query ranks for baseline evidence."""
    record: dict[str, Any] = {
        "metrics": measure_rows(rows),
        "queries": [
            {
                "id": row["id"],
                "expected_sources": row["expected_sources"],
                "sources": row["sources"],
            }
            for row in rows
        ],
    }
    if extra:
        record.update(extra)
    return record
