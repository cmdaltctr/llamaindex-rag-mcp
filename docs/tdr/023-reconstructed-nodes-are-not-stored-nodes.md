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

### The newline-replacement myth

The audit also instructed counting "after the adapter's newline
replacement". No such replacement exists in the installed
`llama_index.embeddings.openai*` (verified at file level in
site-packages). Claims about library behaviour must be checked against the
**installed** code, not documentation folklore or model memory.

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
   estimator exists — the TDR-022 pattern: production preparation +
   in-memory store + network-blocked request recorder.
3. **Library-behaviour claims are verified in site-packages**, not
   assumed from memory or external review. The installed adapter applies
   no newline transformation; "after normalisation" totals are
   hypothetical and do not describe what the API received.

Definitive exp 25 cost verdict (real nodes): 13,622,856 / 13,969,694 =
**0.975 — PASS** (cap 1.15); max payload 2,087 → 1,120.

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

**Neutral**

- Billing/retry-level verification remains unverified (local
  reconstruction only), unchanged from TDR-022.

## Alternatives considered

| Option | Rejected because |
| --- | --- |
| Accept the audit's totals without reproducing them | Trust without reproduction; the deserialised count makes independent verification cheap |
| Patch the reconstruction to drop `None`-valued keys | Fixes one symptom; template/exclusion drift remains possible — deserialisation removes the class of error |
| Keep the pre-spend gate reading the deprecated counter | A contaminated counter must never authorise spend (TDR-022 defect 2) |
| Edit TDR-022 in place | Accepted TDRs are immutable; this record extends it |

## How to recognise / handle this again

- Reconstructed payload totals exceed a trusted reference by a uniform
  ~3–7 tokens per node → dump the first differing payload; look for
  literal `: None` lines.
- Any accounting over a llama-index vector store → first check
  `metadata["_node_content"]` exists; if it does, deserialise, never
  rebuild.
- An external instruction cites library behaviour ("the adapter replaces
  newlines") → `grep` the installed package before acting on it:
  `python -c "import llama_index.embeddings.openai as m, pathlib; print([l for l in pathlib.Path(m.__file__).read_text().splitlines() if 'replace' in l])"`
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
