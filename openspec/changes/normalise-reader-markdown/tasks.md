# Tasks: Normalise reader Markdown before chunking

**Start gate:** Operator decision 2026-09-25: implementation starts before Experiment 34 closes, because the Experiment 34 review needs normalised output to avoid judging known reader noise. Experiment 34 task 3.3 waits for this change's task 4.5.

## 1. Fixtures and the pure function

- [x] 1.1 Cut small fixtures from the Experiment 34 outputs into `tests/fixtures/reader_output/`: pdf-inspector `<u>` (link, running header, half sentence); worker image-only `<div>`, image-plus-text `<div>` ("Check for updates", chart labels), text-only caption `<div>`, `<table>` with `style`/`border`; one LiteParse page as a no-op control; the worker's `eq01` p11 equation block (Experiment 34 A4) as the maths fixture. Verify: files committed, each under 2 KB, source path noted in a README line.
- [x] 1.2 Write red tests in `tests/test_normalise_reader_text.py` for every scenario in `specs/reader-output-normalisation/spec.md`: formatting tags, image blocks, text-only blocks, bare `<img>`, links, tables, code fences, maths (`align*` with `&` and `<`, inline `$…$`, a `$` inside code), entities, unknown tags, determinism, unclosed `<div>` left alone. Verify: `uv run pytest tests/test_normalise_reader_text.py` fails for the missing module only.
- [x] 1.3 Implement `src/omrg/core/ingestion/normalise.py` (`normalise_reader_text`, `NORMALISER_VERSION = 1`) per design D3, stdlib only, `from __future__ import annotations`, Google-style docstrings. Verify: the 1.2 tests pass; `uv run lint-imports` passes.
- [x] 1.4 Add the no-text-loss property test: for every fixture, the visible characters outside removed image blocks are equal before and after. Verify: the test passes on all fixtures.
- [x] 1.5 Add a version-pin test: a digest of the fixture outputs is pinned beside `NORMALISER_VERSION`, so a rule change without a version bump fails. Verify: changing one rule locally fails the test.

## 2. Setting and call site

- [x] 2.1 Add `normalise_reader_output: bool = True` to `IngestionSettings`. Verify: `INGESTION__NORMALISE_READER_OUTPUT=false` resolves to `False` in a settings test; a flat `NORMALISE_READER_OUTPUT` is not read.
- [x] 2.2 Call the normaliser in `chunk_file_async` right after `read_document`, gated to PDF sources (design D1, D2). Verify: a chunker test with a stub backend shows a `.pdf` normalised, a `.md` with `<div><img></div>` unchanged, and the setting off leaves the `.pdf` raw.
- [x] 2.3 Confirm that the structured (cloud) branch and the metadata-extraction input both see normalised text. Verify: a chunker test on the structured branch asserts the node text has no `<u>`.

## 3. Index identity

- [x] 3.1 Add the `normalisation` block (`enabled`, `version`) to `build_index_identity` and advance `_INDEX_IDENTITY_SCHEMA` to 6. Verify: identity tests for the four scenarios in `specs/async-ingestion/spec.md` pass (version change, toggle, schema-5 source reprocesses once, unchanged inputs skip).
- [x] 3.2 Update any test or fixture that pins schema 5. Verify: `uv run pytest -m "not slow"` passes. 2026-09-25: 3,137 passed, 138 skipped; the clean-base tripwire re-pinned to 3140 (+44 here, +1 for the worker fix `d3460bf`) and then passed.

## 4. Measurement (Experiment 36)

- [x] 4.1 Create `experiments/36-reader-output-normalisation-<date>/` with the s-experiment skill. The protocol reads the Experiment 34 outputs by path. Verify: `protocol.md` committed before the run.
- [x] 4.2 Run the measurement: tags removed per engine and rule, visible-character delta per page, the list of removed image-block texts, and the count of unwrapped text-only blocks. Verify: `output/summary.json` committed; visible-character loss outside image blocks is 0 on every page.
- [x] 4.3 Operator spot-checks the removed image-block texts for real captions. Verify: the verdict is recorded in the experiment report. If a real caption was removed, tighten the rule, bump `NORMALISER_VERSION` and repeat 4.2. 2026-09-25: no caption among the 28 texts (after the worker fix, Experiment 34 A9); the operator chose to keep image-block text. Version 2, re-measured: 215 pages, 0 visible-character deltas with no exclusions (Experiment 36 A2).
- [x] 4.4 Resolve the design open question (`[figure]` marker: yes or no) from 4.2–4.3. Verify: the decision is recorded in the experiment report and in design.md. 2026-09-25: no marker.
- [x] 4.5 Rebuild the Experiment 34 review pages on normalised output (Experiment 34 protocol amendment A7). The experiment scripts call the readers directly, so apply the normaliser in make_review.py when it renders each engine panel. Keep the raw outputs in output/<engine>/ unchanged as evidence. Rebuild review_small.html (--only bd03:1,bd03:2,io06:28,io06:53,eq01:11) and review.html (all 42 pages). Record A7 in the Experiment 34 protocol.md: normaliser version, where it is applied, and which panels changed. Verify: no <u>, <span>, <font> or <center> tag in either review page's rendered text; the raw outputs are byte-identical to before; the operator is told which panels to re-review. 2026-09-25: done (Experiment 34 A7); 8 panels normalised in `review_small.html`, 41 in `review.html`; raw outputs unchanged by hash.

## 5. Documentation and close

- [x] 5.1 Document the setting and the rules in `docs/guides/ingestion.md` and `docs/guides/configuration.md`, and add the variable to `.env.example`. Verify: `grep -r NORMALISE_READER_OUTPUT docs .env.example` finds all three.
- [x] 5.2 Mark TDR-028 Accepted, linking the change and the Experiment 36 evidence. Align its setting name to `normalise_reader_output`. Verify: TDR header and README index row updated.
- [x] 5.3 Run the gates: `uv sync`, `uv run pytest -m "not slow" --cov=omrg` (core ≥95 %), `openspec validate --all --strict`, `./scripts/local_ci.sh`. Verify: all pass locally. 2026-09-25: `./scripts/local_ci.sh` passed (fast suite 3,139 passed); coverage run 91 % overall, `normalise.py` 97 %, `chunker.py` 99 %, `source_state.py` 98 %.
- [ ] 5.4 Commit with a `feat(ingestion):` message whose body names the one-off reprocessing (identity schema 6). Follow the schema 5 precedent (`2342424`, no `BREAKING CHANGE` footer) unless the operator decides otherwise. Ask the operator before pushing or opening the PR. Verify: the operator confirms.
