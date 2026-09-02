# Tasks: accept-lancedb-filter-policy-exception

## 1. Evidence: Experiment 21 (engine literal-faithfulness inventory)

- [ ] 1.1 Create `experiments/21-lancedb-literal-faithfulness-2026-09-02/`
  from `experiments/EXP_TEMPLATE.md`. Write `protocol.md` stating the
  falsifiable prediction: on lancedb 0.37.1 the engine's literal builder
  mis-serialises exactly the two known value classes (apostrophe runs;
  backslash directly before an apostrophe) and no others, and
  `translate_where` refuses those two while accepting every ordinary
  value. Record scope: deterministic, offline, no model calls, seconds
  to run.
- [ ] 1.2 Write the probe script: (i) a hostile corpus sweep through
  `lancedb.expr.lit(...).to_sql()` recording the raw serialisation of
  every value class (apostrophe runs, backslash-apostrophe, double
  quotes, unicode, control characters, NUL, newlines, long strings,
  numeric and datetime edge cases); (ii) an ordinary-value corpus of a
  few hundred realistic metadata values (file paths, ISO dates, tags,
  numerics) asserted to pass `translate_where` with zero false
  refusals; (iii) a live-table check that every refused value raises
  before any SQL reaches the engine, and every accepted value's
  equality filter matches only its own row. Use `print(..., flush=True)`
  and atomic output writes (`.tmp` then rename) per experiment
  discipline.
- [ ] 1.3 Run the probe. Write `results.md` from
  `experiments/EXP_RESULT_TEMPLATE.md` with the inventory table (value
  class, engine output, faithful yes/no, translator verdict) and the
  verdict against the prediction.
- [ ] 1.4 Update the `experiments/EXP_README.md` index with the
  Experiment 21 row (PLANNED to DONE).

## 2. Decision record: ADR-058

- [ ] 2.1 Write `docs/adr/058-lancedb-filter-policy-exception.md`:
  Status Accepted; decider Dr Muhammad Aizat Bin Md Hawari; decision
  date 2026-09-02. Context: lancedb 0.37.x has no bind-parameter filter
  API and expression objects cannot address struct sub-fields (verified
  live; ADR-046); upstream `llama-index-vector-stores-lancedb` 0.5.0
  builds WHERE strings with raw f-strings and no guards (`base.py:56`,
  `:432`, `:458`). Decision: option (a) of F1, scoped to
  `core/vectordb/lance_filter.py` on both the search and answer paths.
  Rejected alternatives: (b) drops a working capability on a false
  distinction (both tools share the path); (c) sized 8 to 10 files,
  700 to 1,200 changed lines, index migration, benefit confined to
  LanceDB because ChromaDB accepts filter dictionaries directly.
  Explicitly reject F1's suggested policy tripwire that fails while
  `translate_where` returns executable SQL text: under this decision it
  would fail by design forever, and the fail-closed verification is the
  standing control. Evidence base: Experiment 21 results plus the 129
  collected tests in `tests/test_lance_filter_security.py` and
  `tests/test_lance_filter.py` including the live-engine round-trip
  layer. Revisit triggers: lancedb ships bind parameters or
  struct-capable expression objects; or a new mis-serialisation class
  bypasses the closed-form checks.
- [ ] 2.2 Add ADR-058 to the `docs/adr/ADR_README.md` index.

## 3. Spec delta

- [ ] 3.1 Land the delta in this change's
  `specs/lancedb-vector-store/spec.md`: one MODIFIED requirement
  ("translate ChromaDB where clauses safely") adding the fail-closed
  verification and structural bounds as normative SHALLs with two new
  scenarios; one ADDED requirement scoping the exception to this
  adapter and mandating migration when a parameterised path exists.
- [ ] 3.2 Run `openspec validate accept-lancedb-filter-policy-exception
  --strict` and fix any baseline-scenario drift it reports.

## 4. Close the F1 ship gate in add-grounded-answer-synthesis-3

- [ ] 4.1 In `openspec/changes/add-grounded-answer-synthesis-3/
  security-review.md`: set F1 status to approved option (a) on
  2026-09-02 with pointers to ADR-058 and Experiment 21; update the
  "Most important reason" summary, the open-questions line 35 entry,
  and the line 229 conclusion to match.
- [ ] 4.2 In `openspec/changes/add-grounded-answer-synthesis-3/
  risks.md`: mark ship gate (1) resolved with the same pointers.

## 5. Verification

- [ ] 5.1 Run `uv run pytest tests/test_lance_filter_security.py
  tests/test_lance_filter.py -q` (129 passing expected) and confirm
  with `git status` that no file under `src/` changed.
- [ ] 5.2 Run `openspec validate --all --strict`.
