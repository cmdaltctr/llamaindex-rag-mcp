"""Experiment 37 summary: output/summary.json and output/pages.json.

    uv run python experiments/37-.../summarise.py

Reads only frozen or finished files: maths_labels.json, output/detection.json,
output/ocr_state_<engine>.json, output/katex_<engine>.json,
output/recall_<engine>.json, output/noise_screen.json, noise_verdicts.json.
Writes both outputs atomically. Every number in report.md comes from here.
"""

from __future__ import annotations

import hashlib
import json
import statistics
import sys
from pathlib import Path
from typing import Any

EXP_DIR = Path(__file__).resolve().parent
OUT = EXP_DIR / "output"
ENGINES = ("dots-mocr", "paddleocr-vl")
RUNS = ("E-maths", "E-scan", "E-script")
G2_LIMIT = 0.05


def load(path: Path) -> Any:
    """Read one JSON file."""
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    """Return the hex SHA-256 of *path*."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_atomic(path: Path, data: Any) -> None:
    """Write JSON through a ``.tmp`` file and a rename."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def detection(
    labels: dict[str, Any], det: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Score D-pos and D-neg against the operator labels; return summary and page rows."""
    rows, summary = [], {}
    for run in ("D-pos", "D-neg"):
        tp = fp = fn = tn = 0
        per_doc, unmatched = {}, []
        for doc_id, doc in det["runs"][run]["documents"].items():
            d_tp = d_fp = d_fn = 0
            for p in doc["pages"]:
                label = labels[doc_id][str(p["page"])]["label"]
                maths, flagged = label == "maths", p["flagged"]
                tp += flagged and maths
                fp += flagged and not maths
                fn += maths and not flagged
                tn += not maths and not flagged
                d_tp += flagged and maths
                d_fp += flagged and not maths
                d_fn += maths and not flagged
                if maths and not flagged:
                    unmatched.append({"page": f"{doc_id}:{p['page']}", "fonts": p["other_fonts"]})
                rows.append(
                    {
                        "set": run,
                        "page": f"{doc_id}:{p['page']}",
                        "label": label,
                        "flagged": flagged,
                        "maths_fonts": p["maths_fonts"],
                    }
                )
            per_doc[doc_id] = {
                "pages": doc["page_count"],
                "flagged": doc["flagged_count"],
                "flagged_share": doc["flagged_share"],
                "maths_condition": doc["maths_condition"],
                "tp": d_tp,
                "fp": d_fp,
                "fn": d_fn,
            }
        summary[run] = {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "tn": tn,
            "precision": round(tp / (tp + fp), 4) if tp + fp else None,
            "recall": round(tp / (tp + fn), 4) if tp + fn else None,
            "per_document": per_doc,
            "maths_pages_missed": unmatched,
        }
    return summary, rows


def engine_runs(engine: str) -> dict[str, Any]:
    """Return status counts, timing and memory for one engine."""
    eng = load(OUT / f"ocr_state_{engine}.json")["engines"][engine]
    out: dict[str, Any] = {"runs": {}}
    all_pages = []
    for run in RUNS:
        pages = eng["runs"][run]["pages"]
        all_pages += pages.values()
        codes: dict[str, int] = {}
        for p in pages.values():
            codes[p.get("code", "ok")] = codes.get(p.get("code", "ok"), 0) + 1
        secs = [
            p["seconds"]
            for p in pages.values()
            if p["status"] == "ok" and not p.get("includes_start")
        ]
        out["runs"][run] = {
            "pages": len(pages),
            "outcomes": codes,
            "median_s_per_ok_page": round(statistics.median(secs), 1) if secs else None,
        }
    ok = [p["seconds"] for p in all_pages if p["status"] == "ok" and not p.get("includes_start")]
    out.update(
        {
            "pages": len(all_pages),
            "ok": sum(p["status"] == "ok" for p in all_pages),
            "median_s_per_ok_page": round(statistics.median(ok), 1),
            "engine_seconds_total_h": round(sum(p["seconds"] for p in all_pages) / 3600, 2),
            "peak_footprint_gib": round(eng["peak_footprint_bytes"] / 2**30, 1),
            "worker_process_generations": eng.get("process_generations"),
            "fingerprint": eng["fingerprint"],
        }
    )
    return out


def main() -> int:
    """Build summary.json and pages.json."""
    plan = load(EXP_DIR / "plan.json")
    labels = load(EXP_DIR / "maths_labels.json")["documents"]
    det_summary, det_rows = detection(labels, load(OUT / "detection.json"))
    katex = {e: load(OUT / f"katex_{e}.json") for e in ENGINES}
    recall = {e: load(OUT / f"recall_{e}.json") for e in ENGINES}
    screen = load(OUT / "noise_screen.json")
    verdicts = load(EXP_DIR / "noise_verdicts.json")["verdicts"]
    runs = {e: engine_runs(e) for e in ENGINES}

    g1_flagged_no_maths = det_summary["D-neg"]["fp"]
    g2_rate = katex["dots-mocr"]["overall"]["error_rate"]
    expected = sum(len(v) for v in screen["review_list"].values())
    given = sum(len(v) for v in verdicts.values())
    gates = {
        "G1": {
            "rule": plan["gates"]["G1"]["rule"],
            "measured": g1_flagged_no_maths,
            "pass": g1_flagged_no_maths == 0,
        },
        "G2": {
            "rule": plan["gates"]["G2"]["rule"],
            "measured": g2_rate,
            "formulas": katex["dots-mocr"]["overall"]["formulas"],
            "errors": katex["dots-mocr"]["overall"]["errors"],
            "pass": g2_rate is not None and g2_rate <= G2_LIMIT,
        },
        "G3": {
            "rule": plan["gates"]["G3"]["rule"],
            "measured": f"{given} / {expected}",
            "pass": given == expected,
        },
    }

    noise = {
        e: {
            "verdicts": len(v),
            "noise": sorted(k for k, x in v.items() if x["verdict"] == "noise"),
            "by_source": {
                s: sum(1 for x in v.values() if x["source"] == s)
                for s in ("screen", "audit", "protocol", "paired")
            },
        }
        for e, v in verdicts.items()
    }
    summary = {
        "experiment_id": plan["experiment_id"],
        "protocol_version": plan["protocol_version"],
        "omrg_commit": plan["system_identity"]["omrg_commit"],
        "maths_detector_version": plan["system_identity"]["maths_detector_version"],
        "inputs": {
            "maths_labels_sha256": sha256(EXP_DIR / "maths_labels.json"),
            "noise_verdicts_sha256": sha256(EXP_DIR / "noise_verdicts.json"),
        },
        "gates": gates,
        "verdict": "PASS" if all(g["pass"] for g in gates.values()) else "FAIL",
        "detection": {
            k: {x: v for x, v in d.items() if x != "per_document"}
            | {"per_document": d["per_document"]}
            for k, d in det_summary.items()
        },
        "engines": runs,
        "katex": {e: {"overall": k["overall"], "by_run": k["totals"]} for e, k in katex.items()},
        "script_recall": {e: r["by_writing_system"] for e, r in recall.items()},
        "noise": noise,
        "findings": [
            {
                "id": "F1",
                "what": "dots.mocr drops rotated tables or charts",
                "example": "tl03:8",
                "evidence": (
                    "dots-mocr 45 characters (caption only); "
                    "paddleocr-vl 1,206 characters with the rotated table (DR-5)"
                ),
            },
            {
                "id": "F2",
                "what": "the maths detector misses renamed Minion Math fonts",
                "example": "bd02:3",
                "evidence": (
                    "AdvminionMathIt, AdvminionMathEx, AdvminionSymbols not on MATHS_FONT_PATTERNS"
                ),
            },
            {
                "id": "F3",
                "what": "the maths detector cannot see Word + MathType maths",
                "example": "1106.0083v2 (rejected mp02)",
                "evidence": "Symbol and MT Extra fonts (DR-2)",
            },
            {
                "id": "F4",
                "what": "PaddleOCR-VL on CPU times out at the 300 s default",
                "evidence": (
                    f"{runs['paddleocr-vl']['pages'] - runs['paddleocr-vl']['ok']} of 257 pages "
                    "without output; "
                    f"{runs['paddleocr-vl']['worker_process_generations']} worker processes "
                    "(each timeout restarts the model)"
                ),
            },
            {
                "id": "F5",
                "what": "dots.mocr peak memory above the smoke-test figure",
                "evidence": (
                    f"{runs['dots-mocr']['peak_footprint_gib']} GiB here "
                    "vs 9.5 GiB in the 2026-10-04 smoke test"
                ),
            },
        ],
        "notes": [plan.get("execution_note", "")],
    }

    pages: list[dict[str, Any]] = [{"kind": "detection", **r} for r in det_rows]
    states = {e: load(OUT / f"ocr_state_{e}.json")["engines"][e]["runs"] for e in ENGINES}
    for run in RUNS:
        for key in states["dots-mocr"][run]["pages"]:
            row: dict[str, Any] = {"kind": "ocr", "run": run, "page": key}
            for e in ENGINES:
                st = states[e][run]["pages"].get(key, {})
                k = katex[e]["pages"].get(f"{run} {key}")
                rc = recall[e]["pages"].get(key) if run == "E-script" else None
                row[e] = {
                    "status": st.get("code", st.get("status")),
                    "seconds": st.get("seconds"),
                    "formulas": k["formulas"] if k else None,
                    "katex_errors": len(k["errors"]) if k else None,
                    "recall": rc["recall"] if rc else None,
                    "noise_verdict": verdicts[e].get(key, {}).get("verdict"),
                }
            if run == "E-script":
                row["writing_system"] = recall["dots-mocr"]["pages"][key]["writing_system"]
                row["local_tier_recall"] = recall["dots-mocr"]["pages"][key]["local_tier_recall"]
            pages.append(row)

    write_atomic(OUT / "summary.json", summary)
    write_atomic(OUT / "pages.json", {"experiment_id": plan["experiment_id"], "pages": pages})
    print(
        f"verdict {summary['verdict']} · "
        + " · ".join(
            f"{g} {'PASS' if v['pass'] else 'FAIL'} ({v['measured']})" for g, v in gates.items()
        )
    )
    print(f"pages.json rows: {len(pages)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
