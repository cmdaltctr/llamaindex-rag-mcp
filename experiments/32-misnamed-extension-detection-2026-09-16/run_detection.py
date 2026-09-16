"""Run the label smoke over each Experiment 32 set.

Detection only: each invocation is ``scripts/magika_label_smoke.py
--json <dir>`` in a subprocess. Payload, exit code, and elapsed time
are saved atomically per set. The venv bin directory is placed on
PATH so the injected ``magika`` binary resolves.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

EXP = Path(__file__).resolve().parent
REPO = EXP.parent.parent
SMOKE = REPO / "scripts/magika_label_smoke.py"
OUT = EXP / "output"

# Baseline text uses the exact pin-gate files, passed explicitly so
# the path set matches the gate record.
BASELINE_TEXT_FILES = [
    REPO / "src/omrg/compose.py",
    REPO / "src/omrg/core/ingestion/pipeline.py",
    REPO / "src/omrg/integrations/magika.py",
    REPO / "src/omrg/core/codebase/codebase_map.py",
    REPO / "README.md",
    REPO / "AGENTS.md",
    REPO / "docs/guides/architecture.md",
    REPO / "docs/guides/ingestion.md",
    REPO / "experiments/20-citation-faithfulness-2026-09-02/corpus/source-01-aurora.txt",
    REPO / "experiments/20-citation-faithfulness-2026-09-02/corpus/source-02-birch.txt",
    REPO
    / (
        "experiments/19-lancedb-lifecycle-qualification-2026-08-21/"
        "fixtures/corpus_replacement/bravo_harbour.txt"
    ),
]

BASELINE_PDF_DIRS = [
    REPO / "experiments/31-reader-rescue-retrieval-impact-2026-09-15/corpus/heldout",
    REPO / "experiments/31-reader-rescue-retrieval-impact-2026-09-15/corpus/distractors",
]

SETS: dict[str, list[str]] = {
    "baseline_pdf": [str(p) for p in BASELINE_PDF_DIRS],
    "baseline_text": [str(p) for p in BASELINE_TEXT_FILES],
    "swap_pdf_names": [str(EXP / "output/work/swap_pdf_names")],
    "swap_text_to_pdf": [str(EXP / "output/work/swap_text_to_pdf")],
}


def run_set(name: str, paths: list[str]) -> None:
    env = {**os.environ, "PATH": f"{REPO / '.venv/bin'}:{os.environ['PATH']}"}
    started = time.perf_counter()
    proc = subprocess.run(  # noqa: S603 — fixed smoke-tool invocation
        [sys.executable, str(SMOKE), "--json", *paths],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=REPO,
        env=env,
    )
    elapsed = round(time.perf_counter() - started, 3)
    result = {
        "set": name,
        "command": [str(SMOKE), "--json", *paths],
        "exit_code": proc.returncode,
        "elapsed_seconds": elapsed,
        "payload": json.loads(proc.stdout) if proc.stdout.strip() else None,
        "stderr": proc.stderr.strip(),
    }
    target = OUT / f"{name}.json"
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(result, indent=2), encoding="utf-8")
    tmp.replace(target)
    print(f"{name}: exit={proc.returncode} elapsed={elapsed}s", flush=True)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, paths in SETS.items():
        run_set(name, paths)


if __name__ == "__main__":
    main()
