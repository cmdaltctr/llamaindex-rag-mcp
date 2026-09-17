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

## Run record (task 3.2, 2026-09-16)

Environment and transport:

- Command: `.venv/bin/python scripts/magika_label_smoke.py --json
  <16 frozen paths>` run from the repository root with `.venv/bin`
  on `PATH` (the injected binary name `magika` resolves through
  `shutil.which`).
- Package: `magika==1.0.3` (importlib metadata; pyproject pin and
  lock entry identical). The bundled CLI core self-reports
  `magika 1.1.0 standard_v3_3` — the Rust core shipped inside the
  1.0.3 wheel, recorded for provenance.
- Executable: `<repo>/.venv/bin/magika` (base dependency of the
  venv; no system Magika installed).

Acceptance corpus result: **exit 0 — complete, non-empty all-match.**

- Coverage: 16/16 frozen paths compared; path sets identical (no
  missing, extra, or duplicate paths).
- Labels: 0 of 16 would change. Observed pairs: `code/python` (4),
  `document/markdown` (4, via the text/markdown alias),
  `document/text` (3, via the text/txt alias), `document/pdf` (5).
- Elapsed: 1.00 s for the whole invocation over 16 explicit files
  (16 CLI model startups included; this is the measured whole-run
  cost, not isolated per-file detection).

Diagnostics (each run separately, same tool and detector):

| Probe | Exit | Observed | Recorded limitation |
|-------|------|----------|---------------------|
| misnamed-python.txt | 1 (non-zero) | suffix `document/text`, Magika `code/python` | Designed: content detection wins on misnamed files; the identity shift is reported before any re-ingest. |
| tiny-source.py | 1 (non-zero) | suffix `code/python`, Magika `document/text` (raw `text/txt`, low confidence on 4 bytes) | Short Python can lose its code label; never repaired by padding, retry, or suffix override. |
| tiny-source.txt | 0 | `document/text` both scanners | Low-confidence generic text still aliases to the suffix label; recorded as a match, not a repair. |

Gate incidents (recorded before the pass, corpus untouched):

1. First invocation exited 2: the direct `python3` call had no venv
   on `PATH`, so the binary check failed. Re-ran with the documented
   transport.
2. Second invocation exited 2 on `duplicate=['.']`: the smoke tool
   keyed every direct-file entry as `.` — a tool defect fixed in
   `00d6d46` (re-key to the operator path) with regression
   `test_smoke_comparison_supports_multiple_explicit_file_paths`.
   No acceptance labels were compared or recorded before that fix.

No ingest, store, embedding, or collection operation ran during the
gate. Task 5.1 (undo) was not triggered.

## Task 4.4 — no collection, embedding, or store change

`git diff --name-only adad033..HEAD` contains no path under the
vector stores, embedding, or collection code (verified 2026-09-16;
grep for `vectordb|store|embed|collection` over the full change set
returns nothing). The only production modules touched are
`integrations/magika.py` (parser and boundary), the
`detect_file_types` fallback catch in `core/codebase/codebase_map.py`,
and the binary-skip counter in `core/ingestion/pipeline.py`.
