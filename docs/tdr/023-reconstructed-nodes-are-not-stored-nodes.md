# TDR-023: Reconstructed nodes are not stored nodes — deserialise `_node_content` for payload accounting

**Date:** 2026-09-08
**Status:** Accepted
**Deciders:** Aizat
**Tags:** experiments | lancedb | llama-index | tokenization | embedding-cost
**Extends:** TDR-022

## Context

A second external review round on the exp 25 accounting correction (commit
`6d1ed4a`) found my "corrected" verifier still over-counted:
14,066,499 / 13,780,416 vs the audit's 13,969,694 / 13,622,856
(+0.69% / +1.16%). Root cause analysis:

### Defect 4 — null-valued retained keys render into rebuilt payloads

My verifier rebuilt each row as `TextNode(text=row.text, metadata=stored_metadata)`
and derived excluded keys as `set(metadata) − retained`. But the stored
metadata dict carries **null-valued retained keys** for nodes that never had
them — the LanceDB arrow round-trip materialises absent values as `None`.
LlamaIndex's metadata template renders `None` as a literal `key: None` line:

- `content_type: None` on 19,361 of 32,631 baseline nodes (+~3 tokens each)
- `header_path: None` on all 22,281 candidate nodes (+~4–7 tokens each)

That is the entire unexplained gap — confirmed node-by-node: the first
differing node's payload diff is exactly `+content_type: None`.

### The real nodes were there all along

I initially believed deserialising stored nodes was impossible because the
OMRG LanceDB schema has no `_node_content` **column**
(`id, doc_id, vector, text, metadata`). The adapter injects the serialised
pre-store node into the metadata **dict** under `metadata["_node_content"]`
(and `_node_type`). Deserialising with `TextNode.from_json` recovers the
real metadata, excluded-key sets, and templates — no reconstruction needed.
Counting real nodes reproduces the audit's totals to the token.

### Correction — the adapter replaces newlines

The audit correctly requested counting after the adapter's newline replacement.
The earlier claim that no replacement exists was incorrect. The installed
`llama_index/embeddings/openai/base.py` applies `text.replace("\n", " ")`
in `get_embeddings` (line 170) and `aget_embeddings` (line 194).
`OpenAILikeEmbedding` inherits these sync and async batch paths.
Offline tests exercise the installed adapter with fake clients and capture
normalised request text. Inspect the implementation module and inherited
helpers when checking library behaviour; package re-exports are insufficient.

### Defect 5 — the defective counter still authorised spend

`overnight.sh → token_accounting.py → build_index.py` remained a live
approval path: `--force` re-runs would have read the contaminated
`token_accounting_*.json` files and authorised paid embedding. Two passing
unit tests did not establish that the gate was repaired.

## Decision

1. **Payload accounting deserialises real nodes.**
   `TextNode.from_json(row["metadata"]["_node_content"])` →
   `get_content(metadata_mode=MetadataMode.EMBED)` → tokenise with
   `add_special_tokens=False`. Rebuilding nodes from row text+metadata is
   banned for accounting; it is an approximation that silently renders
   nulls. Implemented in `experiments/25-.../verify_accounting.py`.
2. **The verifier is retrospective only.** It verifies completed builds
   and can never authorise future spend. `build_index.py` preflight now
   hard-refuses paid builds (exit 1, verified) until a corrected pre-spend
   estimator exists. Future estimates must reuse production preparation and
   prove request-text parity offline. This fix adds no ingestion simulator.
3. **Library-behaviour claims are verified in site-packages** and tested
   through inherited adapter paths. Keep `payload_tokens` and
   `max_payload_tokens` for pre-adapter `MetadataMode.EMBED` text. Add
   `request_tokens` and `max_request_tokens` for that text after
   `replace("\n", " ")`. Each maximum is the largest per-node count.

Retrospective exp 25 request-text verdict: 13,521,230 / 13,869,272 =
**0.974906 — PASS** (cap 1.15); max request 2,087 → 1,189.
The pre-adapter EMBED totals remain 13,622,856 / 13,969,694 =
**0.975172 — PASS**; max payload 2,087 → 1,120.
Both use the pinned local tokenizer without special tokens. These counts
do not establish provider billing, retries or historical network traffic.

