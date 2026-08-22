# FreshStack identity freeze — partial (task 6.1.2)

**Date:** 2026-08-22
**Status:** PARTIAL — qrels frozen; corpus and index identities pending.

## Frozen now

| Artefact | SHA-256 |
| --- | --- |
| `experiments/9a-hybrid-retrieval-freshstack-langchain-2026-05-30/freshstack-qrels.json` | `ccd3bc5732d69a3715a322c8557261f4f7c46ca72951ac6dce160e666e4b2c57` |
| `experiments/9a-hybrid-retrieval-freshstack-langchain-2026-05-30/output/freshstack-qrels.json` | `ccd3bc5732d69a3715a322c8557261f4f7c46ca72951ac6dce160e666e4b2c57` |

Both copies are byte-identical; this single digest is the query/qrel
identity for the Stage 6.1 (D17) campaign. The file was produced by
`prepare_freshstack.py` from the 9a continuity selection.

## Pending

- **Corpus identity.** The FreshStack corpus export (`corpus/`) was not
  retained after the 9a/10b v1 runs and is absent from disk. Regenerate
  with `prepare_freshstack.py`, then hash every corpus file and record the
  manifest here before any cell runs. Regeneration requires the FreshStack
  source download.
- **Index identities.** The 10b `output/chroma_dense` and
  `output/chroma_hybrid_bm25` symlinks currently dangle (9a's index
  directories were not retained). Stage 6 index builds must use the
  immutable-index naming contract and their manifest IDs recorded here.
  Index building requires the embedding backend and is deferred while the
  exp5b measurement campaign owns the machine.

## Rule

No D17 cell may start until this file records corpus and index identities.
Update in place; do not delete prior digests.
