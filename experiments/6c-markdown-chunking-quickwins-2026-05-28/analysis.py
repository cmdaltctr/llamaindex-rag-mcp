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
# # Experiment 6c — Markdown Chunking Quick Wins
# Compare baseline vs candidate across multiple pass/top_k configurations.

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

results = {}
for f in sorted(DATA_DIR.glob("eval_results.*.json")):
    with open(f) as fh:
        results[f.stem] = json.load(fh)

# %% [markdown]
# ## Summary Across Configs

# %%
rows = []
for name, raw in results.items():
    for arm_name in ("baseline", "candidate"):
        if arm_name not in raw:
            continue
        arm = raw[arm_name]
        queries = arm["queries"]
        ndcg_5 = [q.get("ndcg_5", 0) for q in queries]
        ndcg_10 = [q.get("ndcg_10", 0) for q in queries]
        latencies = [q["latency_ms"] for q in queries]
        rows.append({
            "config": name,
            "arm": arm_name,
            "pass": raw.get("pass_name", "?"),
            "top_k": raw.get("top_k", "?"),
            "reranker": raw.get("reranker_enabled", "?"),
            "mean_ndcg_5": sum(ndcg_5) / len(ndcg_5) if ndcg_5 else 0,
            "mean_ndcg_10": sum(ndcg_10) / len(ndcg_10) if ndcg_10 else 0,
            "mean_latency_ms": sum(latencies) / len(latencies) if latencies else 0,
        })
df = pd.DataFrame(rows)
df

# %% [markdown]
# ## nDCG@10 by Config

# %%
pivot = df[df["arm"] == "candidate"].pivot_table(values="mean_ndcg_10", index="config", aggfunc="first")
fig, ax = plt.subplots(figsize=(12, 5))
pivot.plot(kind="bar", ax=ax, color="steelblue")
ax.set_ylabel("Mean nDCG@10")
ax.set_title("Candidate nDCG@10 by Configuration")
ax.tick_params(axis="x", rotation=45)
plt.tight_layout()
plt.show()

# %% [markdown]
# ## Baseline vs Candidate nDCG@10

# %%
fig, ax = plt.subplots(figsize=(12, 5))
configs = df["config"].unique()
baseline_vals = df[(df["arm"] == "baseline")].set_index("config")["mean_ndcg_10"].reindex(configs)
candidate_vals = df[(df["arm"] == "candidate")].set_index("config")["mean_ndcg_10"].reindex(configs)
x = range(len(configs))
ax.bar([i - 0.2 for i in x], baseline_vals, width=0.4, label="baseline", alpha=0.7)
ax.bar([i + 0.2 for i in x], candidate_vals, width=0.4, label="candidate", alpha=0.7)
ax.set_xticks(x)
ax.set_xticklabels(configs, rotation=45, fontsize=7)
ax.set_ylabel("Mean nDCG@10")
ax.set_title("Baseline vs Candidate nDCG@10")
ax.legend()
plt.tight_layout()
plt.show()
