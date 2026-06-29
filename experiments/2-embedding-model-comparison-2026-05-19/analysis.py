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
#   kernelspec:
#     display_name: .venv
#     language: python
#     name: python3
# ---

# %% [markdown]
# # Experiment 2 — Embedding Model Comparison
# Compare retrieval quality and latency across embedding models.

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
# ## Summary Table

# %%
df = pd.DataFrame(raw["summaries"])
df

# %% [markdown]
# ## Hit Rate Comparison

# %%
fig, axes = plt.subplots(1, 3, figsize=(15, 5))
metrics = [("hit_rate_at_1", "Hit@1"), ("hit_rate_at_3", "Hit@3"), ("hit_rate_at_5", "Hit@5")]
for ax, (key, title) in zip(axes, metrics):
    ax.bar(df["label"], df[key], color=["steelblue", "coral", "seagreen"][: len(df)])
    ax.set_title(title)
    ax.set_ylim(0, 1.1)
    ax.set_ylabel("Rate")
    ax.tick_params(axis="x", rotation=30)
plt.tight_layout()
plt.show()

# %% [markdown]
# ## Latency Comparison

# %% [markdown]
#

# %%
fig, ax = plt.subplots(figsize=(8, 5))
ax.bar(df["label"], df["avg_latency_ms"], color=["steelblue", "coral", "seagreen"][: len(df)])
ax.set_ylabel("Avg Latency (ms)")
ax.set_title("Average Latency by Embedding Model")
ax.tick_params(axis="x", rotation=30)
plt.tight_layout()
plt.show()

# %% [markdown]
# ## Per-Query Latency Distribution

# %%
all_rows = []
for model_name, queries in raw["detailed_results"].items():
    for q in queries:
        all_rows.append({"model": model_name, "latency_ms": q["latency_ms"]})
lat_df = pd.DataFrame(all_rows)

fig, ax = plt.subplots(figsize=(8, 5))
for model in lat_df["model"].unique():
    subset = lat_df[lat_df["model"] == model]
    ax.hist(subset["latency_ms"], bins=15, alpha=0.6, label=model)
ax.set_xlabel("Latency (ms)")
ax.set_ylabel("Count")
ax.set_title("Latency Distribution by Model")
ax.legend()
plt.tight_layout()
plt.show()
