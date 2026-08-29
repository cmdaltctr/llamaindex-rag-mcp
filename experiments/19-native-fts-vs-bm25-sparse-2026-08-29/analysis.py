# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.16.0
# ---

# %% [markdown]
# # Experiment 19: native FTS vs BM25 sparse backend
#
# Loads the cell JSON outputs and the summary; reproduces the tables
# in results.md and plots the per-query latency distributions.
# Read-only over the raw data — no experiment logic, no env mutation.

# %%
import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

EXP = Path(__file__).resolve().parent
cells = {
    name: json.loads((EXP / "output/cells" / f"{name}.json").read_text())
    for name in ("bm25", "native")
}
summary = json.loads((EXP / "output/eval_results.summary.json").read_text())

# %%
# Quality comparison (sparse-only, warm pass).
rows = []
for name, cell in cells.items():
    warm = cell["sparse"]["warm"]["rows"]
    for row in warm:
        hit5 = any(
            Path(s or "").name == row["expected_source"]
            or row["expected_source"] in Path(s or "").name
            for s in row["sources"][:5]
        )
        hit10 = any(
            Path(s or "").name == row["expected_source"]
            or row["expected_source"] in Path(s or "").name
            for s in row["sources"][:10]
        )
        rows.append(
            {
                "backend": name,
                "category": row["category"],
                "hit@5": hit5,
                "hit@10": hit10,
            }
        )
frame = pd.DataFrame(rows)
quality = frame.groupby(["backend", "category"])[["hit@5", "hit@10"]].mean().round(3)
quality

# %%
# Latency distributions (warm pass, log scale).
fig, ax = plt.subplots(figsize=(7, 4))
for name, cell in cells.items():
    timings_ms = [t * 1000 for t in cell["sparse"]["warm"]["timings_s"]]
    ax.hist(timings_ms, bins=20, alpha=0.6, label=name)
ax.set_xlabel("warm sparse query latency (ms)")
ax.set_ylabel("queries")
ax.set_yscale("log")
ax.set_title("Experiment 19: warm sparse-query latency by backend")
ax.legend()
plt.show()

# %%
# Gate comparison table.
pd.DataFrame([summary["comparison"], summary["gates"]]).T
