"""Experiment 25 report renderer: results.md generation for summarise_eval.

Split from ``summarise_eval.py`` to respect the 500-line file ceiling.
Owns the presentation constants and all results.md rendering. Prose is
data-driven: it adapts to the computed gate verdict so a FAIL renders
as honestly as a PASS.
"""

from __future__ import annotations

from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent

CELLS = ("baseline_splitter", "model_token_markdown")
CELL_NAMES = {
    "baseline_splitter": "baseline (exp 22 hybrid__raw checkpoint)",
    "model_token_markdown": "model-token Markdown chunker (candidate)",
}
CAT_ORDER = ("all", "identifier-heavy", "semantic", "continuity")
CAT_TITLES = {
    "all": "All queries",
    "identifier-heavy": "Identifier-heavy queries",
    "semantic": "Semantic queries",
    "continuity": "Continuity queries",
}
# (json key, table header, direction) — "up" = higher is better.
TABLE_COLS = (
    ("recall_at_1", "R@1", "up"),
    ("recall_at_3", "R@3", "up"),
    ("recall_at_5", "R@5", "up"),
    ("recall_at_10", "R@10", "up"),
    ("recall_at_50", "R@50", "up"),
    ("coverage_at_20", "Coverage@20", "up"),
    ("alpha_ndcg_at_10", "α-nDCG@10", "up"),
    ("hit_at_10", "Hit@10", "up"),
    ("mrr_at_10", "MRR@10", "up"),
    ("mean_latency_ms", "Mean latency", "down"),
    ("p95_latency_ms", "P95 latency", "down"),
)


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _ms(value: float) -> str:
    return f"{value:,.0f} ms"


def _fmt(gate: dict) -> str:
    """Format a gate value at comparison-transparent precision."""
    return f"{gate['value']:,.1f}" if gate["metric"].endswith("ms") else f"{gate['value']:.6f}"


def _cat_table(by_cell: dict, cat: str) -> list[str]:
    """Render one per-category comparison table (exp 22 house format)."""
    headers = [hdr for _, hdr, _ in TABLE_COLS]
    out = [
        "| Cell | " + " | ".join(headers) + " |",
        "| --- | " + " | ".join(["---:"] * len(headers)) + " |",
    ]
    for cell in CELLS:
        agg = by_cell[cell][cat]
        row = [CELL_NAMES[cell]]
        for key, _, direction in TABLE_COLS:
            row.append(_ms(agg[key]) if direction == "down" else _pct(agg[key]))
        out.append("| " + " | ".join(row) + " |")
    return out


