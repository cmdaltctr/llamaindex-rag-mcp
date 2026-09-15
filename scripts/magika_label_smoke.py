#!/usr/bin/env python3
"""Label-equivalence smoke for the pinned Magika detector (fail-closed).

Compares the suffix fallback scanner against the content-based Magika
scanner over explicit operator paths. Detection only: this tool never
imports ingestion, store, embedder, or composition-root modules, so a
run can never re-ingest or mutate an index. Exit status 0 requires a
complete, non-empty all-match result.

Usage::

    python scripts/magika_label_smoke.py --json PATH [PATH ...]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Make the tool runnable with a bare interpreter next to the checkout.
_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from omrg.core.codebase.codebase_map import scan_with_suffix  # noqa: E402
from omrg.core.settings import EffectiveSettings  # noqa: E402
from omrg.integrations.magika import scan_with_magika  # noqa: E402


def _find_duplicates(paths: list[str]) -> set[str]:
    """Return paths a scanner reported more than once."""
    seen: set[str] = set()
    duplicated: set[str] = set()
    for item in paths:
        if item in seen:
            duplicated.add(item)
        seen.add(item)
    return duplicated


def run_comparison(paths: list[str], settings: Any = None) -> dict[str, Any]:
    """Compare suffix and Magika labels over explicit operator paths.

    Args:
        paths: Operator-supplied file or directory paths.
        settings: Effective settings injected into both scanners.

    Returns:
        Payload with ``groups[].files`` records (``path``,
        ``suffix_label``, ``magika_label``, ``would_change``),
        ``total_files``, and ``would_change_count``. Records are grouped
        by the suffix label's group and matched by path, never by the
        scanners' output order.

    Raises:
        ValueError: The input is empty or the two scanner path sets
            differ (missing, extra, or duplicate paths).
        Exception: Scanner failures propagate unchanged (fail-closed).
    """
    if not paths:
        raise ValueError("Magika smoke input is empty: no operator paths given")

    suffix_entries: list = []
    magika_entries: list = []
    for raw_path in paths:
        scan_path = str(raw_path)
        suffix_entries.extend(scan_with_suffix(scan_path, settings))
        magika_entries.extend(scan_with_magika(scan_path, settings))

    if not suffix_entries and not magika_entries:
        raise ValueError("Magika smoke input is empty: no files detected")

    duplicates = _find_duplicates([entry.path for entry in suffix_entries]) | _find_duplicates(
        [entry.path for entry in magika_entries]
    )
    suffix_labels = {entry.path: f"{entry.group}/{entry.label}" for entry in suffix_entries}
    magika_labels = {entry.path: f"{entry.group}/{entry.label}" for entry in magika_entries}
    missing = sorted(set(suffix_labels) - set(magika_labels))
    extra = sorted(set(magika_labels) - set(suffix_labels))
    if duplicates or missing or extra:
        raise ValueError(
            "Magika smoke path sets differ: "
            f"missing={missing} extra={extra} duplicate={sorted(duplicates)}"
        )

    records: list[dict[str, Any]] = []
    for path in sorted(suffix_labels):
        suffix_label = suffix_labels[path]
        magika_label = magika_labels[path]
        records.append(
            {
                "path": path,
                "suffix_label": suffix_label,
                "magika_label": magika_label,
                "would_change": suffix_label != magika_label,
            }
        )

    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        grouped.setdefault(record["suffix_label"].partition("/")[0], []).append(record)

    return {
        "groups": [{"group": name, "files": files} for name, files in sorted(grouped.items())],
        "total_files": len(records),
        "would_change_count": sum(1 for record in records if record["would_change"]),
    }


def _print_summary(payload: dict[str, Any]) -> None:
    """Print a human-readable comparison table."""
    for group in payload["groups"]:
        print(f"[{group['group']}]")
        for record in group["files"]:
            flag = "CHANGED" if record["would_change"] else "match"
            print(
                f"  {flag:7} {record['path']}: {record['suffix_label']} -> {record['magika_label']}"
            )
    print(
        f"total={payload['total_files']} would_change={payload['would_change_count']}",
    )


def main(argv: list[str] | None = None) -> int:
    """Run the smoke comparison and return a CLI exit status.

    Returns:
        0 for a complete, non-empty all-match result; 1 for any label
        mismatch; 2 for empty input or any scanner failure.
    """
    parser = argparse.ArgumentParser(
        description="Fail-closed Magika/suffix label-equivalence smoke (detection only)."
    )
    parser.add_argument("--json", action="store_true", help="emit the comparison payload as JSON")
    parser.add_argument("paths", nargs="+", help="explicit file or directory paths")
    args = parser.parse_args(argv)

    # Bare default settings: the tool is detection-only and must not
    # import the composition root, so resolve plain settings data here.
    # Defaults carry the scanners' scan limits and binary name.
    settings = EffectiveSettings()
    try:
        payload = run_comparison(list(args.paths), settings)
    except Exception as exc:  # noqa: BLE001 — fail-closed CLI boundary
        print(f"magika_label_smoke: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        _print_summary(payload)

    if payload["would_change_count"]:
        print(
            f"magika_label_smoke: {payload['would_change_count']} of "
            f"{payload['total_files']} labels differ from the suffix map",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
