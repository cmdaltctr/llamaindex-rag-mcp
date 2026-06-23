# Experiment 11: LiteParse PDF Quality — Results

**Verdict:** `PARTIAL`

**Recommendation:** Quality win confirmed but speed win failed. Adopt LiteParse as auto default (quality > speed); record H2 failure in ADR-020.

## Executive summary

TODO: Operator replaces this section with a 1–3 paragraph summary of the 
bottom line after the experiment completes. State the verdict in the first
sentence, then the key metric movements, then any caveats.

## Setup

- Platform: `macOS-26.5.1-arm64-arm-64bit`
- Python: `3.12.10`
- Corpus size: `25 queries`
- Top-K: `50`
- K values reported: `[5, 10, 20, 50]`
- Hybrid retrieval: OFF (per protocol.md, isolates parser variable)

## Cell metrics (all queries)

| Cell | n | nDCG@10 | Hit@5 | Hit@10 | Hit@20 | MRR@10 | Coverage@20 | P95 ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `pypdf__rerank_false` | 25 | 3.0000 | 0.960 | 1.000 | 1.000 | 0.9467 | 1.000 | 429.8 |
| `pypdf__rerank_true` | 25 | 3.0333 | 0.960 | 1.000 | 1.000 | 0.9183 | 1.000 | 54921.7 |
| `liteparse__rerank_false` | 25 | 3.2066 | 1.000 | 1.000 | 1.000 | 0.9333 | 1.000 | 473.9 |
| `liteparse__rerank_true` | 25 | 3.1500 | 1.000 | 1.000 | 1.000 | 0.9133 | 1.000 | 29551.2 |

## Per-category breakdown

TODO: Operator expands this section with per-category tables (two_column,
single_column, table_heavy) to show where LiteParse helps or hurts.

## Pass gates

- **H1_quality_win**: `{"baseline_ndcg10": 2.999984, "candidate_ndcg10": 3.206648, "ratio": 1.0689, "threshold": ">= 1.05", "pass": true}`
- **H2_speed_win**: `{"baseline_seconds": 932.842, "candidate_seconds": 990.611, "ratio": 1.0619, "threshold": "<= 0.80", "pass": false}`
- **H3_reranker_still_helps**: `{"no_rerank_ndcg10": 3.206648, "with_rerank_ndcg10": 3.149992, "ratio": 0.9823, "threshold": ">= 1.05", "pass": false}`
- **H4_no_lost_queries**: `{"threshold": "0 queries drop from found to not-found", "pass": true, "lost_count": 0}`

## Build timing (H2 evidence)

| Parser | Total (s) | Parse (s) | Chunk (s) | Embed (s) | Files OK | Chunks |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `pypdf` | 932.842 | 30.88 | 2.353 | 899.606 | 22 | 2858 |
| `liteparse` | 990.611 | 5.629 | 1.897 | 983.082 | 20 | 3280 |

## H4 — Queries lost (pypdf found, liteparse not found)

- Count: **0**
- Pass: **True**


## Conclusion / decision

TODO: Operator writes the final decision — what ships, what does not,
what follow-up is allowed. Reference ADR-020 (pending).

## Artefacts

- Raw results: `output/eval_results.json`
- Summary JSON: `output/eval_results.summary.json`
- Run log: `output/run_eval.log`
- Build timing: `output/build_pypdf_timing.json`, `output/build_liteparse_timing.json`
- Protocol: `protocol.md`
- Ground truth: `ground_truth.json`
