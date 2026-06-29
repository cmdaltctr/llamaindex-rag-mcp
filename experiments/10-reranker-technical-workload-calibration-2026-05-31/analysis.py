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
# # Experiment 10 — Reranker Technical Workload Calibration
# Evaluate reranker pool sizing on a technical workload (FreshStack LangChain).

# %%
import json
from pathlib import Path

try:
    _ROOT = Path(__file__).parent
except NameError:
    _ROOT = Path.cwd()

import matplotlib.pyplot as plt
import pandas as pd

DATA = _ROOT / "output" / "eval_results.summary.json"

with open(DATA) as f:
    raw = json.load(f)

# %% [markdown]
# ## Overall Metrics by Cell

# %%
rows = []
for cell_name, cell_data in raw["metrics_by_cell"].items():
    all_metrics = cell_data["all"]
    rows.append({
        "cell": cell_name,
        "n": all_metrics["n"],
        "alpha_ndcg_at_10": all_metrics["alpha_ndcg_at_10"],
        "coverage_at_20": all_metrics["coverage_at_20"],
        "hit_at_5": all_metrics["hit_at_5"],
        "hit_at_10": all_metrics["hit_at_10"],
        "mrr_at_10": all_metrics["mrr_at_10"],
        "mean_latency_ms": all_metrics["mean_latency_ms"],
        "p95_latency_ms": all_metrics["p95_latency_ms"],
    })
df = pd.DataFrame(rows)
df

# %% [markdown]
# ## Alpha-nDCG@10 and Latency by Cell

# %%
fig, axes = plt.subplots(1, 2, figsize=(14, 5))
axes[0].barh(df["cell"], df["alpha_ndcg_at_10"], color="steelblue")
axes[0].set_xlabel("Alpha-nDCG@10")
axes[0].set_title("Retrieval Quality by Cell")
axes[1].barh(df["cell"], df["mean_latency_ms"], color="coral")
axes[1].set_xlabel("Mean Latency (ms)")
axes[1].set_title("Latency by Cell")
plt.tight_layout()
plt.show()

# %% [markdown]
# ## Quality vs Latency Trade-off

# %%
fig, ax = plt.subplots(figsize=(8, 5))
ax.scatter(df["mean_latency_ms"], df["alpha_ndcg_at_10"], s=80)
for _, row in df.iterrows():
    ax.annotate(str(row["cell"]), (row["mean_latency_ms"], row["alpha_ndcg_at_10"]), fontsize=7, xytext=(5, 5), textcoords="offset points")
ax.set_xlabel("Mean Latency (ms)")
ax.set_ylabel("Alpha-nDCG@10")
ax.set_title("Quality vs Latency Trade-off")
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.show()

# %% [markdown]
# ## Pass Criteria

# %%
pc = raw["pass_criteria"]
pc_rows = []
for key, val in pc.items():
    if isinstance(val, dict) and "pass" in val:
        pc_rows.append({"criterion": key, "value": val.get("value", "N/A"), "pass": val["pass"]})
pc_df = pd.DataFrame(pc_rows)
pc_df

print(f"\nAll gates pass: {pc.get('all_gates_pass', False)}")
print(f"Recommendation: {pc.get('recommendation', 'N/A')}")
