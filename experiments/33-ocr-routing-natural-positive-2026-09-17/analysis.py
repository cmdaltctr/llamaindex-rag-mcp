# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: percent
# ---

# %% [markdown]
# # Experiment 33 analysis
#
# Loads the frozen labels, per-page evidence and both Stage A arms. It runs no
# experiment logic, touches no environment variable and calls no reader.

# %%
import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

EXP = Path(__file__).resolve().parent if "__file__" in dir() else Path.cwd()
OUT = EXP / "output"
ARMS = ("sampled_baseline", "full_scan_candidate")

pages = pd.DataFrame(json.loads((OUT / "page_evidence.json").read_text())["pages"])
labels = pd.DataFrame(json.loads((EXP / "labels.json").read_text())["documents"]).T
labels.index.name = "doc_id"
summaries = {
    arm: json.loads((OUT / f"arm_{arm}" / "eval_results.summary.json").read_text()) for arm in ARMS
}
routing = {
    arm: pd.DataFrame(json.loads((OUT / f"arm_{arm}" / "routing.json").read_text())["rows"])
    for arm in ARMS
}

# %% [markdown]
# ## Headline measurements per arm

# %%
headline = pd.DataFrame(
    {
        arm: {
            "recall": s["primary"]["routing_recall"],
            "false_negatives": s["primary"]["false_negative_count"],
            "precision": s["secondary"]["routing_precision"],
            "false_positives": s["secondary"]["false_positive_count"],
            "routed_documents": s["secondary"]["routed_documents"],
            "routed_pages": s["secondary"]["routed_pages"],
            "unnecessary_ocr_pages": s["secondary"]["unnecessary_ocr_pages"],
        }
        for arm, s in summaries.items()
    }
)
headline

# %% [markdown]
# ## Where the labels came from
#
# `operator` pages are the operator's presence verdicts; they override the rule.

# %%
pages.groupby(["label_source", "label"]).size().unstack(fill_value=0)

# %% [markdown]
# ## Page labels by stratum

# %%
stratum = labels.reset_index()[["doc_id", "stratum", "label", "pages", "figure_tokens_missing"]]
page_counts = pd.json_normalize(labels["page_labels"]).set_index(labels.index)
stratum.join(page_counts, on="doc_id").groupby("stratum").sum(numeric_only=True)

# %% [markdown]
# ## Word recall distribution by final label
#
# The overlap explains the operator disagreement: many `needs_ocr` pages carry
# most of their words and lose only equations or structure.

# %%
fig, ax = plt.subplots(figsize=(7, 4))
for label, group in pages[pages["body_reference_tokens"] >= 10].groupby("label"):
    ax.hist(group["body_r_best"], bins=20, alpha=0.5, label=f"{label} (n={len(group)})")
ax.set_xlabel("body-text token recall (better of poppler, pypdf)")
ax.set_ylabel("pages")
ax.legend()
fig.tight_layout()

# %% [markdown]
# ## Documents whose route differs between arms

# %%
pd.DataFrame(json.loads((OUT / "arm_comparison.json").read_text())["arm_divergence"])

# %% [markdown]
# ## Missed documents with their evidence

# %%
missed = summaries["full_scan_candidate"]["primary"]["false_negative_ids"]
routing["full_scan_candidate"].set_index("doc_id").loc[
    missed,
    ["stratum", "pdf_type", "pdf_confidence", "pages_needing_ocr", "extraction_fallback_backend"],
].join(labels[["pages", "needs_ocr_share"]])
