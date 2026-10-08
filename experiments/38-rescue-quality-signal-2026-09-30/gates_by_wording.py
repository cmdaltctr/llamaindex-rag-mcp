"""Held-out gates for every Clef-flash build on each fixed wording (amendment A3).

lodo_summary.json reports W1 only, plus a best-wording-per-document choice. This
script scores each wording on its own, so a build can be read wording by wording.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from experiment_io import OUTPUT, atomic_json, read_json
from lodo import held_out, lodo_thresholds
from summarise_lodo import evaluate, load_complete

RUNS = {
    "Hosted (H)": "clefflash",
    "MLX 4-bit (I)": "clefmlx",
    "MLX 8-bit (K)": "clefmlx8",
    "llama.cpp Q8_0 (J)": "clefgguf",
}
WORDINGS = ("W1", "W2", "W3")


def run(source: Path) -> dict:
    """Evaluate every complete build and wording at leave-one-document-out thresholds."""
    labels = read_json(source / "labels.json")["documents"]
    baseline = read_json(source / "output" / "arm_sampled_baseline" / "routing.json")["rows"]
    table: dict[str, dict] = {}
    for label, model in RUNS.items():
        for wording in WORDINGS:
            rows = load_complete(OUTPUT / f"wording_{model}_{wording.lower()}.json")
            if rows is None:
                continue
            result = evaluate(held_out(rows, lodo_thresholds(rows)), baseline, labels)
            lite = result["populations"]["liteparse"]
            table[f"{label}|{wording}"] = {
                "junk_flagged": lite["junk_flagged"],
                "good_flagged": lite["healthy_false_positives"],
                "gates": result["gates"],
                "newly_routed_usable": result["newly_routed_usable"],
            }
    atomic_json(OUTPUT / "clef_flash_gates_by_wording.json", table)
    return table


def main() -> None:
    """Read the source location argument and print one line per build and wording."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-exp", required=True, type=Path)
    for name, row in run(parser.parse_args().source_exp.resolve()).items():
        gates = "/".join("P" if v else "F" for v in row["gates"].values())
        print(
            f"{name:24s} {row['junk_flagged']:2d}/89  {row['good_flagged']:2d}/565  {gates}  "
            f"{','.join(row['newly_routed_usable']) or '-'}"
        )


if __name__ == "__main__":
    main()