## Consequences

**Positive**

- Two independent implementations (the audit's and mine) now agree to the
  token; the verdict needs no percentage tolerance.
- The defective approval path is dead: `build_index.py --force` exits 1
  with an actionable message pointing at the retrospective verifier.
- A reusable pattern for any future token audit of llama-index-backed
  LanceDB stores.

**Negative**

- Two review rounds were needed to reach ground truth; my first correction
  traded one approximation for another instead of questioning the
  reconstruction premise.

### Verification evidence (2026-09-08)

- Seven focused tests pass across `tests/test_exp25_accounting_contracts.py`
  and `tests/test_exp25_request_accounting.py`.
- Before the fix, both verifier regressions failed because request counts
  were absent. Removing adapter normalisation in memory makes both adapter
  tests fail; installed package files remain unchanged.
- Offline recounts reconcile all 10,024 files per index with zero mismatches.
  Network connections were blocked. The before/after inventory of 60,153
  dataset files had identical paths, sizes and modification times.
- No embedding requests or rebuilds occurred. The paid-build refusal remains
  active.

**Neutral**

- Billing/retry-level verification remains unverified (local counting of
  deserialised EMBED text and normalised request text), unchanged from TDR-022.

## Alternatives considered

| Option | Rejected because |
| --- | --- |
| Accept the audit's totals without reproducing them | Trust without reproduction; the deserialised count makes independent verification cheap |
| Patch the reconstruction to drop `None`-valued keys | Fixes one symptom; template/exclusion drift remains possible — deserialisation removes the class of error |
| Keep the pre-spend gate reading the deprecated counter | A contaminated counter must never authorise spend (TDR-022 defect 2) |
| Rewrite TDR-022's original decision | Preserve the historical failure; mark superseded guidance and link to this correction |

## How to recognise / handle this again

- Reconstructed payload totals exceed a trusted reference by a uniform
  ~3–7 tokens per node → dump the first differing payload; look for
  literal `: None` lines.
- Any accounting over a llama-index vector store → first check
  `metadata["_node_content"]` exists; if it does, deserialise, never
  rebuild.
- An external instruction cites library behaviour ("the adapter replaces
  newlines") → inspect the installed implementation and inherited helpers:
  `python -c "import inspect; from llama_index.embeddings.openai.base import get_embeddings, aget_embeddings; print(inspect.getsource(get_embeddings)); print(inspect.getsource(aget_embeddings))"`
- Confirm a gate is actually disabled by exercising it:
  `build_index.py --force` must exit 1 with the refusal message.

## Revisit triggers

- The LanceDB adapter schema changes (e.g. `_node_content` dropped or
  moved to a column).
- A llama_index upgrade changes metadata rendering of null values or the
  embedding adapter's text transformation.
- A corrected pre-spend estimator is built → re-enable a real approval
  path and supersede the refusal.

## References

- Commit `a7ec7a2` — deserialised accounting, disabled approval path
- Commit `6d1ed4a` — first correction (the one this TDR corrects)
- TDR-022 — the three original traps; this record extends it
- `experiments/25-token-chunking-ablation-2026-09-08/{verify_accounting.py,build_index.py,protocol.md}`
- External model review round 2, 2026-09-08 (relayed by the operator)

## Follow-up (2026-09-09): refusal restored; estimate-gate scaffold retained unverified

This follow-up was corrected the same day after a blocking security audit.
An interim version had replaced the blanket refusal with an approval-gated
path; the audit found that a self-consistent, correctly digested estimate
document can be handcrafted without genuine production preparation, so
document validation alone cannot authorise spending. `build_index.py` again
refuses every rebuild unconditionally — before estimate/approval documents
are read and before runtime setup is imported — naming the missing
estimator and parity verification. The historical marker still allows a
clean skip (marker present, no `--force`).

### What exists now

- `experiments/25-.../build_index.py` (90 lines): marker skip plus
  unconditional rebuild refusal. Estimate/approval CLI arguments are
  accepted but never read while rebuilds are blocked.
- `experiments/25-.../estimate_gate.py` (438 lines): explicitly UNVERIFIED
  scaffold, unit-tested offline, for a future verified estimator:
  - identity digests (corpus content, fixed settings, builder code,
    `src/omrg/` runtime-source tree, `uv.lock`, tokenizer model+revision);
  - estimate/approval document validation bound to the estimate digest,
    a destination outside every preserved root (both-direction path
    containment), dated pricing with a baseline/candidate comparison,
    tokenizer-fallback invalidation, and an independent
    `max_request_tokens` cap enforced as the lower of the
    currency-derived and token ceilings;
  - `BudgetStopEmbedder` (per-batch request-token ceiling at the single
    production embedding choke point, `get_text_embedding_batch`) and
    `_pack_failed` (ingestion results report failures as statuses, not
    exceptions).
- `build_index.main` never calls the scaffold. Activating an approval
  path requires: the installed production adapter
  (`llama-index-embeddings-openai-like`, optional extra `openrouter`),
  a production-preparation estimator with proven request-text parity
  against that installed adapter (repair tasks 3.2/3.3), and an explicit
  operator decision recorded through the repair change.

### Estimates and billing

The scaffold's display contract shows identified baseline/candidate
request-token counts, percentage difference, and approximate cost from
operator-provided or verified dated pricing, and states that provider
retries and billing can differ — an offline count, never a provider
billing forecast. The frozen 1.15× extra-token threshold judges the
measured result only; these are contract shapes, not a live path.

### Test evidence

- `tests/test_exp25_build_authorisation.py` (251 lines): rebuild-refusal
  and marker-reuse contracts with fake transports as import traps. The
  operator-requested regression feeds a fully valid-looking handcrafted
  estimate (correct digests, live identity, dated pricing) plus a
  matching approval — documents proven to satisfy the scaffold gate —
  and requires exit 1 with zero runtime/embedding requests. Fail-before:
  against the interim approval-gated code this regression FAILED (the
  build proceeded); after the refusal restore it passes. An independent
  read-only audit confirmed the refusal (2026-09-09) and suggested, for
  a future strengthening, explicit file-read traps alongside the import
  traps.
- `tests/test_exp25_estimate_gate_scaffold.py` (382 lines): scaffold
  contracts — tampered digest, changed corpus/lock/runtime-source
  identity, missing pricing date, missing baseline comparison,
  tokenizer fallback, approval digest/destination mismatch, six protected
  destinations, token-cap binding, budget-stop wrapper, pack-failure
  detection, and the valid-document pass case that keeps the handcrafted
  regression meaningful.
- Combined: `uv run --no-sync pytest tests/test_exp25_build_authorisation.py
  tests/test_exp25_estimate_gate_scaffold.py tests/test_exp25_request_accounting.py
  tests/test_exp25_accounting_contracts.py -q` → 32 passed, 2 skipped
  (adapter-parity skips, see below). The pre-existing
  `test_paid_build_still_refuses` passes.

### Unresolved conditions (no operator acceptance implied)

- The offline estimator does not exist; installing the adapter requires
  operator approval (`uv sync --extra openrouter`). Until then no
  estimate document is legitimate and every rebuild refuses.
- The sync and async `test_installed_adapter_normalises_request_text`
  cases skip for the missing dependency; request-text parity (task 3.2)
  is unverified.
- Unresolved risk items awaiting operator decision, NOT accepted:
  preserved DATA roots derive from `Path.home()` (a crafted `HOME` moves
  them); corpus/destination time-of-check-to-time-of-use windows remain;
  lock-wide dependency advisories (chromadb, nltk) await the change-wide
  security reassessment.
- `estimate_gate.py` is scaffold only; any future activation needs the
  verified estimator, parity proof and an explicit operator decision.

### Entry points

`overnight.sh` exits 1 with the blocked status; it no longer runs
`token_accounting.py` for any purpose. `verify_accounting.py` remains
retrospective verification, separate from any approval path.
