# Re-evaluation of open OpenSpecs against the hardened pipeline

**Date:** 2026-08-22
**Task:** 7.8 of `harden-pipeline-correctness-before-calibration`
**Inputs audited:** each change's `proposal.md`, ADR-047/048/049, TDR-013/014,
Experiments 18 (lock-scope A/B) and 19 (LanceDB lifecycle qualification),
and the Stage 4 repaired harnesses.

## Summary

| Change | Verdict | Reason |
| --- | --- | --- |
| `add-per-collection-persist-dirs` | RE-SCOPE REQUIRED | Problem statement is Chroma-centric; the LanceDB default dissolves most of it |
| `implement-native-sparse-backend-strategy` | RE-TARGET REQUIRED | Names the ChromaDB runtime as its target, now quarantined |
| `register-document-backend-strategies` | UNCHANGED | Aligned with the hardened registry governance; safe to resume |
| `add-login-watcher-installer` | UNCHANGED | Orthogonal to pipeline correctness; safe to resume |

## Detail

### 1. `add-per-collection-persist-dirs` — re-scope required

The Why section motivates the change entirely through
`chromadb.PersistentClient` sharing one SQLite file across collections, so
two concurrent stdio clients contend even when ingesting to different
collections. Three post-hardening facts weaken that motivation:

- The default store is LanceDB (ADR-049). Its native layout already gives
  each collection its own `<name>.lance` directory (visible in Experiment 19
  output: `qual_documents.lance/`, `qual_concurrency.lance/`). The
  cross-collection shared-file contention the change targets does not exist
  on the default path.
- Experiment 19 qualified LanceDB concurrency lifecycle: separate
  collections writing concurrently in one store root, with reopen checks.
- The narrow per-collection write lock (TDR-013, Experiment 18 Phase B)
  already removed the process-wide serialisation for real-embed ingestion.

What remains true: `daemon/watcher` still warns about two processes not
sharing an internal write lock, one-writer-per-collection remains an explicit
boundary, and `chroma`-extra deployments still have the original SQLite
contention. The change should be re-scoped to either (a) a chroma-extra-only
concern, or (b) retired in favour of documenting the LanceDB-native
per-collection layout. Recommendation: rewrite the proposal before resuming.

### 2. `implement-native-sparse-backend-strategy` — re-target required

The proposal commits to "a real native sparse query adapter for the
supported ChromaDB runtime" and conditions promotion on Chroma native sparse
vectors. ADR-049 quarantined that runtime behind the opt-in `chroma` extra;
building the flagship sparse path against a quarantined backend contradicts
the quarantine's intent. The change needs re-targeting to the default
LanceDB runtime (native full-text search) or explicit parking until Stage 6
hybrid evidence (D17 dense/hybrid cells) says native sparse is worth
building at all. The BM25 fallback semantics it specifies remain valid and
unaffected.

### 3. `register-document-backend-strategies` — unchanged

Nothing in Stages 1–6 touched document backends. The proposal's shape
(async contract, lazy registration, local-first fallback with visible
diagnostics, cloud opt-in) matches the hardened architecture invariants:
registries as the sole dispatch mechanism (invariant 10), lazy Azure import
(ADR-024), and injected settings (ADR-037). Resume when scheduled; no
rework needed.

### 4. `add-login-watcher-installer` — unchanged

Purely additive CLI/installer work over `rag-mcp watch`. The watch-command
spec survived `openspec validate --all --strict` (40/40), and the daemon
runner is untouched by the hardening stages. No conflict with any Stage 4–6
evidence. Safe to resume anytime.

## Sequencing note

Both re-scope/re-target items (1 and 2) should be decided before or at the
same time as the Stage 6 campaigns conclude, because D17 hybrid evidence
will inform (2), and the v3 consolidation merge should not carry stale
proposals.
