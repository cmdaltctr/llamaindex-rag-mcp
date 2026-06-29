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
# # Experiment 11 — LiteParse PDF Quality and Speed
# Compare pypdf vs LiteParse on retrieval quality, latency, and build timing.

# %%
import json
from pathlib import Path

try:
    _ROOT = Path(__file__).parent
except NameError:
    _ROOT = Path.cwd()

import matplotlib.pyplot as plt
import pandas as pd

DATA = _ROOT / "output" / "eval_results.summary.json"

with open(DATA) as f:
    raw = json.load(f)

# %% [markdown]
# ## Overall Metrics by Cell

# %%
rows = []
for cell_name, cell_data in raw["metrics_by_cell"].items():
    all_metrics = cell_data["all"]
    rows.append({
        "cell": cell_name,
        "n": all_metrics["n"],
        "ndcg_at_10": all_metrics["ndcg_at_10"],
        "coverage_at_20": all_metrics["coverage_at_20"],
        "hit_at_5": all_metrics["hit_at_5"],
        "hit_at_10": all_metrics["hit_at_10"],
        "mrr_at_10": all_metrics["mrr_at_10"],
        "mean_latency_ms": all_metrics["mean_latency_ms"],
        "p95_latency_ms": all_metrics["p95_latency_ms"],
    })
df = pd.DataFrame(rows)
df

# %% [markdown]
# ## nDCG@10 and Latency by Cell

# %%
fig, axes = plt.subplots(1, 2, figsize=(14, 5))
axes[0].barh(df["cell"], df["ndcg_at_10"], color="steelblue")
axes[0].set_xlabel("nDCG@10")
axes[0].set_title("Retrieval Quality by Parser/Rerank")
axes[1].barh(df["cell"], df["mean_latency_ms"], color="coral")
axes[1].set_xlabel("Mean Latency (ms)")
axes[1].set_title("Latency by Parser/Rerank")
plt.tight_layout()
plt.show()

# %% [markdown]
# ## Build Timing: pypdf vs LiteParse

# %%
bt = raw["build_timing"]
bt_rows = []
for parser_name in ("pypdf", "liteparse"):
    p = bt[parser_name]
    bt_rows.append({
        "parser": p["parser"],
        "files_total": p["files_total"],
        "files_ok": p["files_ok"],
        "files_failed": p["files_failed"],
        "chunks_written": p["chunks_written"],
        "total_seconds": p["total_seconds"],
        "parse_seconds": p["parse_seconds_total"],
        "embed_seconds": p["embed_seconds_total"],
    })
bt_df = pd.DataFrame(bt_rows)
bt_df

# %% [markdown]
# ## Per-File Chunk Count Comparison

# %%
fig, ax = plt.subplots(figsize=(12, 5))
pypdf_files = {f["file"]: f["chunks"] for f in bt["pypdf"]["per_file"] if f["status"] == "ok"}
liteparse_files = {f["file"]: f["chunks"] for f in bt["liteparse"]["per_file"] if f["status"] == "ok"}
common_files = sorted(set(pypdf_files) & set(liteparse_files))
x = range(len(common_files))
ax.bar([i - 0.2 for i in x], [pypdf_files[f] for f in common_files], width=0.4, label="pypdf", alpha=0.7)
ax.bar([i + 0.2 for i in x], [liteparse_files[f] for f in common_files], width=0.4, label="liteparse", alpha=0.7)
ax.set_xticks(x)
ax.set_xticklabels(common_files, rotation=90, fontsize=6)
ax.set_ylabel("Chunk Count")
ax.set_title("Chunk Count per File: pypdf vs LiteParse")
ax.legend()
plt.tight_layout()
plt.show()

# %% [markdown]
# ## Pass Criteria

# %%
pc = raw["pass_criteria"]
pc_rows = []
for key, val in pc.items():
    if isinstance(val, dict) and "pass" in val:
        pc_rows.append({"criterion": key, "value": val.get("value", val.get("threshold", "N/A")), "pass": val["pass"]})
pc_df = pd.DataFrame(pc_rows)
pc_df

print(f"\nVerdict: {pc.get('verdict', 'N/A')}")
print(f"Recommendation: {pc.get('recommendation', 'N/A')}")
