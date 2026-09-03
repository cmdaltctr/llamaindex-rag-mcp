# Proposal: accept the LanceDB filter policy exception

## Why

Security finding F1 of `add-grounded-answer-synthesis-3` classifies the
LanceDB filter adapter as CRITICAL because the filter sink is SQL text
assembled from client input, which violates the parameterised-query
invariant stated in that review. On lancedb 0.37.1 literal compliance is
impossible: the engine offers no bind-parameter filter API, and its
expression objects cannot address the struct sub-fields where user
metadata lives (verified live; ADR-046).

The implementation under acceptance, shared unchanged by the
`search_documents` and `answer_documents` tools since the LanceDB
backend landed (ADR-046):

- Field names are validated against a conservative identifier grammar
  and backtick-quoted.
- The operator vocabulary is a fixed internal set.
- Every value is serialised by the engine's own literal builder
  (`lancedb.expr.lit(...).to_sql()`), never by project code.
- Every serialised fragment is verified fail-closed: a closed form per
  value type, and string literals decoded back and compared to the
  original value. Unfaithful output refuses the whole filter. This
  verification is load-bearing, not decorative: the engine demonstrably
  mis-serialises apostrophe runs (collapsing `''` to one apostrophe) and
  backslash-before-apostrophe values.
- Nesting depth, clause count, membership-list length, and serialised
  length are each capped.

Evidence: 129 collected tests across `tests/test_lance_filter_security.py`
(93, including a live-engine round-trip layer where a real table row
whose value IS the payload is matched by an equality filter on that
payload, and only by it) and `tests/test_lance_filter.py` (36). The
installed upstream integration `llama-index-vector-stores-lancedb` 0.5.0
builds the same WHERE strings with raw f-strings and no guards
(`base.py:56`, `:432`, `:458`), so the ecosystem baseline is strictly
weaker than this adapter.

Options recorded in F1: (a) approve a documented exception for this
adapter; (b) drop `metadata_filter` from the answer path only; (c)
schedule a metadata schema redesign (flat columns) as its own change.
The user selected (a) on 2026-09-02. Option (b) removes a capability on
a distinction without a difference, because both tools share the path.
Option (c) is sized at 8 to 10 files and 700 to 1,200 changed lines plus
an index migration, and its benefit is confined to LanceDB because
ChromaDB accepts filter dictionaries directly.

## What Changes

1. **Experiment 21 (small, time-boxed): engine literal-faithfulness
   inventory.** A deterministic offline probe on lancedb 0.37.1 that
   inventories which value classes the engine's literal builder
   mis-serialises, proves `translate_where` refuses exactly those and
   accepts a corpus of ordinary values without false refusals, and
   checks on a live table that refused values never reach the engine
   and accepted values match only their own row. The existing test
   suite proves the adapter's security properties; the experiment adds
   the reproducible engine-behaviour inventory the decision record
   cites.
2. **ADR-058** (`docs/adr/058-lancedb-filter-policy-exception.md`):
   records option (a), the rejected alternatives with sizing, the
   explicit rejection of F1's suggested policy tripwire (it would fail
   by design forever; the fail-closed verification is the standing
   control), the evidence base, and revisit triggers.
3. **Spec delta** on `lancedb-vector-store`: one MODIFIED requirement
   promoting the fail-closed verification and structural bounds to
   normative SHALLs; one ADDED requirement scoping the exception to
   this adapter and mandating migration when a parameterised path
   exists.
4. **Closes the F1 ship gate** in `add-grounded-answer-synthesis-3`:
   `security-review.md` finding status and `risks.md` gate (1) marked
   resolved with pointers to ADR-058 and Experiment 21.
5. **No production code changes.**

## Impact

- Specs: `lancedb-vector-store` (one MODIFIED, one ADDED requirement).
- Docs: ADR-058 and the ADR index.
- Experiments: `experiments/21-lancedb-literal-faithfulness-2026-09-02/`.
- In-flight change: `add-grounded-answer-synthesis-3` gate documents.
- Code: none. Tests: none beyond the experiment probe (the existing
  129-case suite already covers the adapter).
- Residual risk accepted: a future lancedb regression in `lit()` that
  produces output passing the closed-form and round-trip checks while
  meaning something else. No such class is known; the checks are
  re-run by the test suite on every upgrade of the locked dependency.
