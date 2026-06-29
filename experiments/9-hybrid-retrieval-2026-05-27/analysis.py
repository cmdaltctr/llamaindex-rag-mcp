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
# # Experiment 9 — Hybrid Retrieval (Dense + BM25 + RRF)
# Evaluate hybrid retrieval quality vs dense-only on a small corpus.

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
# ## Summary by Cell

# %%
rows = []
for cell in raw["cells"]:
    queries = cell["queries"]
    latencies = [q["latency_ms"] for q in queries]
    hit1 = sum(1 for q in queries if q["hit_at_1"]) / len(queries)
    hit5 = sum(1 for q in queries if q["hit_at_5"]) / len(queries)
    answer_hits = sum(1 for q in queries if q["answer_hit"])
    rows.append({
        "mode": cell["mode"],
        "rerank": cell["rerank"],
        "n_queries": len(queries),
        "hit_at_1": hit1,
        "hit_at_5": hit5,
        "answer_hit_rate": answer_hits / len(queries),
        "mean_latency_ms": sum(latencies) / len(latencies),
    })
df = pd.DataFrame(rows)
df

# %% [markdown]
# ## Hit@1 and Latency by Mode

# %%
fig, axes = plt.subplots(1, 2, figsize=(14, 5))
labels = [f"{r['mode']}/rerank={'on' if bool(r['rerank']) else 'off'}" for _, r in df.iterrows()]
axes[0].bar(labels, df["hit_at_1"], color=["steelblue", "coral", "seagreen", "purple"][: len(df)])
axes[0].set_title("Hit@1 by Mode")
axes[0].set_ylim(0, 1.1)
axes[0].tick_params(axis="x", rotation=30)
axes[1].bar(labels, df["mean_latency_ms"], color=["steelblue", "coral", "seagreen", "purple"][: len(df)])
axes[1].set_title("Mean Latency by Mode")
axes[1].tick_params(axis="x", rotation=30)
plt.tight_layout()
plt.show()

# %% [markdown]
# ## Per-Query: Dense vs Fused Rank

# %%
fig, ax = plt.subplots(figsize=(10, 5))
for cell in raw["cells"]:
    ranks = [q.get("fusion_ranks", {}).get("fused_rank") or q.get("hit_rank", 0) for q in cell["queries"]]
    label = f"{cell['mode']}/rerank={'on' if cell['rerank'] else 'off'}"
    ax.plot(range(len(ranks)), ranks, marker=".", markersize=4, label=label, alpha=0.7)
ax.set_xlabel("Query Index")
ax.set_ylabel("Hit Rank (lower = better)")
ax.set_title("Per-Query Hit Rank by Mode")
ax.legend(fontsize=8)
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.show()
