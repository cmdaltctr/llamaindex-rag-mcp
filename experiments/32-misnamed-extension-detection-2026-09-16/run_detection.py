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
OUT = EXP / "output"


def _relative(path: Path) -> str:
    """Repo-relative POSIX spelling, so committed evidence carries no workstation paths."""
    return path.resolve().relative_to(REPO).as_posix()


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
    "baseline_pdf": [_relative(p) for p in BASELINE_PDF_DIRS],
    "baseline_text": [_relative(p) for p in BASELINE_TEXT_FILES],
    "swap_pdf_names": [_relative(EXP / "output/work/swap_pdf_names")],
    "swap_text_to_pdf": [_relative(EXP / "output/work/swap_text_to_pdf")],
}

SMOKE_REL = "scripts/magika_label_smoke.py"
TIMEOUT_SECONDS = 300
TIMEOUT_EXIT = 124


def run_set(name: str, rel_paths: list[str]) -> None:
    env = {**os.environ, "PATH": f"{REPO / '.venv/bin'}:{os.environ['PATH']}"}
    started = time.perf_counter()
    try:
        proc = subprocess.run(  # noqa: S603 — fixed smoke-tool invocation
            [sys.executable, str(REPO / SMOKE_REL), "--json", *rel_paths],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            cwd=REPO,
            env=env,
        )
        stdout, stderr = proc.stdout, proc.stderr
        exit_code = proc.returncode
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        # A timeout must still produce a result file so later sets run and
        # the gate sees the failed set instead of a missing one.
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode(errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode(errors="replace")
        stderr = f"{stderr}\nsmoke exceeded {TIMEOUT_SECONDS}s timeout".strip()
        exit_code = TIMEOUT_EXIT
        timed_out = True
    elapsed = round(time.perf_counter() - started, 3)
    result = {
        "set": name,
        "command": ["python", SMOKE_REL, "--json", *rel_paths],
        "exit_code": exit_code,
        "timed_out": timed_out,
        "elapsed_seconds": elapsed,
        "payload": json.loads(stdout) if stdout.strip() else None,
        "stderr": stderr.strip(),
    }
    target = OUT / f"{name}.json"
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(result, indent=2), encoding="utf-8")
    tmp.replace(target)
    print(f"{name}: exit={exit_code} elapsed={elapsed}s timeout={timed_out}", flush=True)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, paths in SETS.items():
        run_set(name, paths)


if __name__ == "__main__":
    main()
