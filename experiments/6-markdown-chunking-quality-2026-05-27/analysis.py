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
# # Experiment 6 — Markdown-Aware Chunking Quality
# Compare baseline vs candidate markdown chunking on retrieval quality.

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
# ## Summary: Baseline vs Candidate

# %%
rows = []
for arm_name in ("baseline", "candidate"):
    arm = raw[arm_name]
    queries = arm["queries"]
    latencies = [q["latency_ms"] for q in queries]
    rows.append({
        "arm": arm_name,
        "label": arm["label"],
        "hit_at_1": sum(q["hit_at_1"] for q in queries) / len(queries),
        "hit_at_3": sum(q["hit_at_3"] for q in queries) / len(queries),
        "hit_at_5": sum(q["hit_at_5"] for q in queries) / len(queries),
        "section_match": sum(q["section_match"] for q in queries) / len(queries),
        "mean_latency_ms": sum(latencies) / len(latencies),
    })
df = pd.DataFrame(rows)
df

# %% [markdown]
# ## Per-Query Hit Comparison

# %%
fig, axes = plt.subplots(1, 2, figsize=(14, 5))
for ax, metric in zip(axes, ["hit_at_1", "hit_at_5"]):
    labels = [q["query"][:30] for q in raw["baseline"]["queries"]]
    x = range(len(labels))
    ax.bar([i - 0.2 for i in x], [q[metric] for q in raw["baseline"]["queries"]], width=0.4, label="baseline", alpha=0.7)
    ax.bar([i + 0.2 for i in x], [q[metric] for q in raw["candidate"]["queries"]], width=0.4, label="candidate", alpha=0.7)
    ax.set_title(metric)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=90, fontsize=6)
    ax.legend()
plt.tight_layout()
plt.show()

# %% [markdown]
# ## Latency Distribution

# %%
fig, ax = plt.subplots(figsize=(8, 5))
for arm_name in ("baseline", "candidate"):
    latencies = [q["latency_ms"] for q in raw[arm_name]["queries"]]
    ax.hist(latencies, bins=15, alpha=0.6, label=arm_name)
ax.set_xlabel("Latency (ms)")
ax.set_ylabel("Count")
ax.set_title("Latency Distribution: Baseline vs Candidate")
ax.legend()
plt.tight_layout()
plt.show()
