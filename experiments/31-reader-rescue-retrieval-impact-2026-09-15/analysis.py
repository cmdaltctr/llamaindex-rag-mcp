# %% [markdown]
# # Experiment 31 analysis — reader rescue retrieval impact
#
# Loads the local JSON results and produces pandas summaries and
# matplotlib figures. Analysis only: this notebook never runs experiment
# logic, mutates environment variables, or touches the indexes.
#
# Regenerate the paired notebook (gitignored) with:
#     jupytext --to notebook analysis.py

# %% tags=["load"]
from __future__ import annotations

import json
from pathlib import Path

EXP = Path(__file__).resolve().parent
import pandas as pd  # noqa: E402

summary = json.loads((EXP / "output" / "eval_results.summary.json").read_text())
extraction = pd.DataFrame(json.loads((EXP / "output" / "extraction_manifest.json").read_text()))
paired = pd.DataFrame(summary["per_query_paired_B_vs_C"])
print("cells:", list(summary["cells"]))

# %% [markdown]
# ## Primary metrics per cell
# Evidence Recall@k: fraction of queries whose gold span is matched by a
# top-k retrieved chunk. Recoverability: span present in the cell's full
# extraction (parser stage). Cell A is the sanity check — zero by design.

# %% tags=["primary"]
rows = []
for cell, m in summary["cells"].items():
    rows.append(
        {
            "cell": cell,
            "role": m["role"],
            **{k: v for k, v in m.items() if k not in ("role", "secondary")},
        }
    )
primary = pd.DataFrame(rows).set_index("cell")
primary

# %% tags=["primary-plot"]
axes = primary[
    [
        "evidence_recoverability",
        "evidence_recall@1",
        "evidence_recall@5",
        "evidence_recall@10",
        "mrr@10",
    ]
].plot.bar(title="Experiment 31: primary metrics by cell", rot=0, figsize=(10, 4))

# %% [markdown]
# ## Paired candidate (B) vs reference (C)
# Per-query differences, disagreement list, and the bootstrap CI when it
# applies (>= 20 measured queries).

# %% tags=["paired"]
if not paired.empty:
    display_cols = [
        "query_id",
        "doc_id",
        "b_recovered",
        "c_recovered",
        "b_hit",
        "c_hit",
        "b_rr",
        "c_rr",
    ]
    print(paired[display_cols].to_string(index=False))
    print("\nmean hit@10 delta (B-C):", summary["paired_B_vs_C"]["mean_hit@10_delta_B_minus_C"])
    print("mean RR delta (B-C):", summary["paired_B_vs_C"]["mean_rrr_delta_B_minus_C"])
    print("bootstrap:", summary["paired_B_vs_C"]["bootstrap"])
    print("disagreements:", summary["paired_B_vs_C"]["disagreements"])

# %% [markdown]
# ## Secondary outcomes
# Extraction latency and volume per cell (medians over held-out documents),
# chunk counts and index sizes from the runtime manifests.

# %% tags=["secondary"]
secondary = pd.DataFrame({c: summary["cells"][c]["secondary"] for c in summary["cells"]}).T
secondary

# %% tags=["extraction-detail"]
ext = extraction[extraction["split"].isin(["heldout", "distractor"])]
pivoted = ext.pivot_table(index="doc_id", columns="cell", values="characters", aggfunc="first")
pivoted.columns = [f"chars_{c}" for c in pivoted.columns]
pivoted.join(
    ext[ext["cell"] == "B"].set_index("doc_id")[["reader_seconds_median3", "fallback_tier"]]
).rename(columns={"reader_seconds_median3": "B_reader_seconds"})
