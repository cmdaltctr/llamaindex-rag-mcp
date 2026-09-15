# Experiment 31: Reader Rescue Retrieval Impact

## Why

Experiment 30 showed that the tiered reader fallback chain can recover text when `pdf-inspector` returns an empty extraction. It did not measure whether that recovered text improves downstream retrieval.

OMRG needs direct evidence that the current `pdf-inspector -> LiteParse -> pypdf` rescue path restores answer-supporting evidence and reduces retrieval failures on affected PDFs.

## What Changes

- Add Experiment 31 under `experiments/31-reader-rescue-retrieval-impact-<date>/` when execution is approved.
- Compare `pdf-inspector` only against the current tiered reader fallback chain.
- Keep chunking, embedding, vector store, retrieval, reranking, queries, and qrels fixed across cells.
- Use known pathological PDFs only for harness checks and regression coverage.
- Use an independent held-out set of natural text-layer extraction failures for the measured result.
- Measure evidence recoverability before retrieval and retrieval quality after indexing.
- Record runtime and index-cost measurements as secondary outcomes.
- Do not change production reader defaults or fallback behaviour in this change.

## Capabilities

### New Capabilities

- `reader-rescue-evaluation`: defines the controlled evaluation contract for measuring whether the tiered PDF reader rescue path improves evidence recovery and retrieval.

### Modified Capabilities

- None.

## Impact

- Adds experiment artefacts only.
- Reuses the current production ingestion and retrieval components through an experiment harness.
- Does not change public APIs, packaged defaults, or runtime behaviour.
- Any production change suggested by the result requires a separate OpenSpec change and decision record.
