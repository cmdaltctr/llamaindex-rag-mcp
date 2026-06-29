# ---
# jupyter:
#   jupytext:
#     cell_metadata_filter: -all
#     formats: ipynb,py:percent
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.19.4
# ---

# %% [markdown]
# # Experiment 7a — Chunk Overlap Evidence (Qasper)
# Evidence-level evaluation of chunk overlap on the Qasper dataset.

# %%
import json
from pathlib import Path

try:
    _ROOT = Path(__file__).parent
except NameError:
    _ROOT = Path.cwd()

import matplotlib.pyplot as plt
import pandas as pd

DATA_DIR = _ROOT

with open(DATA_DIR / "eval_results.summary.json") as f:
    summary = json.load(f)

with open(DATA_DIR / "eval_results.json") as f:
    raw = json.load(f)

# %% [markdown]
# ## Experiment Status & Recommendation

# %%
print(f"Status: {summary['status']}")
print(f"Recommendation: {summary['recommendation']}")
print(f"Corpus: {summary['corpus']}")

# %% [markdown]
# ## Main Production Shape (Pass B / rerank on)

# %%
mps = summary["main_production_shape"]
rows = []
for overlap_key, metrics in mps.items():
    if not overlap_key.startswith("overlap_"):
        continue
    rows.append({"overlap": overlap_key, **metrics})
prod_df = pd.DataFrame(rows)
prod_df

# %% [markdown]
# ## nDCG@5 Distribution by Overlap (from full results)

# %%
rows = []
for ev in raw["evaluations"]:
    overlap = ev["overlap"]
    top_k = ev["top_k"]
    rerank = ev["rerank"]
    for q in ev["queries"]:
        rows.append({
            "overlap": overlap,
            "top_k": top_k,
            "rerank": rerank,
            "ndcg_5": q.get("ndcg_5", 0),
            "latency_ms": q["latency_ms"],
        })
detail_df = pd.DataFrame(rows)

# Filter to production shape: top_k=5, rerank=True (pass B)
prod_detail = detail_df[(detail_df["top_k"] == 5) & (detail_df["rerank"])]
fig, ax = plt.subplots(figsize=(8, 5))
for overlap in sorted(prod_detail["overlap"].unique()):
    subset = prod_detail[prod_detail["overlap"] == overlap]
    ax.hist(subset["ndcg_5"], bins=15, alpha=0.5, label=f"overlap={overlap}")
ax.set_xlabel("nDCG@5")
ax.set_ylabel("Count")
ax.set_title("nDCG@5 Distribution by Overlap (top_k=5, rerank=on)")
ax.legend()
plt.tight_layout()
plt.show()
