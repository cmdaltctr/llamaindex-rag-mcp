"""Routing-overhead baseline for the OCR gate freeze (task 1.6 / 5.1).

Times ``pdf_inspector.process_pdf`` — the fast-path routing decision —
over every committed PDF fixture. Baseline-only: no candidate path runs
here and no held-out content is extracted beyond what the pinned unit
tests already assert.

Writes output/routing_overhead.json.
"""

from __future__ import annotations

import json
import statistics
import time
from pathlib import Path

import pdf_inspector

EXP_DIR = Path(__file__).resolve().parent
BASE = EXP_DIR.parents[1] / "tests/fixtures/pdf_baseline"
REPS = 20


def main() -> None:
    """Measure routing decision latency per fixture and write JSON."""
    report: dict = {"tool": "pdf_inspector.process_pdf", "reps": REPS, "files": {}}
    for f in sorted(BASE.rglob("*.pdf")):
        times = []
        for _ in range(REPS):
            t0 = time.perf_counter()
            pdf_inspector.process_pdf(str(f))
            times.append((time.perf_counter() - t0) * 1000)
        ordered = sorted(times)
        report["files"][str(f.relative_to(BASE))] = {
            "mean_ms": round(statistics.fmean(times), 3),
            "p95_ms": round(ordered[int(0.95 * len(ordered)) - 1], 3),
            "max_ms": round(ordered[-1], 3),
        }
    report["worst_case_p95_ms"] = max(v["p95_ms"] for v in report["files"].values())

    out = EXP_DIR / "output/routing_overhead.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(report, indent=2), encoding="utf-8")
    tmp.replace(out)
    print(f"worst-case routing p95: {report['worst_case_p95_ms']} ms")


if __name__ == "__main__":
    main()
