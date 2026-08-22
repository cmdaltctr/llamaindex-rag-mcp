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

## Index identities — build in flight

| Index | Status |
| --- | --- |
| `output/chroma_dense` | Building since 2026-08-22 21:13 (PID 84625, log `output/build-run-2026-08-22.log`); `EMBED_MODEL=qwen3-embedding:0.6b` (1024-dim, matches original index identity), batch 100, 101 batches |
| `output/chroma_hybrid_bm25` | Will be copied from dense on completion (BM25 builds at query time) |

Original build reference: 10,025 chunks in 19,371 s. Expected completion:
early hours 2026-08-23. When `output/index_build.json` lands, record chunk
count + collection identity here and close task 6.1.2.

## Rule

No D17 cell may start until this file records index identities.
Update in place; do not delete prior digests.
