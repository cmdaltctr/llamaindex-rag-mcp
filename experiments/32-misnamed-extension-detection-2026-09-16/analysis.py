# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: percent
# ---

# %% [markdown]
# Experiment 32 — misnamed-extension content detection.
# Loads the saved smoke payloads and prints one label table per set.
# Analysis only: no experiment logic, no environment changes.

# %%
import json
from pathlib import Path

EXP = Path(__file__).resolve().parent
OUT = EXP / "output"

results = {
    name: json.loads((OUT / f"{name}.json").read_text(encoding="utf-8"))
    for name in ("baseline_pdf", "baseline_text", "swap_pdf_names", "swap_text_to_pdf")
}

# %%
rows = []
for name, result in results.items():
    payload = result["payload"]
    for group in payload["groups"]:
        for record in group["files"]:
            rows.append(
                {
                    "set": name,
                    "path": record["path"],
                    "suffix_label": record["suffix_label"],
                    "magika_label": record["magika_label"],
                    "would_change": record["would_change"],
                }
            )

# %%
try:
    import pandas as pd
except ImportError as exc:
    for row in rows:
        print(row)
    raise SystemExit(0) from exc

frame = pd.DataFrame(rows)
table = frame.pivot_table(
    index=["set", "magika_label"],
    columns="suffix_label",
    values="path",
    aggfunc="count",
    fill_value=0,
)
print(table)

# %% [markdown]
# Reading the table: every `swap_pdf_names` row carries the
# `document/pdf` Magika label whatever the lying extension produced,
# and every `swap_text_to_pdf` row keeps its content-true label behind
# a `.pdf` name. The baselines have identical label pairs on both
# sides, which is why they exit 0.

# %%
summary = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))
print("verdict:", summary["verdict"])
print(pd.Series({gate: check["passed"] for gate, check in summary["gates"].items()}))