def write_results_md(
    summary: dict, gates: dict, overall_pass: bool, qrels_sha: str, build: dict
) -> None:
    """Render results.md in the exp 22 house format plus the gate verdict."""
    by_cell = summary["metrics_by_cell"]
    b, c = by_cell["baseline_splitter"], by_cell["model_token_markdown"]
    b_all, c_all = b["all"], c["all"]
    pp = lambda key: f"{(c_all[key] - b_all[key]) * 100:+.1f} pp"  # noqa: E731
    verdict_word = "PASS" if overall_pass else "FAIL"
    failed = [k for k, g in gates.items() if not g["pass"]]
    status_tail = (
        " (all four gates passed)" if overall_pass else f" (failed: {', '.join(failed)})"
    )
    tok = build.get("tokenizer")
    tok_cell = (
        f"`{tok['model']}` @ `{tok['revision'][:12]}…`"
        if isinstance(tok, dict)
        else "see build record"
    )
    delta_r5 = (c_all["recall_at_5"] - b_all["recall_at_5"]) * 100
    delta_r10 = (c["identifier-heavy"]["recall_at_10"] - b["identifier-heavy"]["recall_at_10"]) * 100
    q, r, lat = gates["quality"], gates["regression"], gates["latency"]
    quality_note = (
        f"clears the floor by {abs(q['value'] - q['threshold']):.6f} (paired "
        f"difference {delta_r5:+.2f} pp vs baseline, inside the ±2.48 pp "
        f"bootstrap noise band the floor encodes)"
        if q["pass"]
        else f"misses the floor by {abs(q['value'] - q['threshold']):.6f} "
        f"(paired difference {delta_r5:+.2f} pp vs baseline — the quality "
        f"drop exceeds the noise allowance)"
    )

    lines = [
        "# Experiment 25 Results: Model-Token-Aware Markdown Chunking Ablation",
        "",
        "**ID**: `25-token-chunking-ablation-2026-09-08`  ",
        "**Date evaluated**: 2026-09-09  ",
        "**Operator**: Dr Muhammad Aizat Bin Md Hawari with AI agent  ",
        f"**Status**: COMPLETE — frozen-gate verdict: **{verdict_word}**{status_tail}.  ",
        "**Raw data**: [`output/eval_results.summary.json`](./output/eval_results.summary.json)",
        "",
        "---",
        "",
        "## Executive summary",
        "",
        "This experiment rebuilt the Experiment 22 corpus index with the merged "
        "model-token-aware Markdown chunker (ADR-063: `semantic-text-splitter` "
        "+ pinned Qwen tokenizer) and evaluated the identical 223 raw queries "
        "under the identical hybrid retrieval configuration (BM25 + dense, RRF "
        "k=60, rerank disabled, top_k 50, `qwen/qwen3-embedding-4b` via "
        "OpenRouter). The baseline arm is Experiment 22's `hybrid__raw` "
        "checkpoint, loaded and re-aggregated with the same metric code — "
        "cross-checked equal to the published summary before gating.",
        "",
        f"The candidate index stores {build.get('chunk_count'):,} chunks against the "
        f"baseline's 32,631 (-31.7%) and its build spent "
        f"{gates['cost']['value']:.6f} × the baseline's embedded request tokens. "
        f"Mean Recall@5 over all 223 queries is {_pct(c_all['recall_at_5'])} against "
        f"the baseline's {_pct(b_all['recall_at_5'])} ({pp('recall_at_5')}). "
        f"Identifier-heavy Recall@10 (n=200) is "
        f"{_pct(c['identifier-heavy']['recall_at_10'])} vs "
        f"{_pct(b['identifier-heavy']['recall_at_10'])} ({delta_r10:+.1f} pp). "
        f"Candidate query P95 latency is {_ms(c_all['p95_latency_ms'])} against the "
        f"baseline's {_ms(b_all['p95_latency_ms'])}.",
        "",
        f"**Overall verdict: {verdict_word}.**"
        + (
            " All four frozen validity gates passed."
            if overall_pass
            else f" Failed gate(s): {', '.join(failed)}. Per the interpretation "
            "rules in [`protocol.md`](./protocol.md), this verdict stands as "
            "measured; no re-runs, no threshold edits."
        ),
    ]
    if overall_pass:
        lines += [
            "",
            f"**Recommendation (task 5.5): promote the chunker.** The measured "
            "benefit is cost and input-contract correctness, not quality: "
            "embedded request tokens −2.5%, largest chunk halved (2,087 → "
            "1,120 payload tokens), retrieval neutral. Two costs travel with "
            "the promotion:",
            "",
            f"1. Mean query latency rose from {_ms(b_all['mean_latency_ms'])} to "
            f"{_ms(c_all['mean_latency_ms'])} (fewer, fuller chunks cost more to "
            "score; P95 stays inside the frozen cap). If interactive agents "
            "find this too slow, the fix is a smaller "
            "`CHUNKING__MARKDOWN_CHUNK_SIZE`, not a return to character "
            "budgeting.",
            f"2. The R@5 point estimate sits {abs(delta_r5):.1f} pp below "
            "baseline, inside the ±2.48 pp noise band. One non-inferiority "
            "result is evidence of a wash. A second measurement below "
            "baseline would be a trend; treat it as one.",
        ]
    lines += [
        "",
        "## Frozen-gate verdict",
        "",
        "Thresholds are read from the frozen [`plan.json`](./plan.json) "
        "(task 1.6, frozen 2026-09-08, before any candidate measurement). "
        "Comparisons use unrounded values; the table shows them at "
        "comparison-transparent precision.",
        "",
        "| Gate | Metric | Scope | Value (unrounded) | Threshold | Verdict |",
        "| --- | --- | --- | ---: | ---: | :-: |",
    ]
    for kind in ("quality", "regression", "cost", "latency"):
        g = gates[kind]
        verdict = "**PASS**" if g["pass"] else "**FAIL**"
        lines.append(
            f"| {kind.capitalize()} | {g['metric']} | {g['scope']} | {_fmt(g)} | "
            f"{g['comparator']} {g['threshold']} | {verdict} |"
        )
    lines += [
        "",
        "*Cost gate basis: retrospective corrected accounting "
        "(`verify_accounting.py`, TDR-022 method, committed in 8902309) — "
        "request-text ratio is operative; the pre-adapter EMBED-basis ratio is "
        "recorded in the gate basis in the summary JSON. Latency basis: "
        "per-query wall time around `pipeline.search` exactly as Experiment 22 "
        "measured it (query embedding via OpenRouter included, no warm-up "
        "pass); p95 over the 223 candidate queries with the same order "
        "statistic.*",
        "",
        "## Corpus and setup",
        "",
        "| Parameter | Value |",
        "| --- | --- |",
        "| Corpus source | FreshStack LangChain, October 2024 (exp 22 preserved copy) |",
        "| Parent documents indexed | 10,024 (10,009 FreshStack + 15 continuity) |",
        f"| Chunks stored (candidate) | {build.get('chunk_count'):,} (model-token Markdown chunker) |",
        "| Chunks stored (baseline) | 32,631 (exp 22 production chunking) |",
        f"| Chunker tokenizer | {tok_cell} |",
        "| Query set | 203 FreshStack test queries + 20 continuity = 223 total |",
        "| Query categories | 200 identifier-heavy, 3 semantic, 20 continuity |",
        "| Query path | raw (no instruction template) |",
        "| Embedding model | `qwen/qwen3-embedding-4b` via OpenRouter (cloud) |",
        "| Embedding width | 2560 |",
        "| Vector store | LanceDB (one row per chunk, parent-level relevance) |",
        "| Fusion | RRF, k = 60 (production default `hybrid_rrf_k`) |",
        "| Reranking | disabled |",
        "| Fetch depth | top_k = 50 |",
        f"| Qrels sha256 | `{qrels_sha[:16]}…` (identical to exp 22) |",
        "",
        "## Cell metrics",
        "",
    ]
    for cat in CAT_ORDER:
        lines += [
            f"### {CAT_TITLES[cat]} (n = {by_cell['baseline_splitter'][cat]['n']})",
            "",
            *_cat_table(by_cell, cat),
            "",
        ]
        if cat == "all":
            lines += [
                "*Metric definitions as in Experiment 22's results: R@K = recall "
                "at cutoff K over deduplicated parent rankings; Coverage@20 = "
                "mean fraction of a query's nuggets covered by the top-20 "
                "results; α-nDCG@10 = alpha-normalised DCG at 10; Hit@10 = "
                "queries with at least one relevant document in the top 10; "
                "MRR@10 = mean reciprocal rank at 10; Mean/P95 latency include "
                "the OpenRouter network round-trip.*",
                "",
            ]
        else:
            lines += ["*Metric definitions as in the all-queries table.*", ""]
        if cat == "semantic":
            lines += ["*Note: only 3 semantic queries — too few for statistical conclusions.*", ""]

    lines += [
        "## Monitored, not gated",
        "",
        "| Metric | Baseline | Candidate | Δ |",
        "| --- | ---: | ---: | ---: |",
        f"| Continuity R@10 (n=20) | {_pct(b['continuity']['recall_at_10'])} | "
        f"{_pct(c['continuity']['recall_at_10'])} | "
        f"{(c['continuity']['recall_at_10'] - b['continuity']['recall_at_10']) * 100:+.1f} pp |",
        "",
        "*Per the frozen plan, continuity R@10 is recorded and inspected, not "
        "gated: at n=20 the bootstrap 95% half-width is ±0.15, so a hard gate "
        "would be noise.*",
        "",
        "## Arm comparison (all queries)",
        "",
        "| Metric | Baseline | Candidate | Δ (candidate − baseline) |",
        "| --- | ---: | ---: | ---: |",
    ]
    for key, label in (
        ("recall_at_1", "Recall@1"),
        ("recall_at_5", "Recall@5"),
        ("recall_at_10", "Recall@10"),
        ("recall_at_50", "Recall@50"),
        ("coverage_at_20", "Coverage@20"),
        ("alpha_ndcg_at_10", "α-nDCG@10"),
        ("hit_at_10", "Hit@10"),
        ("mrr_at_10", "MRR@10"),
    ):
        lines.append(f"| {label} | {_pct(b_all[key])} | {_pct(c_all[key])} | {pp(key)} |")
    lines.append(
        f"| Mean latency | {_ms(b_all['mean_latency_ms'])} | {_ms(c_all['mean_latency_ms'])} | "
        f"{c_all['mean_latency_ms'] - b_all['mean_latency_ms']:+,.0f} ms |"
    )
    lines.append(
        f"| P95 latency | {_ms(b_all['p95_latency_ms'])} | {_ms(c_all['p95_latency_ms'])} | "
        f"{c_all['p95_latency_ms'] - b_all['p95_latency_ms']:+,.0f} ms |"
    )

    lines += [
        "",
        "## Interpretation",
        "",
        f"1. Chunk count falls from 32,631 to {build.get('chunk_count'):,} "
        f"(-31.7%) while embedded request tokens fall to "
        f"{gates['cost']['value']:.4f} × baseline — the token-aware splitter "
        f"produces fewer, more model-aligned chunks and spends less to index "
        f"the same corpus.",
        f"2. Quality: candidate mean R@5 {_fmt(q)} against the frozen floor "
        f"{q['threshold']} — {quality_note}.",
        f"3. Regression (identifier-heavy R@10): candidate {_fmt(r)} against "
        f"the frozen floor {r['threshold']} — "
        f"{'clears' if r['pass'] else 'misses'} by "
        f"{abs(r['value'] - r['threshold']):.6f} (paired difference "
        f"{delta_r10:+.2f} pp). This is the at-risk workload for "
        f"heading-prefix tokens and identifier splitting.",
        f"4. Latency: candidate P95 {_fmt(lat)} ms against the "
        f"{lat['threshold']:,} ms cap — {'passes' if lat['pass'] else 'fails'} "
        f"with {abs(lat['threshold'] - lat['value']) / 1000:.1f} s headroom. "
        f"Both arms bundle the OpenRouter round-trip, so the tail is "
        f"network-dominated.",
    ]
    if overall_pass:
        lines.append(
            "5. All four gates pass: per the interpretation rules, the "
            "candidate is eligible for task 5.5's promotion judgement, which "
            "weighs lift and cost together (fewer chunks, less spend, quality "
            "held inside noise)."
        )
    else:
        lines.append(
            "5. Verdict recorded as FAIL per the frozen interpretation rules: "
            + (
                "quality floor missed with regression held — a negative "
                "result; current splitter defaults stay and ADR-063 stays "
                "Proposed."
                if not q["pass"] and r["pass"]
                else "see the failed gate rows above; investigate before any "
                "re-run, and do not relax thresholds."
            )
        )

    if overall_pass:
        lines += [
            "",
            "## Discussion",
            "",
            "The gates asked one question: does the new chunker damage "
            "retrieval? The answer is no. That was the right safety question, "
            "but it was never the reason the chunker exists. ADR-063 chose "
            "token units because the embedding model, the API bill, and the "
            "context window all count in tokens. Characters are a proxy with "
            "a drifting exchange rate. Four characters per token holds for "
            "English prose. It collapses on code, JSON, error dumps, and "
            "heading paths, which is what this corpus is made of.",
            "",
            "The measurement shows that failure mode was real, not "
            "theoretical. The baseline splitter produced chunks up to 2,087 "
            "tokens. The candidate tops out at 1,120. On token-dense Markdown "
            "the character estimate ran at nearly double the intended "
            "budget, and every oversize chunk was invisible from the "
            "character side.",
            "",
            "Retrieval came out a wash for a structural reason. Both paths "
            "are heading-aware, so changing the size budget mostly changes "
            "which part of the right document surfaces, not whether the "
            "document surfaces at all. Sizing accuracy was never likely to "
            "move R@5 on this workload.",
            "",
            "What sizing accuracy buys is an honest input contract. Spend is "
            "measured in the unit the provider bills. Chunks respect the cap "
            "the operator configured. This experiment demonstrated the same "
            "point from an unplanned direction: the TDR-022 accounting "
            "corrections existed because character-era tooling could not "
            "measure tokens, and that gap produced two wrong counters before "
            "a right one.",
        ]

    lines += [
        "",
        "## Reproduction",
        "",
        "```bash",
        "# Candidate index (already built; build_index.py refuses paid rebuilds,",
        "# see TDR-022)",
        "uv run --no-sync python build_index.py --resume",
        "",
        "# Evaluation cell (checkpoint/resume; single candidate arm)",
        "uv run --no-sync python run_eval.py",
        "",
        "# Aggregates + gates + this report",
        "uv run --no-sync python summarise_eval.py",
        "```",
        "",
        "The baseline arm is Experiment 22's `hybrid__raw` checkpoint, loaded "
        "read-only. The preserved indexes live outside the repository (exp 22 "
        "`DATA_LOCATIONS.md`).",
        "",
        "## Artefacts",
        "",
        "| File | Description |",
        "| --- | --- |",
        "| `protocol.md` | Pre-run plan and measurement intent |",
        "| `plan.json` | Frozen machine-readable plan and gates (never edited post-results) |",
        "| `build_index.py` | Candidate index builder (paid rebuilds refused) |",
        "| `run_eval.py` | Candidate evaluation runner with checkpoint/resume |",
        "| `summarise_eval.py` + `report.py` | Aggregator, gate evaluation, this report |",
        "| `token_accounting.py` | Deprecated pre-spend counter (defects documented in protocol) |",
        "| `verify_accounting.py` | Retrospective corrected cost accounting |",
        "| `output/eval_results.summary.json` | Aggregates, gates, runtime manifest |",
        "| `output/cells/model_token_markdown.json` | Candidate per-query checkpoint |",
        "| `output/build_done.json` | Index build record |",
        "| `output/verify_accounting_*.json` | Cost-gate evidence (both sides) |",
        "",
        "---",
        "",
        "*Raw metrics: `output/eval_results.summary.json`*  ",
        "*Per-query checkpoint: `output/cells/model_token_markdown.json`*  ",
        "*Baseline checkpoint: `experiments/22-raw-query-qwen4b-baseline-2026-09-07/output/cells/hybrid__raw.json`*",
    ]
    (EXP_DIR / "results.md").write_text("\n".join(lines), encoding="utf-8")
