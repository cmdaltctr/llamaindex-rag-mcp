# Experiment 14 Results: LiteParse Promotion on Qasper

**Recommendation:** Quality gates pass. H2 timing is provisional because the campaign ran under ambient machine load. Do not promote a PDF reader until a quiet-machine timing rerun completes. See [the deviation record](DEVIATION-2026-08-24-ambient-load.md).

## Gate summary

| Gate | Result | Detail |
| --- | :--: | --- |
| H1: Corpus validity | ✅ | Dense Hit@5=0.5446 |
| H2: Speed | ⚠️ Provisional | pypdf=384.1s, liteparse=371.0s, pdf_inspector=352.6s; ambient-load timing requires a quiet-machine rerun |
| H3: Reranker benefit | ✅ | pypdf lift=-0.0179, liteparse lift=-0.0089 |
| Non-regression | ✅ | pypdf Cov@20=0.8125, liteparse Cov@20=0.8036 |

## Cell metrics

| Cell | Coverage@20 | Hit@5 | Hit@10 | MRR@10 | P95 ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| pypdf_off | 0.8125 | 0.5446 | 0.6964 | 0.4537 | 170 |
| pypdf_on | 0.7946 | 0.6161 | 0.7232 | 0.4899 | 1309 |
| liteparse_off | 0.8036 | 0.5536 | 0.6696 | 0.4512 | 3 |
| liteparse_on | 0.7946 | 0.6161 | 0.7500 | 0.5314 | 1290 |
| pdf_inspector_off | 0.8125 | 0.5446 | 0.6696 | 0.4369 | 3 |
| pdf_inspector_on | 0.8036 | 0.6250 | 0.7321 | 0.5282 | 1140 |