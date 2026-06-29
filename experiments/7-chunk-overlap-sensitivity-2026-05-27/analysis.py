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
# # Experiment 7 — Chunk Overlap Sensitivity
# Evaluate retrieval quality and latency across chunk overlap values.

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
# ## Summary by Overlap

# %%
rows = []
for ev in raw["evaluations"]:
    overlap = ev["overlap"]
    queries = ev["queries"]
    latencies = [q["latency_ms"] for q in queries]
    hit1 = sum(q["hit_at_1"] for q in queries) / len(queries)
    hit3 = sum(q["hit_at_3"] for q in queries) / len(queries)
    hit5 = sum(q["hit_at_5"] for q in queries) / len(queries)
    answer_hits = sum(1 for q in queries if q["answer_hit"])
    rows.append({
        "overlap": overlap,
        "hit_at_1": hit1,
        "hit_at_3": hit3,
        "hit_at_5": hit5,
        "answer_hit_rate": answer_hits / len(queries),
        "mean_latency_ms": sum(latencies) / len(latencies),
        "p95_latency_ms": sorted(latencies)[int(len(latencies) * 0.95) - 1] if latencies else 0,
    })
df = pd.DataFrame(rows)
df

# %% [markdown]
# ## Hit Rate vs Overlap

# %%
fig, ax = plt.subplots(figsize=(8, 5))
ax.plot(df["overlap"], df["hit_at_1"], marker="o", label="Hit@1")
ax.plot(df["overlap"], df["hit_at_3"], marker="s", label="Hit@3")
ax.plot(df["overlap"], df["hit_at_5"], marker="^", label="Hit@5")
ax.set_xlabel("Chunk Overlap")
ax.set_ylabel("Hit Rate")
ax.set_title("Hit Rate vs Chunk Overlap")
ax.legend()
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.show()

# %% [markdown]
# ## Latency vs Overlap

# %%
fig, ax = plt.subplots(figsize=(8, 5))
ax.plot(df["overlap"], df["mean_latency_ms"], marker="o", label="Mean Latency")
ax.plot(df["overlap"], df["p95_latency_ms"], marker="^", label="P95 Latency")
ax.set_xlabel("Chunk Overlap")
ax.set_ylabel("Latency (ms)")
ax.set_title("Latency vs Chunk Overlap")
ax.legend()
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.show()
