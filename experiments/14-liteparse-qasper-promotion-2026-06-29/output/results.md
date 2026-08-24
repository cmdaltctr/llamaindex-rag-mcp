# Experiment 14 Results: LiteParse Promotion on Qasper

**Recommendation:** The approved timing rerun and quality results nominate `pdf_inspector` as the candidate default. The parser-only recording rerun completes task 6.3.3. Keep production settings unchanged until the result artefacts are committed and a follow-up ADR/OpenSpec accepts the policy. The earlier ambient-load result remains documented in [the deviation record](DEVIATION-2026-08-24-ambient-load.md).

## Gate summary

| Gate | Result | Detail |
| --- | :--: | --- |
| H1: Corpus validity | ✅ | Dense Hit@5=0.5446 |
| H2: Timing rerun | ✅ | pypdf=379.4s, liteparse=356.3s, pdf_inspector=346.7s |
| H3: Reranker effect measured | pypdf −0.0179, liteparse −0.0089, pdf_inspector +0.0804 | Reranked Hit@5 lift |
| Non-regression | ✅ | pypdf Cov@20=0.8125, liteparse Cov@20=0.8036 |

**Gate 6C ordering:** Commit the Experiment 14 result artefacts separately. Only then amend ADR-020 or write its successor in a follow-up ADR/OpenSpec. Until then, `pdf_inspector` remains a candidate and the production default is unchanged.

## Parser evidence

All readers had 35 parse-start and 35 parse-end events, with zero parse-error events. The parser-only rerun did not embed or write indexes. Each frozen source PDF has 359 pages in total, measured independently with pypdf. Emitted-document totals are 359 for pypdf, 358 for LiteParse, and 35 for pdf-inspector. LlamaIndex-default `TokenCounter` totals are 339,825, 331,664, and 324,503 respectively. These token counts are corpus-size proxies, not qwen3-embedding tokenisation. `pdf_inspector` had the highest reranked Hit@5 (0.6250) and the shortest approved-rerun ingestion time (346.7s). Parser-only timings are excluded from the timing evidence.

## Cell metrics

| Cell | Coverage@20 | Hit@5 | Hit@10 | MRR@10 | P95 ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| pypdf_off | 0.8125 | 0.5446 | 0.6964 | 0.4537 | 170 |
| pypdf_on | 0.7946 | 0.6161 | 0.7232 | 0.4899 | 1309 |
| liteparse_off | 0.8036 | 0.5536 | 0.6696 | 0.4512 | 3 |
| liteparse_on | 0.7946 | 0.6161 | 0.7500 | 0.5314 | 1290 |
| pdf_inspector_off | 0.8125 | 0.5446 | 0.6696 | 0.4369 | 3 |
| pdf_inspector_on | 0.8036 | 0.6250 | 0.7321 | 0.5282 | 1140 |