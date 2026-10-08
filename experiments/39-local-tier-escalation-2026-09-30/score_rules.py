"""Experiment 39: score local OCR escalation rules on Experiment 33 rows.

Re-scores the 464 saved local OCR pages. No OCR runs. Standard library only.

    uv run python score_rules.py --e33-dir <experiment 33 directory>

The Experiment 33 directory supplies ``freeze.py``, ``pages.json`` and the saved
page text. The text is gitignored, so it can sit in another worktree. The run
stops unless ``freeze.py --check`` prints ``freeze verified`` and the rows file
hash equals ``source_data.rows_sha256`` in ``plan.json``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import unicodedata
from collections import Counter
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent
E33_DEFAULT = EXP_DIR.parent / "33-ocr-routing-natural-positive-2026-09-17"
PLAN = EXP_DIR / "plan.json"
RULES_OUT = EXP_DIR / "output" / "rules.json"

CONFIDENCE_CUT = 0.8  # OCR_LOCAL_MIN_CONFIDENCE, the shipped post-check
CJK_THRESHOLD = 0.05
SWEEP_CUTS = (0.5, 0.6, 0.7, 0.8, 0.9)

#: Name prefixes (``unicodedata.name``) that fall in the single CJK group.
_CJK_PREFIXES = (
    "CJK ",
    "HIRAGANA",
    "KATAKANA",
    "HANGUL",
    "HALFWIDTH KATAKANA",
    "HALFWIDTH HANGUL",
)
_DISCARDED = re.compile(r"discarded (\d+) regions")


def script_group(char: str) -> str | None:
    """Return the script group of one letter, or ``None`` for a non-letter.

    The group is the first word of the Unicode name. CJK ideographs, Hiragana,
    Katakana and Hangul share the group ``"CJK"``.
    """
    if not char.isalpha():
        return None
    name = unicodedata.name(char, "")
    if not name:
        return "UNKNOWN"
    if name.startswith(_CJK_PREFIXES):
        return "CJK"
    return name.split(" ", 1)[0]


def script_counts(text: str) -> Counter[str]:
    """Count the letters of *text* per script group."""
    return Counter(g for g in map(script_group, text) if g is not None)


def cjk_share(text: str) -> float:
    """Return CJK letters divided by all letters (0.0 when there are none)."""
    counts = script_counts(text)
    total = sum(counts.values())
    return counts["CJK"] / total if total else 0.0


def discarded_regions(warnings: list[str]) -> int:
    """Sum the discarded-region counts the engine reports in *warnings*."""
    return sum(int(m.group(1)) for w in warnings if (m := _DISCARDED.search(w)))


def c0(row: dict, text: str, cut: float = CONFIDENCE_CUT) -> bool:
    """Shipped post-check: empty text, low or unreported confidence, hosted flag."""
    confidence = row["confidence"]
    return (
        not text.strip()
        or confidence is None
        or confidence < cut
        or bool(row["hosted_recommended"])
    )


def c1(text: str, threshold: float = CJK_THRESHOLD) -> bool:
    """Script mismatch: empty output, or CJK share at or above *threshold*."""
    return not text.strip() or cjk_share(text) >= threshold


def c3(row: dict, text: str) -> bool:
    """Combination: C0 or C1."""
    return c0(row, text) or c1(text)


def decisions(row: dict, text: str) -> dict[str, bool]:
    """Return one escalate decision per rule for a page."""
    out = {"C0": c0(row, text), "C1": c1(text), "C3": c3(row, text)}
    for cut in SWEEP_CUTS:
        out[f"C0@{cut}"] = c0(row, text, cut)
    return out


def sha256_file(path: Path) -> str:
    """Return the hex SHA-256 digest of *path*."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_freeze_check(e33_dir: Path) -> str:
    """Run ``freeze.py --check`` and return its verdict line, or exit on drift."""
    done = subprocess.run(  # noqa: S603 — fixed argv, no shell
        [sys.executable, str(e33_dir / "freeze.py"), "--check"],
        capture_output=True,
        text=True,
        cwd=e33_dir,
        check=False,
    )
    if done.returncode != 0 or "freeze verified" not in done.stdout:
        sys.exit(f"freeze check failed:\n{done.stdout}{done.stderr}")
    return "freeze verified"


def load_pages(e33_dir: Path, plan: dict) -> list[dict]:
    """Load the 464 rows with their saved text, after the data checks."""
    source = plan["source_data"]
    rows_path = e33_dir / "output" / "local_ocr" / "pages.json"
    digest = sha256_file(rows_path)
    if digest != source["rows_sha256"]:
        sys.exit(f"rows hash {digest} differs from the plan {source['rows_sha256']}")
    rows = json.loads(rows_path.read_text(encoding="utf-8"))["rows"]
    texts_dir = e33_dir / "output" / ".local_ocr_text"
    pages = []
    for row in rows:
        path = texts_dir / row["doc_id"] / f"p{row['page']:03d}.md"
        if not path.is_file():
            sys.exit(f"saved text missing: {path}")
        pages.append({"row": row, "text": path.read_text(encoding="utf-8")})
    counts = source["counts"]
    found = {
        "rows": len(rows),
        "texts": len(pages),
        "gated_needs_ocr": sum(r["body_label"] == "needs_ocr" for r in rows),
        "io06": sum(r["body_label"] == "needs_ocr" and r["doc_id"] == "io06" for r in rows),
    }
    for key, value in found.items():
        if value != counts[key]:
            sys.exit(f"count {key}: found {value}, plan says {counts[key]}")
    if any(r["body_label"] == "needs_ocr" and r["body_recall"] is None for r in rows):
        sys.exit("a gated row has no body_recall")
    return pages


def page_record(page: dict) -> dict:
    """Build the rules.json record for one page: numbers only, no text."""
    row, text = page["row"], page["text"]
    return {
        "doc_id": row["doc_id"],
        "page": row["page"],
        "population": "gated" if row["body_label"] == "needs_ocr" else "figure_only",
        "body_recall": row["body_recall"],
        "confidence": row["confidence"],
        "hosted_recommended": row["hosted_recommended"],
        "escalate": decisions(row, text),
        "signals": {
            "cjk_share": round(cjk_share(text), 6),
            "discarded_regions": discarded_regions(row["warnings"]),
            "chars": row["chars"],
        },
    }


def write_atomic(path: Path, payload: dict) -> None:
    """Write JSON to ``<path>.tmp`` then rename, so a stop never leaves half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def main() -> None:
    """Check the data, score every rule on every page, write ``output/rules.json``."""
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--e33-dir", type=Path, default=E33_DEFAULT)
    args = parser.parse_args()
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    verdict = run_freeze_check(args.e33_dir)
    print(verdict, flush=True)
    pages = load_pages(args.e33_dir, plan)
    records = [page_record(p) for p in pages]
    write_atomic(
        RULES_OUT,
        {
            "experiment_id": plan["experiment_id"],
            "rows_sha256": plan["source_data"]["rows_sha256"],
            "freeze": verdict,
            "rules": list(records[0]["escalate"]),
            "pages": records,
        },
    )
    print(f"scored {len(records)} pages -> {RULES_OUT}", flush=True)


if __name__ == "__main__":
    main()
