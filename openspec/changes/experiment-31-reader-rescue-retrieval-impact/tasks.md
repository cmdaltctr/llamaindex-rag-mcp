# Tasks: Experiment 31 Reader Rescue Retrieval Impact

## 1. Freeze the protocol

- [ ] 1.1 Define control and candidate cells in machine-readable form.
- [ ] 1.2 Freeze controlled variables: chunker, tokenizer, embedding identity, vector store, retrieval settings, reranker settings, and query order.
- [ ] 1.3 Define evidence-recoverability and retrieval metrics before measured execution.

## 2. Build the corpus and qrels

- [ ] 2.1 Register known Experiment 30/pathology documents as development or regression cases only.
- [ ] 2.2 Select an independent held-out set of natural text-layer extraction failures.
- [ ] 2.3 Label source-grounded evidence and queries without using either reader output as ground truth.
- [ ] 2.4 Hash and freeze the corpus, query set, and qrels.

## 3. Implement the experiment harness

- [ ] 3.1 Add `experiments/31-reader-rescue-retrieval-impact-<date>/` using the repository experiment templates.
- [ ] 3.2 Implement the `pdf-inspector`-only control without changing production code.
- [ ] 3.3 Run the candidate through the current production fallback chain.
- [ ] 3.4 Emit secret-free runtime manifests and separate index identities for both cells.

## 4. Validate before measured execution

- [ ] 4.1 Run contract/preflight checks for cell agreement and controlled variables.
- [ ] 4.2 Verify development cases exercise the expected empty-extraction path.
- [ ] 4.3 Verify measured outputs do not expose private document paths or text.

## 5. Execute and report

- [ ] 5.1 Run both cells on the frozen held-out corpus.
- [ ] 5.2 Report evidence recoverability, Recall@1/@3/@5/@10, MRR@10, and no-hit rate.
- [ ] 5.3 Report extraction latency, chunk count, embedding tokens, and index size where available.
- [ ] 5.4 Preserve per-query paired results and confidence intervals where justified.
- [ ] 5.5 Record limitations and retain negative findings.

## 6. Close the evidence loop

- [ ] 6.1 State whether the current reader rescue path has direct downstream retrieval evidence.
- [ ] 6.2 If production behaviour should change, create a separate OpenSpec proposal; do not modify it here.
