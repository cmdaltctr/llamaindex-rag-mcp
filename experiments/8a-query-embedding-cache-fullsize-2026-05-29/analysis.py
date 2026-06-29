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
# # Experiment 8a — Query Embedding Cache (Full-Size)
# Full-size evaluation of cache effect with rerank on/off.

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

with open(DATA_DIR / "eval_results.json") as f:
    raw = json.load(f)

with open(DATA_DIR / "eval_results.summary.json") as f:
    summary = json.load(f)

# %% [markdown]
# ## Summary by Cell

# %%
rows = []
for cell in raw["cells"]:
    calls = cell["calls"]
    latencies = [c["latency_ms"] for c in calls]
    cache_hits = sum(1 for c in calls if c["cache_hit"])
    rows.append({
        "cache_enabled": cell["cache_enabled"],
        "trace": cell["trace"],
        "rerank": cell.get("rerank", "?"),
        "n_calls": len(calls),
        "cache_hit_rate": cache_hits / len(calls) if calls else 0,
        "mean_latency_ms": sum(latencies) / len(latencies) if latencies else 0,
        "p95_latency_ms": sorted(latencies)[int(len(latencies) * 0.95) - 1] if latencies else 0,
    })
df = pd.DataFrame(rows)
df

# %% [markdown]
# ## Cache Effect: Warm Speedup

# %%
fig, ax = plt.subplots(figsize=(10, 5))
labels = [f"cache={'on' if bool(r['cache_enabled']) else 'off'}/rerank={'on' if bool(r['rerank']) else 'off'}/{r['trace']}" for _, r in df.iterrows()]
ax.bar(range(len(df)), df["mean_latency_ms"], color=["steelblue" if bool(r["cache_enabled"]) else "coral" for _, r in df.iterrows()])
ax.set_xticks(range(len(df)))
ax.set_xticklabels(labels, rotation=45, fontsize=7, ha="right")
ax.set_ylabel("Mean Latency (ms)")
ax.set_title("Mean Latency by Cache/Rerank/Trace Config")
plt.tight_layout()
plt.show()

# %% [markdown]
# ## Latency Boxplot: Cache On vs Off

# %%
fig, ax = plt.subplots(figsize=(8, 5))
data_by_label = {}
for cell in raw["cells"]:
    label = f"cache={'on' if cell['cache_enabled'] else 'off'}/{cell['trace']}"
    data_by_label.setdefault(label, []).extend([c["latency_ms"] for c in cell["calls"]])
ax.boxplot(list(data_by_label.values()), tick_labels=list(data_by_label.keys()))
ax.set_ylabel("Latency (ms)")
ax.set_title("Latency Distribution by Cache Config")
ax.tick_params(axis="x", rotation=30)
plt.tight_layout()
plt.show()
