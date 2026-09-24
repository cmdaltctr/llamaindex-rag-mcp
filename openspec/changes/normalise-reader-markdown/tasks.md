# Tasks: Normalise reader Markdown before chunking

**Start gate:** do not start until Experiment 34 closes (its tasks 3.3 and 4.1). Operator decision 2026-09-24: implement on this branch after the experiment.

## 1. Fixtures and the pure function

- [ ] 1.1 Cut small fixtures from the Experiment 34 outputs into `tests/fixtures/reader_output/`: pdf-inspector `<u>` (link, running header, half sentence); worker image-only `<div>`, image-plus-text `<div>` ("Check for updates", chart labels), text-only caption `<div>`, `<table>` with `style`/`border`; one LiteParse page as a no-op control. Verify: files committed, each under 2 KB, source path noted in a README line.
- [ ] 1.2 Write red tests in `tests/test_normalise_reader_text.py` for every scenario in `specs/reader-output-normalisation/spec.md`: formatting tags, image blocks, text-only blocks, bare `<img>`, links, tables, code fences, entities, unknown tags, determinism, unclosed `<div>` left alone. Verify: `uv run pytest tests/test_normalise_reader_text.py` fails for the missing module only.
- [ ] 1.3 Implement `src/omrg/core/ingestion/normalise.py` (`normalise_reader_text`, `NORMALISER_VERSION = 1`) per design D3, stdlib only, `from __future__ import annotations`, Google-style docstrings. Verify: the 1.2 tests pass; `uv run lint-imports` passes.
- [ ] 1.4 Add the no-text-loss property test: for every fixture, the visible characters outside removed image blocks are equal before and after. Verify: the test passes on all fixtures.
- [ ] 1.5 Add a version-pin test: a digest of the fixture outputs is pinned beside `NORMALISER_VERSION`, so a rule change without a version bump fails. Verify: changing one rule locally fails the test.

## 2. Setting and call site

- [ ] 2.1 Add `normalise_reader_output: bool = True` to `IngestionSettings`. Verify: `INGESTION__NORMALISE_READER_OUTPUT=false` resolves to `False` in a settings test; a flat `NORMALISE_READER_OUTPUT` is not read.
- [ ] 2.2 Call the normaliser in `chunk_file_async` right after `read_document`, gated to PDF sources (design D1, D2). Verify: a chunker test with a stub backend shows a `.pdf` normalised, a `.md` with `<div><img></div>` unchanged, and the setting off leaves the `.pdf` raw.
- [ ] 2.3 Confirm that the structured (cloud) branch and the metadata-extraction input both see normalised text. Verify: a chunker test on the structured branch asserts the node text has no `<u>`.

## 3. Index identity

- [ ] 3.1 Add the `normalisation` block (`enabled`, `version`) to `build_index_identity` and advance `_INDEX_IDENTITY_SCHEMA` to 6. Verify: identity tests for the four scenarios in `specs/async-ingestion/spec.md` pass (version change, toggle, schema-5 source reprocesses once, unchanged inputs skip).
- [ ] 3.2 Update any test or fixture that pins schema 5. Verify: `uv run pytest -m "not slow"` passes.

## 4. Measurement (Experiment 36)

- [ ] 4.1 Create `experiments/36-reader-output-normalisation-<date>/` with the s-experiment skill. The protocol reads the Experiment 34 outputs by path. Verify: `protocol.md` committed before the run.
- [ ] 4.2 Run the measurement: tags removed per engine and rule, visible-character delta per page, the list of removed image-block texts, and the count of unwrapped text-only blocks. Verify: `output/summary.json` committed; visible-character loss outside image blocks is 0 on every page.
- [ ] 4.3 Operator spot-checks the removed image-block texts for real captions. Verify: the verdict is recorded in the experiment report. If a real caption was removed, tighten the rule, bump `NORMALISER_VERSION` and repeat 4.2.
- [ ] 4.4 Resolve the design open question (`[figure]` marker: yes or no) from 4.2–4.3. Verify: the decision is recorded in the experiment report and in design.md.

## 5. Documentation and close

- [ ] 5.1 Document the setting and the rules in `docs/guides/ingestion.md` and `docs/guides/configuration.md`, and add the variable to `.env.example`. Verify: `grep -r NORMALISE_READER_OUTPUT docs .env.example` finds all three.
- [ ] 5.2 Mark TDR-028 Accepted, linking the change and the Experiment 36 evidence. Align its setting name to `normalise_reader_output`. Verify: TDR header and README index row updated.
- [ ] 5.3 Run the gates: `uv sync`, `uv run pytest -m "not slow" --cov=omrg` (core ≥95 %), `openspec validate --all --strict`, `./scripts/local_ci.sh`. Verify: all pass locally.
- [ ] 5.4 Commit with a `feat(ingestion):` message whose body names the one-off reprocessing (identity schema 6). Follow the schema 5 precedent (`2342424`, no `BREAKING CHANGE` footer) unless the operator decides otherwise. Ask the operator before pushing or opening the PR. Verify: the operator confirms.
