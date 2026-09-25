# ---
# jupyter:
#   jupytext:
#     cell_metadata_filter: -all
#     formats: ipynb,py:percent
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.16.0
#   kernelspec:
#     display_name: .venv
#     language: python
#     name: python3
# ---

# %% [markdown]
# # Experiment 34 — Worker sample review
# Operator verdicts per page and engine (review checklist v2), plus
# per-page seconds for the PaddleOCR-VL worker and the dots.mocr probe.
# Loads saved JSON only.

# %%
from __future__ import annotations

import json
from pathlib import Path

try:
    _ROOT = Path(__file__).parent
except NameError:
    _ROOT = Path.cwd()

import matplotlib.pyplot as plt
import pandas as pd

ENGINES = ["pdf_inspector", "liteparse", "local_ocr", "worker", "dots_mocr"]
FIELDS = ["output", "accuracy", "order", "structure", "table", "issues", "llm"]

verdicts = json.loads((_ROOT / "review_verdicts.json").read_text())
worker_state = json.loads((_ROOT / "output" / "worker_state.json").read_text())
dots_state = json.loads((_ROOT / "output" / "dots_mocr_state.json").read_text())

# %% [markdown]
# ## Verdicts: one row per page and engine

# %%
rows = []
for page, v in verdicts["pages"].items():
    for engine in ENGINES:
        e = v.get(engine, {})
        row = {"page": page, "engine": engine}
        for f in FIELDS:
            val = e.get(f, "")
            row[f] = ",".join(val) if isinstance(val, list) else val
        row["best"] = engine in v["page"]["best"]
        rows.append(row)
df = pd.DataFrame(rows)
df

# %% [markdown]
# ## Per-engine tallies (5 pages: 4 reviewed + eq01 p11)

# %%
tally = (
    df.groupby("engine")
    .agg(
        text=("output", lambda s: int((s == "text").sum())),
        llm_yes=("llm", lambda s: int((s == "yes").sum())),
        best=("best", "sum"),
    )
    .reindex(ENGINES)
)
tally

# %% [markdown]
# ## Pass gates on the reviewed set (A1)

# %%
reviewed = ["bd03/1", "bd03/2", "io06/28", "io06/53"]
complete = all(p in verdicts["pages"] for p in reviewed)
bd03_worker = [verdicts["pages"][p]["worker"] for p in ("bd03/1", "bd03/2")]
control_guard = all(
    w.get("accuracy") != "wrong" and w.get("structure") != "lost" for w in bd03_worker
)
io06_ok = sum(
    verdicts["pages"][p]["worker"].get("accuracy") in {"all", "most"}
    and verdicts["pages"][p]["worker"].get("llm") == "yes"
    for p in ("io06/28", "io06/53")
)
print(f"completeness: {complete}; control guard: {control_guard}; io06 worker ready: {io06_ok}/2")

# %% [markdown]
# ## Seconds per page: worker (CPU) vs dots.mocr (MPS)

# %%
t_rows = []
# A later run over other pages of a document is keyed "<doc>@<pages>" (run_worker.py).
worker_docs: dict[str, list[float]] = {}
for key, d in worker_state["done"].items():
    totals = worker_docs.setdefault(key.split("@")[0], [0.0, 0])
    totals[0] += d["seconds"]
    totals[1] += len(d["pages"])
for doc, (seconds, pages) in worker_docs.items():
    t_rows.append({"doc": doc, "engine": "worker", "s_per_page": seconds / pages})
dots_docs: dict[str, list[float]] = {}
for page, p in dots_state["pages"].items():
    dots_docs.setdefault(page.split("/")[0], []).append(p["seconds"])
for doc, secs in dots_docs.items():
    t_rows.append({"doc": doc, "engine": "dots_mocr", "s_per_page": sum(secs) / len(secs)})
timing = pd.DataFrame(t_rows).pivot(index="doc", columns="engine", values="s_per_page").round(1)
timing

# %%
fig, ax = plt.subplots(figsize=(8, 4))
timing.dropna().plot.bar(ax=ax)
ax.set_ylabel("seconds per page")
ax.set_title("Worker (CPU) vs dots.mocr (MPS), pages both engines ran")
plt.tight_layout()
plt.show()
