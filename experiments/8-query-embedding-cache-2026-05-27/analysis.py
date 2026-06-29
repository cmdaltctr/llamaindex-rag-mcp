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
# # Experiment 8 — Query Embedding Cache
# Evaluate LRU cache effect on warm vs cold query latency.

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
    calls = cell["calls"]
    latencies = [c["latency_ms"] for c in calls]
    cache_hits = sum(1 for c in calls if c["cache_hit"])
    rows.append({
        "cache_enabled": cell["cache_enabled"],
        "trace": cell["trace"],
        "n_calls": len(calls),
        "cache_hit_rate": cache_hits / len(calls) if calls else 0,
        "mean_latency_ms": sum(latencies) / len(latencies) if latencies else 0,
        "p95_latency_ms": sorted(latencies)[int(len(latencies) * 0.95) - 1] if latencies else 0,
    })
df = pd.DataFrame(rows)
df

# %% [markdown]
# ## Latency Distribution: Cache On vs Off

# %%
fig, ax = plt.subplots(figsize=(8, 5))
for cell in raw["cells"]:
    latencies = [c["latency_ms"] for c in cell["calls"]]
    label = f"cache={'on' if cell['cache_enabled'] else 'off'}/{cell['trace']}"
    ax.hist(latencies, bins=15, alpha=0.5, label=label)
ax.set_xlabel("Latency (ms)")
ax.set_ylabel("Count")
ax.set_title("Latency Distribution by Cache Config")
ax.legend(fontsize=8)
plt.tight_layout()
plt.show()

# %% [markdown]
# ## Per-Call Latency Timeline

# %%
fig, axes = plt.subplots(len(raw["cells"]), 1, figsize=(12, 3 * len(raw["cells"])), sharex=True)
if len(raw["cells"]) == 1:
    axes = [axes]
for ax, cell in zip(axes, raw["cells"]):
    calls = cell["calls"]
    latencies = [c["latency_ms"] for c in calls]
    cache_hits = [c["cache_hit"] for c in calls]
    ax.plot(range(len(latencies)), latencies, marker=".", markersize=3, linewidth=0.5)
    for i, hit in enumerate(cache_hits):
        if hit:
            ax.axvline(i, color="green", alpha=0.1)
    ax.set_ylabel(f"cache={'on' if cell['cache_enabled'] else 'off'}/{cell['trace']}", fontsize=8)
    ax.grid(True, alpha=0.3)
axes[-1].set_xlabel("Call Index")
fig.suptitle("Per-Call Latency Timeline (green = cache hit)", y=1.0)
plt.tight_layout()
plt.show()
