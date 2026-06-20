# Summarise Eval Pattern

Use this as the canonical structure for `experiments/<id>/summarise_eval.py`.

## Requirements

- Read raw `eval_results.json`
- Aggregate metrics by cell and category
- Compute pass gates from the pre-written protocol thresholds
- Write `eval_results.summary.json`
- Write or update `results.md` with executive summary, tables, gates, recommendation

## Skeleton

```python
from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 6) if values else 0.0


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(statistics.quantiles(sorted(values), n=100, method="inclusive")[94], 2)
```

## Aggregate a cell

```python
def _aggregate_cell(cell: dict[str, Any]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in cell.get("queries", []):
        groups["all"].append(row)
        groups[row.get("category") or "unknown"].append(row)

    metrics: dict[str, Any] = {}
    for name, rows in groups.items():
        latencies = [float(row.get("latency_ms", 0.0)) for row in rows]
        metrics[name] = {
            "n": len(rows),
            "coverage_at_20": _mean([row["metrics"].get("coverage_at_20", 0.0) for row in rows]),
            "recall_at_50": _mean([row["metrics"].get("recall_at_50", 0.0) for row in rows]),
            "hit_at_5": _mean([1.0 if row["metrics"].get("hit_at_5") else 0.0 for row in rows]),
            "hit_at_10": _mean([1.0 if row["metrics"].get("hit_at_10") else 0.0 for row in rows]),
            "mrr_at_10": _mean([row["metrics"].get("mrr_at_10", 0.0) for row in rows]),
            "mean_latency_ms": round(statistics.mean(latencies), 2) if latencies else 0.0,
            "p95_latency_ms": _p95(latencies),
        }
    return metrics


def _cell_key(cell: dict[str, Any]) -> str:
    return f"{cell['mode']}__rerank_{str(cell['rerank']).lower()}"
```

## Pass criteria

Implement gates from `protocol.md`, not after-the-fact thresholds.

```python
def _pass_criteria(data: dict[str, Any], aggregates: dict[str, Any]) -> dict[str, Any]:
    baseline = aggregates.get("dense-only__rerank_true", {}).get("all", {})
    candidate = aggregates.get("hybrid_bm25__rerank_true", {}).get("all", {})

    coverage_lift = candidate.get("coverage_at_20", 0.0) - baseline.get("coverage_at_20", 0.0)
    latency_ratio = (
        candidate.get("p95_latency_ms", 0.0) / baseline.get("p95_latency_ms", 0.0)
        if baseline.get("p95_latency_ms", 0.0)
        else float("inf")
    )

    criteria = {
        "primary_quality_lift": {"value": round(coverage_lift, 6), "pass": coverage_lift >= 0.05},
        "latency_guardrail": {"value": round(latency_ratio, 6), "pass": latency_ratio <= 1.5},
    }
    criteria["all_gates_pass"] = all(v.get("pass", False) for v in criteria.values() if isinstance(v, dict))
    criteria["recommendation"] = (
        "ADOPT candidate / propose follow-up change"
        if criteria["all_gates_pass"]
        else "KEEP baseline / document negative or inconclusive result"
    )
    return criteria
```

Customize metric names and thresholds to match the experiment protocol.

## Write results.md

```python
def _write_results_md(data: dict[str, Any], summary: dict[str, Any], path: Path) -> None:
    lines = [
        f"# {data.get('experiment', 'Experiment')} Results",
        "",
        f"**Recommendation:** {summary['pass_criteria']['recommendation']}",
        "",
        "## Executive summary",
        "",
        "TODO: Summarise the bottom line in 1–3 paragraphs.",
        "",
        "## Cell metrics",
        "",
        "| Cell | Category | n | Primary metric | Hit@10 | MRR@10 | P95 ms |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for cell_key, groups in summary["metrics_by_cell"].items():
        for category, metrics in groups.items():
            lines.append(
                f"| {cell_key} | {category} | {metrics['n']} | "
                f"{metrics.get('coverage_at_20', 0.0):.3f} | "
                f"{metrics.get('hit_at_10', 0.0):.3f} | "
                f"{metrics.get('mrr_at_10', 0.0):.3f} | "
                f"{metrics.get('p95_latency_ms', 0.0):.1f} |"
            )
```

```python
    lines.extend(["", "## Pass gates", ""])
    for name, value in summary["pass_criteria"].items():
        if name in {"recommendation", "all_gates_pass"}:
            continue
        lines.append(f"- **{name}**: `{json.dumps(value, ensure_ascii=False)}`")

    lines.extend([
        "",
        "## Conclusion / decision",
        "",
        "TODO: State what ships, what does not ship, and any follow-up experiment.",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")
```

## Main

```python
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=SCRIPT_DIR / "output" / "eval_results.json")
    parser.add_argument("--output", type=Path, default=SCRIPT_DIR / "output" / "eval_results.summary.json")
    parser.add_argument("--results-md", type=Path, default=SCRIPT_DIR / "results.md")
    args = parser.parse_args()

    data = json.loads(args.input.read_text(encoding="utf-8"))
    aggregates = {_cell_key(cell): _aggregate_cell(cell) for cell in data.get("cells", [])}
    summary = {
        "experiment": data.get("experiment"),
        "metrics_by_cell": aggregates,
        "pass_criteria": _pass_criteria(data, aggregates),
    }
```

```python
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_results_md(data, summary, args.results_md)
    print(f"Summary written to {args.output}")
    print(f"Results report written to {args.results_md}")
    print(summary["pass_criteria"]["recommendation"])


if __name__ == "__main__":
    main()
```

## Results.md quality checklist

- Executive summary states the decision in the first screen
- Corpus/setup table includes corpus size, model, reranker, and key env vars
- Metrics table includes all cells and important categories
- Pass gates show raw values and pass/fail booleans
- Negative and inconclusive results are documented honestly
- Recommendation maps directly to a code/config/product decision
- Raw JSON and logs are linked under artefacts
