# ADR-058: LanceDB Filter Policy Exception

**Date:** 2026-09-02
**Status:** Accepted
**Deciders:** Dr Muhammad Aizat Bin Md Hawari

## Context

The parameterised-query invariant holds that client input must never
become SQL text. A security review found one path that cannot yet obey
it. Three forces shaped this decision:

1. **lancedb 0.37.x has no bind-parameter filter API.** Expression
   objects cannot address struct sub-fields. This was verified live and
   recorded in ADR-046. The engine accepts only WHERE strings.
2. **The upstream vector store builds WHERE strings with raw f-strings
   and no guards.** `llama-index-vector-stores-lancedb` 0.5.0 assembles
   SQL text from client input at `base.py:56`, `:432`, and `:458`. The
   filter sink is SQL text, not a parameterised statement.
3. **Security finding F1 classified the filter adapter as CRITICAL.**
   The review of `add-grounded-answer-synthesis-3` named the LanceDB
   filter adapter as the single CRITICAL finding. The adapter violates
   the parameterised-query invariant because it turns client input into
   SQL text.

## Decision

1. **Approve a documented exception to the parameterised-query
   invariant (F1 option a).** The exception is scoped to
   `core/vectordb/lance_filter.py` on both the search and answer paths.
   The adapter is the sole sanctioned exception.

2. **Serialise every value through engine-owned quoting.** The adapter
   passes each value through `lancedb.expr.lit(...).to_sql()`. The
   engine owns the quoting. The adapter does not construct SQL literals
   by hand.

3. **Validate field names against a conservative identifier grammar.**
   The adapter permits only field names that match a fixed grammar. It
   rejects all other names.

4. **Use a fixed operator vocabulary.** The adapter accepts only a
   closed set of operators. Unknown operators are rejected.

5. **Verify every serialised fragment fail-closed against the original
   value.** After serialisation, the adapter compares the SQL fragment
   back to the source value. If the comparison fails, the adapter
   raises and the query does not run.

6. **Enforce structural bounds.** The adapter caps nesting depth at 10,
   clause count at 50, membership-list length at 100, and serialised
   length at 8192 characters. These bounds prevent resource exhaustion.

## Consequences

### Positive

- The filter adapter is the sole sanctioned exception. The scope is
  explicit and narrow.
- Fail-closed verification catches engine regressions on every test
  run.
- Structural bounds prevent resource exhaustion.

### Negative

- The adapter remains string-based SQL, not parameterised.
- A future lancedb regression in `lit()` that produces output passing
  the closed-form and round-trip checks while meaning something else is
  a residual risk. No such class is known.

### Neutral

- The exception is engine-version-specific. It lapses when a
  parameterised path exists.

## Alternatives Considered

| Option | Rejected because |
| --- | --- |
| (b) Drop `metadata_filter` from the answer path only | Both `search_documents` and `answer_documents` share the same path. Dropping the filter on one is a distinction without a difference. |
| (c) Schedule a metadata schema redesign with flat columns | Sized at 8 to 10 files and 700 to 1,200 changed lines, plus an index migration. The benefit is confined to LanceDB because ChromaDB accepts filter dictionaries directly. |
| F1's suggested policy tripwire that fails while `translate_where` returns executable SQL text | Under this decision it would fail by design forever. The fail-closed verification is the standing control. |

## Evidence Base

- Experiment 21 results
  (`experiments/21-lancedb-literal-faithfulness-2026-09-02/`).
- The existing 129 collected tests across
  `tests/test_lance_filter_security.py` and `tests/test_lance_filter.py`.
- The new absent-field and scalar-faithfulness regression tests in
  `tests/test_lance_filter_security.py`, including the live-engine
  round-trip layer.

## Revisit Triggers

- lancedb ships bind parameters or struct-capable expression objects.
- A new mis-serialisation class bypasses the closed-form checks.

## References

- ADR-046 (LanceDB vector store backend)
- OpenSpec change: `openspec/changes/accept-lancedb-filter-policy-exception/`
- Security finding F1: `openspec/changes/archive/2026-09-03-add-grounded-answer-synthesis-3/security-review.md`
- Experiment 21: `experiments/21-lancedb-literal-faithfulness-2026-09-02/`
- Implementation: `src/rag_mcp/core/vectordb/lance_filter.py`
- Tests: `tests/test_lance_filter_security.py`, `tests/test_lance_filter.py`
