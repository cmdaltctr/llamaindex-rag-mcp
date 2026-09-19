# Tasks: LiteParse reading order

**Progress 2026-09-18:** 11 of 11 done. Implemented and measured; the evidence
gate passed on all four conditions (multi-column reading order 0.5309 → 0.9613,
both guard pages unchanged, no recall change, no regression on any page).
`openspec validate --all --strict` (57 passed) and `./scripts/local_ci.sh`
(`== local CI passed ==`) are green at `f24b593`. PR #96 carries this change
to `v3`.

## 1. Tests first

- [x] 1.1 Add adapter tests with synthetic text items: a two-column page joins left column then right; a single-column page keeps library order; a row-structured (table) page keeps library order; a page with a full-width running head over two columns still classifies `multi_column`; reordering preserves the multiset of item texts.
- [x] 1.2 Add a metadata test: a reordered page carries `column="multi_column"`; an unreordered page keeps `single`, `left` or `right`.
- [x] 1.3 Confirm the two-column and metadata tests fail on the current adapter.

## 2. Implement

- [x] 2.1 Add the layout classifier to `integrations/pdf/liteparse.py` as a pure function over a page's text items, returning the class and the gutter centre, with the thresholds from design decision 2.
- [x] 2.2 Use the classification when joining page text, and set `column="multi_column"` on a reordered page.
- [x] 2.3 Run the reader tests, then the fast suite with coverage. Reader tests green (8); the full fast suite with coverage green (the clean-base tripwire surfaced once, re-baselined 2941 → 2948 for the 7 new tests, and the suite stayed green through every later commit on this branch).

## 3. Evidence

- [x] 3.1 Write the measurement script in the Experiment 33 worktree, loading this checkout through `--code-root` the way `route.py` does; run `freeze.py --check` first.
- [x] 3.2 Measure the four evidence-gate conditions and commit the script and its `output/*.json` in the Experiment 33 worktree.
- [x] 3.3 Replace the prototype numbers in `design.md` with the measured ones.

## 4. Close

- [x] 4.1 Run `openspec validate --all --strict` and `./scripts/local_ci.sh`. Green at `f24b593`: 57 OpenSpec items passed, local CI passed end to end (ruff, format, import-linter, OpenSpec, OpenAPI, torch-free, fast suite, advisory pyright).
- [x] 4.2 Include this change in the branch's PR to `v3`. PR #96, opened 2026-09-18.
