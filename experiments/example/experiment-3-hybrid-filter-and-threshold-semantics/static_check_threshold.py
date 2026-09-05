"""Static evidence for H4: where thresholds are compared against scores.

Protocol §14 H4 requires proof that no code path compares the positive
dense threshold with the fused RRF score.  This script walks the AST of
the production retrieval modules, records every comparison site whose
operands mention a threshold on one side and a score on the other, and
labels the score kind each site can see at that point.  The output is a
committed artefact cited from ``results.md``; the script never modifies
production code.

Run (from the repository root)::

    uv run --no-sync python \\
        experiments/example/experiment-3-hybrid-filter-and-threshold-semantics/static_check_threshold.py
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

TARGETS = [
    PROJECT_ROOT / "src" / "omrg" / "core" / "retrieval" / "pipeline.py",
    PROJECT_ROOT / "src" / "omrg" / "core" / "retrieval" / "policy.py",
]
OUTPUT = SCRIPT_DIR / "output" / "static_check" / "threshold_application_sites.json"


def _texts(node: ast.AST) -> set[str]:
    """Return every identifier, attribute and string-constant text in *node*."""
    found: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            found.add(child.id)
        elif isinstance(child, ast.Attribute):
            found.add(child.attr)
        elif isinstance(child, ast.Constant) and isinstance(child.value, str):
            found.add(child.value)
    return found


def _mentions(node: ast.AST, *substrings: str) -> bool:
    """Return whether any text in *node* contains a substring."""
    return any(any(s in text for s in substrings) for text in _texts(node))


def _snippet(source: list[str], node: ast.AST) -> str:
    lines = source[node.lineno - 1 : node.end_lineno]
    return "\n".join(line.rstrip() for line in lines)


def scan(path: Path) -> list[dict[str, Any]]:
    """Record every comparison joining a threshold with a score operand."""
    source = path.read_text(encoding="utf-8").splitlines()
    tree = ast.parse("\n".join(source))
    sites: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        operands = [node.left, *node.comparators]
        threshold_side = any(_mentions(op, "threshold") for op in operands)
        score_side = any(
            _mentions(op, "score", "fused") and not _mentions(op, "threshold") for op in operands
        )
        if threshold_side and score_side:
            sites.append(
                {
                    "file": str(path.relative_to(PROJECT_ROOT)),
                    "line": node.lineno,
                    "end_line": node.end_lineno,
                    "code": _snippet(source, node),
                    "score_operand_names": sorted(
                        {
                            text
                            for op in operands
                            for text in _texts(op)
                            if ("score" in text or "fused" in text) and "threshold" not in text
                        }
                    ),
                }
            )
    return sites


def main() -> None:
    sites: list[dict[str, Any]] = []
    for target in TARGETS:
        sites.extend(scan(target))
    sites.sort(key=lambda item: (item["file"], item["line"]))

    fused_comparisons = [
        site for site in sites if any("fused" in name for name in site["score_operand_names"])
    ]
    payload = {
        "targets": [str(t.relative_to(PROJECT_ROOT)) for t in TARGETS],
        "threshold_vs_score_comparison_sites": sites,
        "threshold_vs_fused_score_comparison_sites": fused_comparisons,
        "fused_score_thresholded": bool(fused_comparisons),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT} ({len(sites)} threshold-vs-score sites)", flush=True)
    for site in sites:
        print(f"  {site['file']}:{site['line']} operands={site['score_operand_names']}", flush=True)
    print(
        "H4 static gate: threshold-vs-fused comparisons = "
        f"{len(fused_comparisons)} ({'FAIL' if fused_comparisons else 'PASS'})",
        flush=True,
    )


if __name__ == "__main__":
    main()
