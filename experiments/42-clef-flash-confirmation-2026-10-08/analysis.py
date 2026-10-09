"""Task 6.3: print the report tables from output/summary.json (no new computation).

uv run --no-sync python analysis.py > output/report_tables.md
"""

from __future__ import annotations

from exp42_io import OUTPUT, read_json

ARMS = {
    "control": "Production today (no check)",
    "A": "Word check (A)",
    "clef": "Clef-flash Q8_0 W1",
}


def pct(x: float | None) -> str:
    """Format a share as a percentage."""
    return "n/a" if x is None else f"{100 * x:.1f}%"


def interval(i: dict) -> str:
    """Format a 95% interval."""
    return f"{pct(i['lower'])} to {pct(i['upper'])}"


def main() -> None:
    """Print Markdown tables."""
    s = read_json(OUTPUT / "summary.json")
    yes = {True: "PASS", False: "FAIL"}
    print(
        "| Arm | Junk caught | Recall (Wilson) | Healthy flagged | Rate (Wilson) | G1 | G2 | G3 |"
    )
    print("| --- | ---: | --- | ---: | --- | --- | --- | --- |")
    for key, name in ARMS.items():
        a = s["arms"][key]
        m = a["populations"]["liteparse"]
        g = a["gates"]
        print(
            f"| {name} | {m['junk_flagged']}/{m['junk_pages']} | {pct(m['junk_recall'])} "
            f"({interval(m['junk_recall_wilson'])}) | {m['healthy_false_positives']}/"
            f"{m['healthy_pages']} | {pct(m['healthy_false_positive_rate'])} "
            f"({interval(m['fp_rate_wilson'])}) | {yes[g['G1']]} | {yes[g['G2']]} "
            f"| {yes[g['G3']]} |"
        )
    print()
    print(
        "| Arm | Document-cluster recall interval | Document-cluster rate interval | AUC | "
        "Rate at threshold x0.9 / x1.1 |"
    )
    print("| --- | --- | --- | ---: | --- |")
    for key in ("A", "clef"):
        m = s["arms"][key]["populations"]["liteparse"]
        sens = m["sensitivity_fp_rate"]
        print(
            f"| {ARMS[key]} | {interval(m['junk_recall_cluster'])} | "
            f"{interval(m['fp_rate_cluster'])} | {m['auc']:.3f} | "
            f"{pct(sens['x0.9'])} / {pct(sens['x1.1'])} |"
        )
    print()
    print(
        "| Arm | Rescued junk-layer documents missed (G1) "
        "| Rescued usable documents sent to OCR (G2) |"
    )
    print("| --- | --- | --- |")
    for key in ("A", "clef"):
        a = s["arms"][key]
        missed = ", ".join(f"`{d}`" for d in a["missed_junk_layer_documents"]) or "none"
        usable = ", ".join(f"`{d}`" for d in a["newly_routed_usable"]) or "none"
        print(f"| {ARMS[key]} | {missed} | {usable} |")
    print()
    m = s["adoption"]
    print(
        f"Margin: recall difference {m['delta']:+.4f} (needs +0.10); McNemar Clef-only "
        f"{m['mcnemar']['b_only']}, A-only {m['mcnemar']['a_only']}, one-sided p "
        f"{m['p_one_sided']:.4f} (needs < 0.05). "
        f"Verdict: {s['verdict']} (OD1 {s['gate_priority']})."
    )


if __name__ == "__main__":
    main()
