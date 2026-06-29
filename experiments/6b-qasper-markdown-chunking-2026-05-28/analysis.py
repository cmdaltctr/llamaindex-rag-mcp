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
# # Experiment 6b — Qasper Markdown Chunking (Evidence Level)
# Evaluate markdown chunking quality on the Qasper dataset.

# %%
import json
from pathlib import Path

try:
    _ROOT = Path(__file__).parent
except NameError:
    _ROOT = Path.cwd()

import matplotlib.pyplot as plt
import pandas as pd

DATA = _ROOT / "eval_results.json"

with open(DATA) as f:
    raw = json.load(f)

# %% [markdown]
# ## Summary: Baseline vs Candidate

# %%
rows = []
for arm_name in ("baseline", "candidate"):
    arm = raw[arm_name]
    queries = arm["queries"]
    latencies = [q["latency_ms"] for q in queries]
    ndcg_scores = [q.get("ndcg_5", 0) for q in queries]
    rows.append({
        "arm": arm_name,
        "label": arm["label"],
        "n_queries": len(queries),
        "mean_ndcg_5": sum(ndcg_scores) / len(ndcg_scores),
        "section_match_at_1": sum(q["section_match_at_1"] for q in queries) / len(queries),
        "mean_latency_ms": sum(latencies) / len(latencies),
    })
df = pd.DataFrame(rows)
df

# %% [markdown]
# ## nDCG Distribution

# %%
fig, ax = plt.subplots(figsize=(8, 5))
for arm_name in ("baseline", "candidate"):
    ndcg = [q.get("ndcg_5", 0) for q in raw[arm_name]["queries"]]
    ax.hist(ndcg, bins=20, alpha=0.6, label=arm_name)
ax.set_xlabel("nDCG@5")
ax.set_ylabel("Count")
ax.set_title("nDCG@5 Distribution: Baseline vs Candidate")
ax.legend()
plt.tight_layout()
plt.show()

# %% [markdown]
# ## Latency by Category

# %%
all_rows = []
for arm_name in ("baseline", "candidate"):
    for q in raw[arm_name]["queries"]:
        all_rows.append({"arm": arm_name, "category": q.get("category", "unknown"), "latency_ms": q["latency_ms"]})
cat_df = pd.DataFrame(all_rows)
pivot = cat_df.pivot_table(values="latency_ms", index="category", columns="arm", aggfunc="mean")
pivot
