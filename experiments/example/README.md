# Example experiment protocols — pre-calibration hardening

These directories are **templates**, not completed experiments. They exist to make the scientific design reviewable before runners or expensive compute are used.

Promote a template by copying it to a dated top-level experiment directory, freezing the corpus/query/qrel artefacts, completing the runtime manifest/preflight section, and adding the runner/analysis scripts. Do not edit a completed historical experiment to make it look as though the repaired design was what originally ran; mark old work superseded and create a new dated experiment instead.

## Order

| # | Template | Purpose | Expected cost | Blocks calibration? |
|---|---|---|---|---|
| 1 | `experiment-1-sentencesplitter-vs-codesplitter` | Prove AST code chunking really runs and improves structural integrity over the fallback | Tiny | Yes |
| 2 | `experiment-2-dense-cross-store-score-parity` | Prove Chroma/Lance satisfy the same dense ranking/score contract | Tiny | Yes |
| 3 | `experiment-3-hybrid-filter-and-threshold-semantics` | Prove hybrid filters cannot leak and thresholds are applied to compatible score kinds | Tiny | Yes |
| 4 | `experiment-4-bm25-cache-isolation` | Prove sparse cache isolation across stores/collections | Tiny | Yes |
| 5 | `experiment-5-reranker-backend-device-parity` | Separate ONNX/Torch backend precision from CPU/MPS/CoreML device effects | Small bounded inference | Yes for backend/device claims |
| 6 | `experiment-6-ingestion-boundedness-and-atomicity` | Measure peak memory/failure safety; decide whether concurrency redesign is warranted | Small synthetic | Yes |
| 7 | `experiment-7-metadata-cap-and-granularity` | Verify metadata chunk cap units and persisted granularity | Tiny/small LLM optional | Yes |
| 8 | `experiment-8-reranker-retrieval-pool-factorial` | Replace overlapping 9a-rerun + 10b with one paired factorial run | Large | Stage 6 |
| 9 | `experiment-9-technical-threshold-policy` | Calibrate technical routing only if Experiment 8 shows semantic reranker value worth preserving | Large/conditional | Stage 6 |
| 10 | `experiment-10-real-pdf-parser-ab` | Replace invalid Markdown-based Exp 14 with a true real-PDF pypdf vs LiteParse A/B | Medium/large | Stage 6 |

## Common scientific rules

1. **Pre-register before running.** Hypotheses, primary metric, manipulated variables, controls and decision thresholds are filled in before measured cells start.
2. **Use a runtime manifest.** Requested settings are not evidence that the requested backend/device/parser actually ran.
3. **Pair comparisons.** Reuse identical fixtures/query sets across cells unless the manipulated factor changes the index itself.
4. **Block first, randomise second.** Technical/semantic or document-type blocks have fixed membership across treatments; execution order can be counterbalanced.
5. **Separate correctness from performance.** A speed win never rescues a failed correctness gate.
6. **No silent fallback in treatment cells.** Production may degrade gracefully; experiments manipulating that component abort instead.
7. **Incomplete is not slow.** A hung/interrupted cell is `INCOMPLETE`, never an invented latency value.
8. **Keep raw data.** Store per-query/per-repetition rows and environment manifests alongside summaries.
9. **Immutable index identity.** Parser, chunker, embedding model/provider, corpus or other index-shaping changes create a different index identity.
10. **Default changes happen later.** Experiments produce evidence; an ADR/OpenSpec makes the production decision.

## Standard status vocabulary

- `PLANNED` — protocol exists; no measured result.
- `RUNNING` — measured work started; no conclusion yet.
- `PASS` — all pre-registered correctness/decision gates passed.
- `FAIL` — a pre-registered gate failed with valid completed evidence.
- `INCONCLUSIVE` — valid run, uncertainty/effect gate prevents a decision.
- `INCOMPLETE` — execution did not complete; never treat as evidence for/against the hypothesis.
- `INVALID` — manipulated/control variables or protocol execution were violated; results must not drive decisions.

## Minimum raw artefacts when promoted

```text
protocol.md
plan.json                 # machine-readable factors/cells/assertions
runtime_manifest.json     # or one per cell/repetition
raw_results.json          # per experimental unit
summary.json
results.md
run_eval.py
summarise_eval.py
output/checkpoint/
output/run_eval.log
```

Large indexes/corpora may remain gitignored, but their identities/hashes and reproduction commands must be committed.
