"""Compare local Clef-flash builds with hosted Clef-flash, page by page (amendment A3).

Speed is not taken from the scoring files: MLX serves one request at a time, so those
times include queue waiting. Fair timings are in clef_flash_speed.json (measure_speed.py).

Hosted scores (candidate H, wording W1) are the reference. Each local build is
compared on every page/tier pair both runs scored, so a partial run still gives
a fair, smaller comparison.
"""

from __future__ import annotations

import math
from pathlib import Path

from experiment_io import OUTPUT, atomic_json, read_json

HOSTED = "wording_clefflash_w1.json"
# label -> (scores file, download size in GB, runtime, bits)
VARIANTS = {
    "MLX 4-bit (I)": ("wording_clefmlx_w1.json", 6.2, "MLX", 4),
    "MLX 8-bit (K)": ("wording_clefmlx8_w1.json", 10.7, "MLX", 8),
    "GGUF Q8_0 (J)": ("wording_clefgguf_w1.json", 9.7, "llama.cpp", 8),
}
# Q4_K_M was checked on 94 pages (bd01, rf06) only; per-page scores were not saved.
GGUF_Q4_94_PAGE_CHECK = {
    "pairs": 94,
    "pearson": 0.9991,
    "mean_abs_diff": 0.0045,
    "max_abs_diff": 0.1081,
    "side_flips": 0,
    "size_gb": 6.5,
    "runtime": "llama.cpp",
    "bits": 4,
}


def key(row: dict) -> tuple[str, int, str]:
    """Identify one page/tier pair."""
    return row["doc_id"], row["page"], row["tier"]


def pearson(x: list[float], y: list[float]) -> float:
    """Pearson correlation of two equal-length lists."""
    mx, my = sum(x) / len(x), sum(y) / len(y)
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y, strict=True))
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    return sxy / math.sqrt(sxx * syy)


def compare(hosted: list[dict], local: list[dict]) -> dict:
    """Measure agreement with hosted scores over the pairs both runs scored."""
    reference = {key(r): r["score"] for r in hosted}
    pairs = [(reference[key(r)], r["score"]) for r in local if key(r) in reference]
    if len(pairs) < 2:
        raise ValueError("fewer than two shared page/tier pairs")
    h, v = [p[0] for p in pairs], [p[1] for p in pairs]
    diffs = [abs(a - b) for a, b in pairs]
    return {
        "pairs": len(pairs),
        "pearson": pearson(h, v),
        "mean_abs_diff": sum(diffs) / len(diffs),
        "max_abs_diff": max(diffs),
        "pages_over_0_10": sum(d > 0.10 for d in diffs),
        "side_flips": sum((a < 0.5) != (b < 0.5) for a, b in pairs),
    }


def common_keys(*row_lists: list[dict]) -> set[tuple[str, int, str]]:
    """Page/tier pairs present in every run, so partial runs compare like with like."""
    return set.intersection(*({key(r) for r in rows} for rows in row_lists))


WORDING_MODELS = {
    "MLX 4-bit (I)": "clefmlx",
    "MLX 8-bit (K)": "clefmlx8",
    "GGUF Q8_0 (J)": "clefgguf",
}


def by_wording() -> dict:
    """Compare each complete local build with hosted Clef-flash on every wording."""
    out: dict[str, dict] = {}
    for wording in ("w1", "w2", "w3"):
        hosted_path = OUTPUT / f"wording_clefflash_{wording}.json"
        if not hosted_path.exists():
            continue
        hosted = read_json(hosted_path)["rows"]
        for label, model in WORDING_MODELS.items():
            path = OUTPUT / f"wording_{model}_{wording}.json"
            if not path.exists():
                continue
            payload = read_json(path)
            if len(payload["completed_documents"]) == 40:
                out.setdefault(label, {})[wording.upper()] = compare(hosted, payload["rows"])
    return out


def run() -> dict:
    """Compare every available variant and save the table data."""
    hosted = read_json(OUTPUT / HOSTED)["rows"]
    loaded = {}
    for label, (name, size, runtime, bits) in VARIANTS.items():
        path = Path(OUTPUT / name)
        if path.exists():
            loaded[label] = (read_json(path)["rows"], size, runtime, bits)
    shared = common_keys(hosted, *(rows for rows, *_ in loaded.values()))
    table = {}
    for label, (rows, size, runtime, bits) in loaded.items():
        table[label] = {
            **compare(hosted, rows),
            "on_shared_pages": compare(hosted, [r for r in rows if key(r) in shared]),
            "size_gb": size,
            "runtime": runtime,
            "bits": bits,
        }
    result = {
        "reference": "hosted Clef-flash (H), wording W1",
        "shared_pages": len(shared),
        "variants": table,
        "by_wording": by_wording(),
        "gguf_q4_k_m_94_page_check": GGUF_Q4_94_PAGE_CHECK,
    }
    atomic_json(OUTPUT / "clef_flash_variants.json", result)
    return result


def _line(label: str, m: dict) -> str:
    return (
        f"{label:15s} pairs {m['pairs']:5d} corr {m['pearson']:.4f} "
        f"mean {m['mean_abs_diff']:.4f} max {m['max_abs_diff']:.3f} "
        f"over0.10 {m['pages_over_0_10']} flips {m['side_flips']}"
    )


if __name__ == "__main__":
    out = run()
    print("own pages")
    for label, m in out["variants"].items():
        print(_line(label, m))
    print(f"same {out['shared_pages']} pages for every variant")
    for label, m in out["variants"].items():
        print(_line(label, m["on_shared_pages"]))
