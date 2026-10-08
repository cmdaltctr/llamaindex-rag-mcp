# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:percent
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#   kernelspec:
#     display_name: .venv
#     language: python
#     name: python3
# ---

# %% [markdown]
# # Experiment 38: rescue-quality signals and the local OCR follow-up
# Load saved summaries only. Model inference and threshold selection do not run here.

# %%
"""Read-only tables and plots from the saved Experiment 38 results."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

try:
    ROOT = Path(__file__).resolve().parent
except NameError:
    ROOT = Path.cwd()

summary = json.loads((ROOT / "output" / "summary.json").read_text(encoding="utf-8"))

# %% [markdown]
# ## Both operating points and both rescue tiers

# %%
rows = []
for candidate, result in summary["candidates"].items():
    for point, data in result["operating_points"].items():
        for tier, population in data["populations"].items():
            rows.append(
                {
                    "candidate": candidate,
                    "point": point,
                    "tier": tier,
                    **{
                        key: population[key]
                        for key in (
                            "threshold",
                            "junk_recall",
                            "healthy_false_positive_rate",
                            "junk_flagged",
                            "junk_pages",
                            "healthy_false_positives",
                            "healthy_pages",
                        )
                    },
                }
            )
main_table = pd.DataFrame(rows)
print(main_table.to_string(index=False))

# %% [markdown]
# ## Per-document junk recall at equal cost

# %%
rows = []
for candidate, result in summary["candidates"].items():
    documents = result["operating_points"]["equal_cost"]["populations"]["liteparse"]["per_document"]
    for doc_id, measured in documents.items():
        rows.append(
            {
                "candidate": candidate,
                "document": doc_id,
                "junk_pages": measured["junk_pages"],
                "junk_recall": measured["junk_recall"],
            }
        )
per_document_table = pd.DataFrame(rows)
per_document_table

# %% [markdown]
# ## Local text: ranking and the unchanged thresholds

# %%
rows = []
for candidate, data in summary["local_text_followup"]["signals"].items():
    for population in ("gated", "io06"):
        rows.append({"candidate": candidate, "population": population, **data[population]})
followup_table = pd.DataFrame(rows)
print(followup_table.to_string(index=False))

# %%
primary = main_table[main_table["tier"] == "liteparse"].copy()
primary["label"] = primary["candidate"] + " / " + primary["point"]
figure, axes = plt.subplots(1, 2, figsize=(12, 4))
primary.plot.bar(x="label", y=["junk_recall", "healthy_false_positive_rate"], ax=axes[0])
axes[0].set_title("Rescue text: detection and healthy-page cost")
axes[0].set_ylabel("Share of pages")
axes[0].axhline(0.02, linestyle=":", label="Healthy-page ceiling")
local = followup_table.pivot(index="population", columns="candidate", values="auc")
local.plot.bar(ax=axes[1])
axes[1].axhline(0.788, linestyle=":", label="Experiment 39 character-count AUC")
axes[1].axhline(0.8, linestyle="--", label="Follow-up trigger")
axes[1].set_title("Saved local OCR: AUC")
axes[1].set_ylabel("AUC, higher separates bad text better")
axes[1].set_ylim(0, 1)
axes[1].legend()
figure.tight_layout()
plt.show()

# %% [markdown]
# ## Amendment A3: held-out (leave-one-document-out) verdict
# Read from `lodo_summary.json`. Skipped when the file is absent.

# %%
lodo_path = ROOT / "output" / "lodo_summary.json"
lodo_table = None
if lodo_path.exists():
    lodo = json.loads(lodo_path.read_text(encoding="utf-8"))
    lodo_table = pd.DataFrame(
        [
            {
                "candidate": name,
                "junk_flagged": data["populations"]["liteparse"]["junk_flagged"],
                "healthy_flagged": data["populations"]["liteparse"]["healthy_false_positives"],
                **data["gates"],
            }
            for name, data in lodo["candidates"].items()
        ]
    )
    print(lodo_table.to_string(index=False))
    ceiling = int(0.02 * lodo["candidates"]["A"]["populations"]["liteparse"]["healthy_pages"])
    axis = lodo_table.plot.scatter(x="healthy_flagged", y="junk_flagged", figsize=(6, 4))
    for _, row in lodo_table.iterrows():
        axis.annotate(row["candidate"], (row["healthy_flagged"], row["junk_flagged"]))
    axis.axvline(ceiling + 0.5, linestyle=":", label="G3 ceiling")
    axis.set_title("Held-out thresholds: junk caught against healthy pages flagged")
    axis.legend()
    plt.show()
