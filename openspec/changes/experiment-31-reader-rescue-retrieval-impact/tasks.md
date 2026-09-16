# Tasks: Experiment 31 Reader Rescue Retrieval Impact

## 1. Freeze the protocol

- [x] 1.1 Define the sanity-check, candidate, and reference cells in machine-readable form.
- [x] 1.2 Freeze controlled variables: `documents` profile, chunker, tokenizer, embedding identity, vector store, retrieval settings, reranker settings, OCR worker disabled, and query order.
- [x] 1.3 Define evidence-recoverability and retrieval metrics before measured execution.
- [x] 1.4 Freeze the text-span matching rule: case folding, whitespace collapse, hyphen rejoin, and fuzzy-match threshold.

## 2. Build the corpus and qrels

- [x] 2.1 Register known Experiment 30/pathology documents as development or regression cases only.
- [x] 2.2 Select an independent held-out set that meets the exact rescue trigger: `text_based`, at least one page, empty extraction.
- [x] 2.3 Target at least 5 held-out PDFs and 20-30 queries; record each PDF's failure type and the count of excluded partial extractions.
- [x] 2.4 Select 10-20 healthy text-based distractor PDFs where the rescue does not fire.
- [x] 2.5 Label source-grounded evidence spans and queries without using any reader output as ground truth.
- [x] 2.6 Hash and freeze the corpus, distractors, query set, qrels, and matching rule.

## 3. Implement the experiment harness

- [x] 3.1 Add `experiments/31-reader-rescue-retrieval-impact-<date>/` using the repository experiment templates.
- [x] 3.2 Implement the `pdf-inspector`-only sanity-check cell as a script-local mirror without changing production code.
- [x] 3.3 Run the candidate through the current production fallback chain.
- [x] 3.4 Implement the pypdf-only reference cell as a script-local mirror of the historical guard (commit 928f030).
- [x] 3.5 Build one index per cell containing the held-out and distractor groups.
- [x] 3.6 Emit secret-free runtime manifests, per-document `ocr_required`/`ocr_used`, and separate index identities for all cells.

## 4. Validate before measured execution

- [x] 4.1 Run contract/preflight checks for cell agreement and controlled variables.
- [x] 4.2 Verify development cases exercise the expected empty-extraction path.
- [x] 4.3 Verify every measured PDF produces zero chunks in the sanity-check cell.
- [x] 4.4 Abort a cell if any measured document reports `ocr_used=True`.
- [x] 4.5 Verify measured outputs do not expose private document paths or text.

## 5. Execute and report

- [x] 5.1 Run all three cells on the frozen held-out and distractor corpus.
- [x] 5.2 Report evidence recoverability, Recall@1/@3/@5/@10, MRR@10, and no-hit rate for each cell.
- [x] 5.3 Report extraction latency, chunk count, embedding tokens, and index size where available.
- [x] 5.4 Preserve per-query paired results for candidate against reference; add a paired bootstrap interval only with at least 20 measured queries.
- [x] 5.5 Record limitations, failure types covered, and retain negative findings.

## 6. Close the evidence loop

- [x] 6.1 State whether rescued text has direct downstream retrieval evidence, and whether the LiteParse-first chain retrieves as well as pypdf-only rescue.
- [x] 6.2 If production behaviour should change, create a separate OpenSpec proposal; do not modify it here.
