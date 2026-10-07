"""Experiment 39 analysis: print the report tables from ``output/summary.json``.

Reads the summary only. Runs no scoring and calls no reader.

    uv run python analysis.py
"""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent / "output"
RULES = ("C0", "C1", "C3", "C0@0.5", "C0@0.6", "C0@0.7", "C0@0.8", "C0@0.9")
NON_LATIN = {"io01": "Devanagari", "io02": "Arabic", "io03": "Arabic", "io07": "Bengali"}


def row(*cells: object) -> str:
    """Format one markdown table row."""
    return "| " + " | ".join(str(c) for c in cells) + " |"


def gate_table(summary: dict) -> list[str]:
    """Return the gate table: one line per rule."""
    lines = [
        row(
            "Rule",
            "Escalated",
            "Kept bad (no io06)",
            "Kept bad (with io06)",
            "Non-Latin kept",
            "G1",
            "G2",
            "G3",
        ),
        row(*["---"] * 8),
    ]
    for rule in RULES:
        m = summary["metrics"][rule]
        g = m["gates"]
        lines.append(
            row(
                rule,
                f"{m['escalated_share']:.3f}",
                f"{m['kept_bad_share_without_io06']:.3f}",
                f"{m['kept_bad_share_with_io06']:.3f}",
                f"{m['non_latin_kept']} of 129",
                *("pass" if g[k] else "fail" for k in ("G1", "G2", "G3")),
            )
        )
    return lines


def document_table(summary: dict) -> list[str]:
    """Return per-document escalation for the three candidates."""
    docs = summary["metrics"]["C0"]["per_document"]
    lines = [row("Document", "Script", "Pages", "C0", "C1", "C3"), row(*["---"] * 6)]
    for doc, info in docs.items():
        cells = [
            f"{summary['metrics'][r]['per_document'][doc]['escalated']}" for r in ("C0", "C1", "C3")
        ]
        lines.append(row(f"`{doc}`", NON_LATIN.get(doc, ""), info["pages"], *cells))
    return lines


def io06_table(summary: dict) -> list[str]:
    """Return the io06 column: bad pages and how many each rule escalates."""
    lines = [
        row("Rule", "io06 pages", "Bad (recall < 0.5)", "Bad escalated", "Share"),
        row(*["---"] * 5),
    ]
    for rule in ("C0", "C1", "C3"):
        io = summary["metrics"][rule]["io06"]
        n = round(io["bad_escalated_share"] * io["bad_pages"])
        lines.append(row(rule, io["pages"], io["bad_pages"], n, f"{io['bad_escalated_share']:.3f}"))
    return lines


def c4_table(summary: dict) -> list[str]:
    """Return the exploratory engine-signal AUCs."""
    c4 = summary["c4"]
    lines = [
        row("Signal", "AUC (one-sided)", "AUC (two-sided)", "Follow-up (>= 0.8)"),
        row(*["---"] * 4),
    ]
    for name in ("discarded_regions", "chars_low_is_positive"):
        s = c4[name]
        lines.append(
            row(
                name,
                f"{s['auc_one_sided']:.3f}",
                f"{s['auc_two_sided']:.3f}",
                "yes" if s["follow_up"] else "no",
            )
        )
    lines.append(
        f"\n{c4['positives']} positives (io06, recall < 0.5), {c4['negatives']} negatives."
    )
    return lines


def main() -> None:
    """Print every table the report cites."""
    summary = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))
    bounds = summary["gate_bounds"]
    print(f"O = {summary['O']:.4f}; G2 <= {bounds['G2_max']}; G3 <= {bounds['G3_max']:.4f}")
    print(f"Winner: {summary['winner']}\n")
    for title, lines in (
        ("Gates", gate_table(summary)),
        ("Escalated pages per non-Latin document and others (gated)", document_table(summary)),
        ("io06", io06_table(summary)),
        ("C4", c4_table(summary)),
    ):
        print(f"### {title}\n")
        print("\n".join(lines), "\n")
    figure = summary["figure_only_escalated_share"]
    print("### Figure-only diagnostic (65 pages), escalated share\n")
    print(", ".join(f"{r} {figure[r]:.3f}" for r in RULES))


if __name__ == "__main__":
    main()
