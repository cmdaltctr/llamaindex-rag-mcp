"""Time 40 fixed pages, one request at a time, against the server on 127.0.0.1:3000.

Usage: python measure_speed.py "<label>". Run it once per server; the server must be the
only job using the GPU. Two warm-up requests are not counted.
"""

import json
import statistics as st
import sys
import time
import urllib.request as u

sys.path.insert(0, ".")
from experiment_io import OUTPUT, approved_plan, read_json
from jev_hosted import HEAD_CHARACTERS


def main() -> None:
    """Time the fixed sample against the local server."""
    label = sys.argv[1]
    q = approved_plan()["wordings"]["W1"]["question"]
    rows = read_json(OUTPUT / "wording_clefflash_w1.json")["rows"]
    # a fixed, spread-out sample: every 16th liteparse pair
    sample = [r for r in rows if r["tier"] == "liteparse"][::16][:40]
    texts = {}
    for r in sample:
        doc = r["doc_id"]
        if doc not in texts:
            texts[doc] = read_json(OUTPUT / ".rescue_text" / doc / "liteparse.json")

    def one(text):
        b = json.dumps(
            {
                "model": "clef-flash",
                "state": text[:HEAD_CHARACTERS],
                "questions": {"readable": {"type": "noul", "instructions": q}},
            }
        ).encode()
        t = time.perf_counter()
        u.urlopen(
            u.Request(
                "http://127.0.0.1:3000/v1/systemone", b, {"Content-Type": "application/json"}
            ),
            timeout=300,
        ).read()
        return time.perf_counter() - t

    pages = [texts[r["doc_id"]][r["page"] - 1] for r in sample]
    one(pages[0])
    one(pages[1])  # warm-up, not counted
    t = [one(p) for p in pages]
    p95 = sorted(t)[int(len(t) * 0.95) - 1]
    print(
        f"{label}: {len(t)} pages one at a time | mean {st.mean(t):.3f} s | "
        f"median {st.median(t):.3f} s | p95 {p95:.3f} s"
    )
    print(
        json.dumps(
            {
                "label": label,
                "n": len(t),
                "mean_s": round(st.mean(t), 3),
                "median_s": round(st.median(t), 3),
                "p95_s": round(sorted(t)[int(len(t) * 0.95) - 1], 3),
            }
        )
    )


if __name__ == "__main__":
    main()
