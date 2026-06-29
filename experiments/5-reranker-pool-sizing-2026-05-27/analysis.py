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
# # Experiment 5 — Reranker Pool Sizing
# Evaluate retrieval quality and latency across reranker pool configurations.

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
# ## Summary by Config

# %%
rows = []
for cfg in raw["configs"]:
    queries = cfg["queries"]
    latencies = [q["latency_ms"] for q in queries]
    source_hits = sum(1 for q in queries if q["source_hit"])
    answer_hits = sum(1 for q in queries if q["answer_hit"])
    rows.append({
        "label": cfg["label"],
        "max_fetch": cfg["max_fetch"],
        "multiplier": cfg["multiplier"],
        "fetch_k_eff": cfg["fetch_k_effective"],
        "source_hit_rate": source_hits / len(queries) if queries else 0,
        "answer_hit_rate": answer_hits / len(queries) if queries else 0,
        "mean_latency_ms": sum(latencies) / len(latencies) if latencies else 0,
        "p95_latency_ms": sorted(latencies)[int(len(latencies) * 0.95) - 1] if latencies else 0,
    })
df = pd.DataFrame(rows)
df

# %% [markdown]
# ## Latency vs Pool Size

# %%
fig, ax = plt.subplots(figsize=(8, 5))
ax.plot(df["fetch_k_eff"], df["mean_latency_ms"], marker="o", label="Mean Latency")
ax.plot(df["fetch_k_eff"], df["p95_latency_ms"], marker="^", label="P95 Latency")
ax.set_xlabel("Effective fetch_k")
ax.set_ylabel("Latency (ms)")
ax.set_title("Latency vs Effective Pool Size")
ax.legend()
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.show()

# %% [markdown]
# ## Hit Rate vs Pool Size

# %%
fig, ax = plt.subplots(figsize=(8, 5))
ax.plot(df["fetch_k_eff"], df["source_hit_rate"], marker="o", label="Source Hit Rate")
ax.plot(df["fetch_k_eff"], df["answer_hit_rate"], marker="^", label="Answer Hit Rate")
ax.set_xlabel("Effective fetch_k")
ax.set_ylabel("Hit Rate")
ax.set_title("Hit Rate vs Effective Pool Size")
ax.set_ylim(0, 1.1)
ax.legend()
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.show()
