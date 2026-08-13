# %% [markdown]
# # Experiment 17: Reranker MPS vs ONNX CPU — Analysis
#
# Loads `output/eval_results.json` and produces latency/memory distributions.
# This script only reads saved JSON — it never runs experiment logic or
# modifies environment variables.
#
# Generate the paired notebook: `jupytext --to notebook analysis.py`

# %%
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent

# %% [markdown]
# ## Load results

# %%
results_path = SCRIPT_DIR / "output" / "eval_results.json"
if not results_path.exists():
    raise FileNotFoundError(f"Run run_eval.py first: {results_path}")

data = json.loads(results_path.read_text(encoding="utf-8"))
cells = data.get("cells", {})
gates = data.get("gates", {})
print(f"Verdict: {gates.get('overall', {}).get('verdict', 'UNKNOWN')}")

# %% [markdown]
# ## Cell comparison table

# %%
rows = []
for cell_id in ("17A", "17B", "17C"):
    cell = cells.get(cell_id, {})
    rows.append(
        {
            "cell": cell_id,
            "backend": cell.get("backend"),
            "device": cell.get("selected_device"),
            "loaded": cell.get("loaded"),
            "p50_ms": cell.get("p50_query_ms"),
            "p95_ms": cell.get("p95_query_ms"),
            "cold_start_s": cell.get("cold_start_s"),
            "peak_rss_mb": cell.get("peak_rss_mb"),
            "mps_current_mb": cell.get("mps_current_allocated_mb"),
        }
    )
df = pd.DataFrame(rows)
df

# %% [markdown]
# ## Per-repetition P50 latency

# %%
rep_rows = []
for cell_id in ("17A", "17B", "17C"):
    reps = cells.get(cell_id, {}).get("repetition_p50s", [])
    for i, p50 in enumerate(reps, 1):
        rep_rows.append({"cell": cell_id, "repetition": i, "p50_ms": p50})
rep_df = pd.DataFrame(rep_rows)
if not rep_df.empty:
    pivot = rep_df.pivot(index="repetition", columns="cell", values="p50_ms")
    pivot.plot(kind="bar", rot=0)
    plt.title("Per-repetition P50 latency by cell")
    plt.ylabel("P50 latency (ms)")
    plt.tight_layout()
    plt.savefig(SCRIPT_DIR / "output" / "p50_by_repetition.png", dpi=150)
    plt.show()
    pivot
else:
    print("No per-repetition data available")

# %% [markdown]
# ## Raw per-query latency distribution

# %%
latency_rows = []
iterations = data.get("iterations", 5) or 1
for cell_id in ("17A", "17B", "17C"):
    # Load checkpoint files for raw latencies
    checkpoint_dir = SCRIPT_DIR / "output" / "checkpoint"
    for rep in range(1, data.get("repetitions", 3) + 1):
        f = checkpoint_dir / f"{cell_id}_rep{rep}.json"
        if f.exists():
            rep_data = json.loads(f.read_text(encoding="utf-8"))
            for i, lat in enumerate(rep_data.get("per_query_latencies_ms", [])):
                latency_rows.append(
                    {
                        "cell": cell_id,
                        "repetition": rep,
                        "query_index": i % iterations,
                        "latency_ms": lat,
                    }
                )
lat_df = pd.DataFrame(latency_rows)
if not lat_df.empty:
    lat_df.boxplot(column="latency_ms", by="cell", grid=False)
    plt.title("Per-query latency distribution by cell")
    plt.suptitle("")
    plt.ylabel("Latency (ms)")
    plt.tight_layout()
    plt.savefig(SCRIPT_DIR / "output" / "latency_boxplot.png", dpi=150)
    plt.show()

# %% [markdown]
# ## Memory comparison

# %%
mem_df = df[["cell", "peak_rss_mb", "mps_current_mb"]].set_index("cell")
mem_df.plot(kind="bar", rot=0)
plt.title("Memory usage by cell")
plt.ylabel("Memory (MB)")
plt.tight_layout()
plt.savefig(SCRIPT_DIR / "output" / "memory_comparison.png", dpi=150)
plt.show()
mem_df

# %% [markdown]
# ## Gate summary

# %%
gate_rows = []
for gate_id in ("H1", "H2", "H3", "H4", "H5"):
    gate = gates.get(gate_id, {})
    gate_rows.append(
        {
            "gate": gate_id,
            "pass": gate.get("pass"),
            "criterion": gate.get("criterion"),
        }
    )
gate_df = pd.DataFrame(gate_rows)
gate_df

# %% [markdown]
# ## Score correlation (H5 diagnostic)
#
# Compares the sigmoid scores for the first query across cells.

# %%
score_rows = []
for cell_id in ("17A", "17B", "17C"):
    scores = cells.get(cell_id, {}).get("scores", [])
    if scores:
        for doc_idx, score in enumerate(scores[0]):
            score_rows.append({"cell": cell_id, "doc_idx": doc_idx, "score": score})
score_df = pd.DataFrame(score_rows)
if not score_df.empty:
    pivot = score_df.pivot(index="doc_idx", columns="cell", values="score")
    pivot.plot(kind="bar", figsize=(12, 4))
    plt.title("Sigmoid scores for query 1 (all docs)")
    plt.ylabel("Score")
    plt.tight_layout()
    plt.savefig(SCRIPT_DIR / "output" / "score_comparison_q1.png", dpi=150)
    plt.show()
