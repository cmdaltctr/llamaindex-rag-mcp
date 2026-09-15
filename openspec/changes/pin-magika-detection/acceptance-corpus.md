# Frozen acceptance corpus and predesignated diagnostics

Task 3.1 record for `pin-magika-detection`. Both path sets below were
frozen and committed BEFORE any smoke output existed. No acceptance
file has been moved or excluded after seeing output. Detection is
read-only; no ingest, store, or embedding occurs.

Selection criteria (objective, fixed before the run):

- PDF: real academic corpus PDFs plus text/table fixture PDFs.
- Python: core modules of this repository, including the modules this
  change touches.
- Markdown: repository entry points and the main guides.
- TXT: real experiment corpus prose files (>= 160 bytes).
- Acceptance corpus holds only the four representative types. Edge
  cases (misnamed, tiny) are diagnostics and never acceptance files.

## Acceptance corpus (16 paths, all-match gate)

| # | Type | Path (repo-relative) | Bytes |
|---|------|----------------------|-------|
| 1 | pdf | experiments/2-embedding-model-comparison-2026-05-19/corpus/Ghazali-Mustasfa.pdf | 803353 |
| 2 | pdf | experiments/2-embedding-model-comparison-2026-05-19/corpus/Kalai et al. - 2025 - Why Language Models Hallucinate.pdf | 815337 |
| 3 | pdf | experiments/2-embedding-model-comparison-2026-05-19/corpus/Popat and Starkey - 2019 - Learning to code or coding to learn A systematic review.pdf | 520287 |
| 4 | pdf | tests/fixtures/pdf_baseline/calibration/cal_clean_text.pdf | 1071 |
| 5 | pdf | tests/fixtures/pdf_baseline/calibration/cal_table_text.pdf | 946 |
| 6 | py | src/omrg/compose.py | 21924 |
| 7 | py | src/omrg/core/ingestion/pipeline.py | 20862 |
| 8 | py | src/omrg/integrations/magika.py | 8501 |
| 9 | py | src/omrg/core/codebase/codebase_map.py | 17060 |
| 10 | md | README.md | 11498 |
| 11 | md | AGENTS.md | 19143 |
| 12 | md | docs/guides/architecture.md | 40340 |
| 13 | md | docs/guides/ingestion.md | 33522 |
| 14 | txt | experiments/20-citation-faithfulness-2026-09-02/corpus/source-01-aurora.txt | 178 |
| 15 | txt | experiments/20-citation-faithfulness-2026-09-02/corpus/source-02-birch.txt | 168 |
| 16 | txt | experiments/19-lancedb-lifecycle-qualification-2026-08-21/fixtures/corpus_replacement/bravo_harbour.txt | 718 |

## Predesignated diagnostics (expected non-zero, recorded as limitations)

Created before any smoke output; absolute paths under the session
diagnostics directory:

| Probe | Path | Content (sha256) | Expected outcome |
|-------|------|------------------|------------------|
| Misnamed Python | diagnostics/misnamed-python.txt | 2f6d0a931df509cd3961d9c3476a2ad261615c7740f5f5c8d0dc89f87a0a9107 | Suffix says `document/text`, Magika says `code/python`; mismatch exits non-zero. Recorded as a designed limitation, never repaired. |
| Tiny Python | diagnostics/tiny-source.py | 98752ee28d5484bdc2814fb70adb6a0b2fb31f6a9b8ee7ae81fd2fc9cf300b3b | Short or low-confidence Python can return `text/txt`; any mismatch exits non-zero and is recorded. |
| Tiny text | diagnostics/tiny-source.txt | dc51b8c96c2d745df3bd5590d990230a482fd247123599548e0632fdbf97fc22 | Low-confidence generic text; any mismatch exits non-zero and is recorded. |

Tiny probes contain 4 bytes (`x=1\n` / `ok\n`); the misnamed probe
holds 469 bytes of substantial valid Python. Diagnostics run
separately from the acceptance corpus and never gate it.

## Run record (filled after task 3.2)

- Command, executable, package/pin, elapsed detection, coverage,
  counts, mismatches, and diagnostic limitations live in the task 3.2
  evidence appended below after the gate runs.
