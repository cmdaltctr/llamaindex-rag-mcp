# Experiment 31: Reader Rescue Retrieval Impact

## Why

Experiment 30 showed that the tiered reader fallback chain can recover text when `pdf-inspector` returns an empty extraction. It did not measure whether that recovered text improves downstream retrieval.

Without a rescue, an affected PDF produces no chunks, so any rescue beats no rescue by definition. The open questions are different:

- Does the rescued text survive chunking and embedding well enough to retrieve the gold evidence?
- Experiment 30 found that LiteParse returns 2-16% fewer characters than pypdf, because it omits textless pages and joins text differently. Does that change retrieval quality?

## What Changes

- Add Experiment 31 under `experiments/31-reader-rescue-retrieval-impact-<date>/` when execution is approved.
- Run three cells: `pdf-inspector` only (harness sanity check), the current tiered chain (candidate), and a pypdf-only rescue (reference).
- Use the candidate against the reference as the measured comparison.
- Keep chunking, embedding, vector store, retrieval, reranking, OCR routing, queries, and qrels fixed across cells.
- Use known pathological PDFs only for harness checks and regression coverage.
- Use an independent held-out set of natural PDFs that meet the production rescue trigger for the measured result.
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
