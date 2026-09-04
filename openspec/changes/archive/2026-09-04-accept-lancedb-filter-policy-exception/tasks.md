# Tasks: accept-lancedb-filter-policy-exception

## 1. Harden the translator and add regression tests

- [x] 1.1 Add failing tests proving that schema-absent fields do not
  bypass field-name validation, membership operand validation, or the
  membership-list limit.
- [x] 1.2 Move field-name and membership validation before the
  schema-absent-field fold in `core/vectordb/lance_filter.py`. Confirm
  the new tests pass without changing ChromaDB missing-field semantics.
- [x] 1.3 Add failing tests that replace the engine builder's boolean,
  integer, float, Decimal, date, and datetime output with a different
  valid-looking value. Each test must prove that the translator refuses
  the mismatched value.
- [x] 1.4 Parse each supported scalar fragment and compare it with the
  original value using exact or canonical type semantics. Confirm all
  scalar-faithfulness tests pass.

## 2. Evidence: Experiment 21 (engine literal-faithfulness inventory)

- [x] 2.1 Create `experiments/21-lancedb-literal-faithfulness-2026-09-02/`
  from `experiments/EXP_TEMPLATE.md`. Write `protocol.md` stating the
  falsifiable prediction: on lancedb 0.37.1 the engine's literal builder
  mis-serialises exactly the two known value classes (apostrophe runs;
  backslash directly before an apostrophe) and no others, and
  `translate_where` refuses those two while accepting every ordinary
  value. Record scope: deterministic, offline, no model calls, seconds
  to run.
- [x] 2.2 Write the probe script: (i) a hostile corpus sweep through
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
- [x] 2.3 Run the probe. Write `results.md` from
  `experiments/EXP_RESULT_TEMPLATE.md` with the inventory table (value
  class, engine output, faithful yes/no, translator verdict) and the
  verdict against the prediction.
- [x] 2.4 Update the `experiments/EXP_README.md` index with the
  Experiment 21 row (PLANNED to DONE).

## 3. Decision record: ADR-058

- [x] 3.1 Write `docs/adr/058-lancedb-filter-policy-exception.md`:
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
  standing control. Evidence base: Experiment 21 results, the existing
  129 collected tests, and the new absent-field and scalar-faithfulness
  regression tests in `tests/test_lance_filter_security.py` and
  `tests/test_lance_filter.py`, including the live-engine round-trip
  layer. Revisit triggers: lancedb ships bind parameters or
  struct-capable expression objects; or a new mis-serialisation class
  bypasses the closed-form checks.
- [x] 3.2 Add ADR-058 to the `docs/adr/ADR_README.md` index.

## 4. Spec delta

- [x] 4.1 Land the delta in this change's
  `specs/lancedb-vector-store/spec.md`: one MODIFIED requirement
  ("translate ChromaDB where clauses safely") adding the fail-closed
  verification and structural bounds as normative SHALLs with three new
  scenarios; one ADDED requirement scoping the exception to this
  adapter and mandating migration when a parameterised path exists.
- [x] 4.2 Run `openspec validate accept-lancedb-filter-policy-exception
  --strict` and fix any baseline-scenario drift it reports.

## 5. Close the F1 ship gate in archived grounded-answer synthesis

- [x] 5.1 In `openspec/changes/archive/
  2026-09-03-add-grounded-answer-synthesis-3/security-review.md`, set F1
  status to approved option (a) on 2026-09-02 with pointers to ADR-058
  and Experiment 21. Update the
  "Most important reason" summary, the open-questions line 35 entry,
  and the line 229 conclusion to match.
- [x] 5.2 In `openspec/changes/archive/
  2026-09-03-add-grounded-answer-synthesis-3/risks.md`, mark ship gate
  (1) resolved with the same pointers.

## 6. Verification

- [x] 6.1 Run `uv run pytest tests/test_lance_filter_security.py
  tests/test_lance_filter.py -q`. Record the passing count and confirm
  that the production diff is limited to the planned translator
  hardening.
- [x] 6.2 Run `openspec validate --all --strict`.
