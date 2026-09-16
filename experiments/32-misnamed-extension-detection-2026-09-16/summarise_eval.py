"""Evaluate the Experiment 32 pass gates from the saved detections.

Reads ``output/<set>.json`` and ``output/swap_manifest.json``,
evaluates gates G1-G5 from ``protocol.md``, and writes
``output/summary.json`` with a verdict line.
"""

from __future__ import annotations

import json
from pathlib import Path

EXP = Path(__file__).resolve().parent
OUT = EXP / "output"


def load(name: str) -> dict:
    return json.loads((OUT / f"{name}.json").read_text(encoding="utf-8"))


def files_of(result: dict) -> dict[str, dict]:
    return {
        record["path"]: record for group in result["payload"]["groups"] for record in group["files"]
    }


def main() -> None:
    baseline_pdf = load("baseline_pdf")
    baseline_text = load("baseline_text")
    swap_pdf = load("swap_pdf_names")
    swap_text = load("swap_text_to_pdf")
    manifest = json.loads((OUT / "swap_manifest.json").read_text(encoding="utf-8"))

    gates: dict[str, dict] = {}

    gates["G1_baseline_pdf_all_match"] = {
        "exit": baseline_pdf["exit_code"],
        "passed": baseline_pdf["exit_code"] == 0
        and baseline_pdf["payload"]["total_files"] == 19
        and baseline_pdf["payload"]["would_change_count"] == 0,
    }
    gates["G2_baseline_text_all_match"] = {
        "exit": baseline_text["exit_code"],
        "passed": baseline_text["exit_code"] == 0
        and baseline_text["payload"]["total_files"] == 11
        and baseline_text["payload"]["would_change_count"] == 0,
    }

    pdf_files = files_of(swap_pdf)
    wrong_pdf = [
        path for path, record in pdf_files.items() if record["magika_label"] != "document/pdf"
    ]
    gates["G3_renamed_pdfs_stay_document_pdf"] = {
        "exit": swap_pdf["exit_code"],
        "total": len(pdf_files),
        "wrong_labels": wrong_pdf,
        "passed": swap_pdf["exit_code"] == 1 and len(pdf_files) == 19 and not wrong_pdf,
    }

    expected = {
        record["copy"].rsplit("/", 1)[-1]: record["expected_magika_label"]
        for record in manifest["swap_text_to_pdf"]
    }
    text_files = files_of(swap_text)
    wrong_text = [
        path for path, record in text_files.items() if record["magika_label"] != expected.get(path)
    ]
    gates["G4_renamed_text_keeps_content_label"] = {
        "exit": swap_text["exit_code"],
        "total": len(text_files),
        "wrong_labels": {path: text_files[path]["magika_label"] for path in wrong_text},
        "passed": swap_text["exit_code"] == 1 and len(text_files) == 11 and not wrong_text,
    }

    gates["G5_no_detector_failure"] = {
        "exits": {
            name: load(name)["exit_code"]
            for name in ("baseline_pdf", "baseline_text", "swap_pdf_names", "swap_text_to_pdf")
        },
        "passed": all(
            gates[g]["exit"] != 2
            for g in (
                "G1_baseline_pdf_all_match",
                "G2_baseline_text_all_match",
                "G3_renamed_pdfs_stay_document_pdf",
                "G4_renamed_text_keeps_content_label",
            )
        ),
    }

    verdict = "PASS" if all(gate["passed"] for gate in gates.values()) else "FAIL"
    summary = {
        "verdict": verdict,
        "gates": gates,
        "elapsed_seconds": {
            name: load(name)["elapsed_seconds"]
            for name in ("baseline_pdf", "baseline_text", "swap_pdf_names", "swap_text_to_pdf")
        },
    }
    target = OUT / "summary.json"
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    tmp.replace(target)
    print(f"verdict: {verdict}", flush=True)
    for name, gate in gates.items():
        print(f"{name}: {'PASS' if gate['passed'] else 'FAIL'}", flush=True)


if __name__ == "__main__":
    main()
