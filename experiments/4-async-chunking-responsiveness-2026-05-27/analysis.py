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
# # Experiment 4 — Async Chunking Responsiveness
# Analyse search latency under idle and load conditions during ingestion.

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

traces = {}
for f in sorted(DATA_DIR.glob("*.json")):
    with open(f) as fh:
        traces[f.stem] = json.load(fh)

# %% [markdown]
# ## Latency Summary by Mode

# %%
rows = []
for name, trace in traces.items():
    queries = trace.get("queries", [])
    latencies = [q["latency_ms"] for q in queries]
    rows.append({
        "trace": name,
        "mode": trace.get("mode", name),
        "n_queries": len(latencies),
        "mean_ms": sum(latencies) / len(latencies) if latencies else 0,
        "max_ms": max(latencies) if latencies else 0,
        "p95_ms": sorted(latencies)[int(len(latencies) * 0.95) - 1] if latencies else 0,
    })
df = pd.DataFrame(rows)
df

# %% [markdown]
# ## Latency Timeline per Trace

# %%
fig, axes = plt.subplots(len(traces), 1, figsize=(12, 3 * len(traces)), sharex=True)
if len(traces) == 1:
    axes = [axes]
for ax, (name, trace) in zip(axes, traces.items()):
    queries = trace.get("queries", [])
    latencies = [q["latency_ms"] for q in queries]
    ax.plot(range(len(latencies)), latencies, marker=".", markersize=3, linewidth=0.5)
    ax.set_ylabel(name, fontsize=8)
    ax.grid(True, alpha=0.3)
axes[-1].set_xlabel("Query Index")
fig.suptitle("Per-Query Latency Timeline", y=1.0)
plt.tight_layout()
plt.show()

# %% [markdown]
# ## Latency Distribution Comparison

# %%
fig, ax = plt.subplots(figsize=(10, 5))
for name, trace in traces.items():
    latencies = [q["latency_ms"] for q in trace.get("queries", [])]
    ax.hist(latencies, bins=20, alpha=0.5, label=name)
ax.set_xlabel("Latency (ms)")
ax.set_ylabel("Count")
ax.set_title("Latency Distribution by Trace")
ax.legend(fontsize=8)
plt.tight_layout()
plt.show()
