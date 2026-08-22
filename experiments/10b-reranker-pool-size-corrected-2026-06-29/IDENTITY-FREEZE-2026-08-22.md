# FreshStack identity freeze (task 6.1.2)

**Date opened:** 2026-08-22 · **Corpus frozen:** 2026-08-22 · **Indexes:** BUILD IN PROGRESS

## Frozen

| Artefact | Identity |
| --- | --- |
| Query/qrels (9a root) `freshstack-qrels.json` | sha256 `ccd3bc5732d69a3715a322c8557261f4f7c46ca72951ac6dce160e666e4b2c57` |
| Query/qrels (9a output) `output/freshstack-qrels.json` | sha256 `ccd3bc5732d69a3715a322c8557261f4f7c46ca72951ac6dce160e666e4b2c57` — byte-identical pair |
| Corpus manifest `corpus/langchain_manifest.jsonl` | sha256 `f6e7bb094cc661d83ccb8a55735cc2d3a72a481431a76b0a5c9285622e2f8ab0` |
| Corpus composition | 10,024 parent docs = 10,009 FreshStack LangChain + 15 exp-9 continuity; seed 20260530; `missing_qrel_ids: []` |

**Qrels reproducibility verified 2026-08-22:** regenerating via
`prepare_freshstack.py` (defaults, seed 20260530, upstream
`freshstack/{queries,corpus}-oct-2024`) reproduced both qrels files
byte-identically to the committed digests. Tracked files unchanged.

**Corpus drift vs the original 2026-05-30 build:** upstream now yields
10,009 FreshStack docs vs 10,010 originally (total 10,024 vs 10,025). The
drift is one distractor document; every qrel-relevant document is present
(`missing_qrel_ids` empty), so evaluation identity is unaffected. The
rebuilt indexes therefore differ from the lost originals by at most this
distractor, and the manifest hash above is the binding corpus identity for
Stage 6.

## Index identities — frozen (build complete 2026-08-22)

**Re-base decision (2026-08-22, user-ratified):** the D17 campaign re-based
its immutable inputs on the qualified LanceDB default (ADR-049 D11). A
Chroma build started first was killed at batch 10/101 and discarded; the
2026-08-21 chroma manipulated-factor declaration in `plan.json` is withdrawn.

| Item | Identity |
| --- | --- |
| Store directory | `output/lancedb_dense` (gitignored) |
| Collection | `exp10b-freshstack-langchain-seed-20260530-ollama-qwen3-embedding-0-6b` |
| Chunks | 10,024 (= corpus parent docs, 1 chunk per parent doc) |
| Embedding | `qwen3-embedding:0.6b` via Ollama, 1024-dim |
| Build time | 6,251 s (vs 19,371 s for the original Chroma build) |
| Build log | `output/build-run-2026-08-22-lancedb.log`; summary `output/index_build.json` |
| Hybrid BM25 | In-process at query time over the dense collection; no second index |
| Query smoke | Verified post-build: count 10,024; live dense probe returned scored FreshStack hits (0.6198 top) |

**Task 6.1.2 is CLOSED.** Corpus, query/qrel, and index identities are all
frozen above. The D17 campaign may start measured cells.

## Rule

No D17 cell may start until this file records index identities.
Update in place; do not delete prior digests.
