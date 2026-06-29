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
# # Experiment 1 — Reranker Threshold Calibration
# Analysis of reranker threshold configurations and their impact on accuracy vs latency.

# %%
import json
from pathlib import Path

try:
    _ROOT = Path(__file__).parent
except NameError:
    _ROOT = Path.cwd()

import matplotlib.pyplot as plt
import pandas as pd

DATA = _ROOT / "experiment_results.json"

with open(DATA) as f:
    raw = json.load(f)

# %% [markdown]
# ## Summary Table

# %%
summaries = raw["summaries"]
df = pd.DataFrame(summaries)
df

# %% [markdown]
# ## Accuracy vs Latency

# %%
fig, ax = plt.subplots(figsize=(8, 5))
ax.scatter(df["avg_latency_ms"], df["source_accuracy"], s=80, label="Source Accuracy")
ax.scatter(df["avg_latency_ms"], df["answer_accuracy"], s=80, marker="^", label="Answer Accuracy")
for _, row in df.iterrows():
    ax.annotate(str(row["label"]), (row["avg_latency_ms"], row["source_accuracy"]), fontsize=8, xytext=(5, 5), textcoords="offset points")
ax.set_xlabel("Avg Latency (ms)")
ax.set_ylabel("Accuracy")
ax.set_title("Accuracy vs Latency by Configuration")
ax.legend()
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.show()

# %% [markdown]
# ## Per-Query Score Distribution

# %%
detailed = raw["detailed_results"]
all_rows = []
for config_label, queries in detailed.items():
    for q in queries:
        all_rows.append({
            "config": config_label,
            "query": q["query"][:40],
            "source_correct": q["source_correct"],
            "answer_correct": q["answer_correct"],
            "latency_ms": q["latency_ms"],
            "top_score": q["top_score"],
        })
detail_df = pd.DataFrame(all_rows)
detail_df.head(20)

# %%
fig, ax = plt.subplots(figsize=(10, 5))
for config in detail_df["config"].unique():
    subset = detail_df[detail_df["config"] == config]
    ax.plot(range(len(subset)), subset["latency_ms"], marker="o", label=config, alpha=0.7)
ax.set_xlabel("Query Index")
ax.set_ylabel("Latency (ms)")
ax.set_title("Per-Query Latency by Configuration")
ax.legend(fontsize=8)
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.show()
