"""Fit the two frozen thresholds on committed Experiment 38 scores (tasks 2.1, 2.2).

Uses the Experiment 38 equal-cost rule (signal_stats.equal_cost_threshold) on the
LiteParse healthy pages of all 40 Experiment 38 documents. No model call.

    uv run --no-sync python fit_thresholds.py           # print values
    uv run --no-sync python fit_thresholds.py --write   # also write plan.json
"""

from __future__ import annotations

import argparse
import subprocess
import sys

from exp42_io import EXP33, EXP38, EXP_DIR, atomic_json, load_module, read_json, sha256

INPUTS = {
    "clef_flash_q8_0_w1": EXP38 / "output" / "wording_clefgguf_w1.json",
    "word_check_a": EXP38 / "output" / "candidate_a.json",
}
EXPECTED_A = 0.8834080717
HEALTHY_PAGES = 565


def fit(rows: list[dict]) -> float:
    """Return the Experiment 38 equal-cost threshold on LiteParse rows."""
    stats = load_module(EXP38 / "signal_stats.py", "exp38_signal_stats")
    primary = [r for r in rows if r["tier"] == "liteparse"]
    if sum(r["class"] == "healthy" for r in primary) != HEALTHY_PAGES:
        raise ValueError("input does not hold the 565 Experiment 38 healthy LiteParse pages")
    return stats.equal_cost_threshold(primary)


def check_exp33_freeze() -> None:
    """Require Experiment 33 freeze.py --check to pass (run where its corpus lives)."""
    from exp42_io import EXPERIMENTS

    source = EXPERIMENTS.parent.parent / "llamaindex-rag-mcp-v3" / "experiments" / EXP33.name
    result = subprocess.run(  # noqa: S603, S607 - fixed argv
        [sys.executable, "freeze.py", "--check"],
        cwd=source,
        capture_output=True,
        text=True,
        check=False,
    )
    if "freeze verified" not in result.stdout.splitlines():
        raise RuntimeError("Experiment 33 freeze check failed")


def main() -> None:
    """Fit, check candidate A against the reported value, optionally write plan.json."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    check_exp33_freeze()
    commit = subprocess.run(  # noqa: S603, S607
        ["git", "log", "-1", "--format=%H", "--", *map(str, INPUTS.values())],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
        cwd=EXP_DIR,
    ).stdout.strip()
    values = {k: fit(read_json(p)["rows"]) for k, p in INPUTS.items()}
    if abs(values["word_check_a"] - EXPECTED_A) > 5e-11:
        raise SystemExit(f"candidate A threshold {values['word_check_a']} != {EXPECTED_A}: stop")
    for key, value in values.items():
        print(f"{key}: {value!r} ({INPUTS[key].name}, sha256 {sha256(INPUTS[key])[:12]}…)")
    if args.write:
        plan_path = EXP_DIR / "plan.json"
        current = read_json(plan_path)
        for key, value in values.items():
            current["thresholds"][key].update(
                value=value,
                input_sha256=sha256(INPUTS[key]),
                commit=commit,
                status="fitted 2026-10-09 by fit_thresholds.py; frozen",
            )
        atomic_json(plan_path, current)


if __name__ == "__main__":
    main()
