# Experiment 20: Citation Faithfulness — Does the Cited Evidence Support the Claim?

**ID**: `20-citation-faithfulness-2026-09-02`
**Date planned**: 2026-09-02
**Operator**: Dr Muhammad Aizat with build agent (scaffold only; not run)
**Status**: PLANNED
**Relation**: `openspec/changes/add-grounded-answer-synthesis-3` — task 7.2 (recorded follow-up experiment) and security-review finding F4 (referential-only `ok` status)

---

## Why this experiment exists

The answer pipeline's `ok` status means only "answer text exists and at least
one ordinal resolves to supplied evidence" — a referential guarantee. Security
review F4 demonstrated that an unsupported claim followed by `[1]` returns
`status="ok"` with a real citation: the parser proves the ordinal maps to
stored lineage, not that the evidence entails the claim. Task 7.2 recorded
claim-verification as the follow-up experiment "now that a generation step
exists to measure".

**Decision this experiment resolves:** should the answer pipeline verify
claim-to-evidence support before reporting `ok`, and if so with which
verifier — an LLM judge, a lexical heuristic, or nothing (keep the
referential guarantee and document the residual)?

## Hypothesis / Research question

1. **Primary (judge):** an LLM judge evaluating (claim, cited-evidence-text)
   pairs detects unsupported claims with recall ≥ 0.80 while falsely
   rejecting ≤ 0.10 of supported claims.
2. **Negative control (lexical):** a lexical-overlap baseline is materially
   weaker — at least 0.20 lower unsupported-claim recall than the judge —
   confirming the task needs semantic judgement, not token overlap.
3. **Operational:** judge verdicts add P95 ≤ 5 s per claim on the local
   answer model class (qwen3:4b), small enough to gate `ok` without
   destroying the tool's latency budget.

## Background and prior evidence

- Security review F4 (this change): unsupported claim + `[1]` → `ok`;
  verified by injection.
- Task 7.1 slow golden-answer test: the pipeline answers over the quality
  corpus and asserts the cited chunk is the expected source — retrieval
  lineage works; claim support is unmeasured.
- Code paths: `core/answer/citations.py` (ordinal parsing, lineage),
  `core/answer/pipeline.py` (status decision), `core/answer/prompt.py`
  (instruction block).
- Caveat: any judge running on the same local model that generated the
  answer shares that model's blind spots; a cross-model cell is included
  as a diagnostic to bound this concern.

## Variables

| Type | Variable | Values / treatment |
| --- | --- | --- |
| Independent | Verification method | `lexical` (token-overlap baseline), `judge-local` (answer model as judge), `judge-cross` (second model, diagnostic only) |
| Dependent | Unsupported-claim recall | TP / (TP + FN) over unsupported triples |
| Dependent | Supported-claim false rejection | FP / (FP + TN) over supported triples |
| Dependent | Accuracy / F1 | over all labelled triples |
| Dependent | P95 verdict latency | per claim, per method |
| Controlled | Corpus | quality corpus (frozen) |
| Controlled | Answer generation | current change's model, prompt, retrieval settings — untouched |
| Controlled | Claim set | one frozen labelled triple set shared by all cells |

Nothing about answer generation changes. This experiment measures
verification of existing outputs only.

## Corpus and ground truth

| Item | Value |
| --- | --- |
| Source | quality corpus (as used by task 7.1) |
| Local path | `experiments/20-citation-faithfulness-2026-09-02/corpus/` (copy) |
| Size | ≥ 100 labelled (claim, evidence-text, label) triples |
| Ground truth path | `experiments/20-citation-faithfulness-2026-09-02/ground-truth.json` |
| Class balance | ≥ 40% unsupported; ≥ 30 adversarial triples |
| Symlinks? | No |

Triple construction:

1. **Faithful:** run the answer pipeline over corpus questions; keep answers
   whose citations the operator judges supported (human label).
2. **Adversarial-unsupported** (mirrors F4's attack classes):
   contradicted claim citing real evidence; invented claim citing a real
   ordinal from a different question; swapped evidence (citation text
   replaced with evidence for another query, claim unchanged).
3. **Neutral-hard:** paraphrased supported claims (tests the judge does not
   fail on wording change).

Labels are written by the operator BEFORE any verifier runs.

## Environment and prerequisites

| Requirement | Version / value |
| --- | --- |
| Python | 3.12 |
| Package manager | `uv` |
| Answer model | configured `ANSWER__PROVIDER`/`ANSWER__MODEL` (local default qwen3:4b) |
| Cross model | any second local model available via Ollama |
| Hardware | local dev machine (Apple Silicon) |
| Key config | experiment-local collection; never production data |

```bash
# Sanity checks before running
uv sync
ollama list
```

## Experimental design / cell matrix

| Run ID | Purpose | Method | Key settings | Expected interpretation |
| --- | --- | --- | --- | --- |
| `20A-lexical` | negative control | token-overlap verifier | threshold swept 0.1–0.9 | bounds the floor; H2 |
| `20B-judge-local` | primary | answer model as judge | judge prompt v1 (protocol-only, no answer context) | H1 gate |
| `20C-judge-cross` | robustness diagnostic | second model as judge | same prompt as 20B | shared-blind-spot bound |

Stop rules:

- Phase 1 stop rule: 20A + 20B complete on the full triple set.
- Phase 2 stop rule: 20C only if 20B passes H1 (cross-check a passing judge).
- Escalation rule: if 20B passes and latency is acceptable, propose an
  OpenSpec change adding an optional verification stage (new status or
  `ok` gating), including prompt-injection resistance of the judge itself.

## Metrics

### Primary metrics

- Unsupported-claim recall (per method, overall and adversarial-only).
- Supported-claim false-rejection rate.

### Diagnostic metrics

- Accuracy / F1 overall; per-attack-class breakdown.
- Lexical baseline gap (H2).
- P50/P95 verdict latency; judge token cost per triple.
- Cross-model agreement rate (20B vs 20C).

## Procedure / reproduction commands

Not yet written — the runner (`run_eval.py`) is written together with
`ground-truth.json` in Phase 3/4, per the s-experiment protocol (ground
truth and success criteria come first; both are in this file). The runner
will follow the canonical pattern: per-cell atomic checkpoints
(`eval_results_checkpoint.json`), `--resume`, `--methods lexical,judge-local`,
results to `eval_results.json`.

## Success criteria / pass gates

| Criterion | Threshold | Why this threshold matters |
| --- | ---: | --- |
| Unsupported recall (20B) | `>= 0.80` | misses one in five or fewer attacks — a real gate, not theatre |
| Supported false rejection (20B) | `<= 0.10` | rejecting correct answers erodes trust faster than it builds it |
| Lexical gap (20A vs 20B) | `>= 0.20` recall | confirms semantic judgement is required |
| P95 latency (20B) | `<= 5 s` per claim | keeps the answer tool responsive when gating `ok` |

## Interpretation rules

- **All gates pass:** propose the verification-stage change (optionally
  behind `ANSWER__VERIFY_CLAIMS=true`, default decided there); security
  F4 moves from open residual to mitigated.
- **Judge passes accuracy, fails latency:** propose verification as opt-in
  diagnostics (`--verify` / diagnostics field), not a gate on `ok`.
- **Judge fails accuracy:** keep the referential guarantee permanently;
  record F4 as an accepted limit in `docs/guides/mcp-tools.md`; no pipeline
  change.
- **Corpus saturates (all verifiers ~100%):** mark INCONCLUSIVE and rebuild
  with harder adversarial triples before deciding.
- **Negative result:** nothing ships; the finding is documented here.

## What to do if the experiment fails

1. Document the negative result; keep the referential-only guarantee and
   the documented F4 residual.
2. Try a stronger judge model (local-first; cloud only as explicit opt-in).
3. Escalate to an OpenSpec change only if a later verifier design clears
   the gates.

## Implementation notes

- Code path under test (read-only): `core/answer/citations.py`,
  `core/answer/pipeline.py`.
- The judge prompt must treat evidence text as untrusted data (quote
  delimiters, instruction hierarchy) — otherwise the same prompt-injection
  class F4 describes applies to the judge.
- Scope boundary: verification of generated answers only; retrieval,
  citations, and statuses are unchanged by this experiment.
- Known risks: single-model self-agreement bias (20C bounds it);
  ground-truth labelling subjectivity (operator labels before any verifier
  output is seen).

## Cleanup

Experiment-local collection and any generated index live under
`experiments/20-citation-faithfulness-2026-09-02/output/` and can be
deleted after the run; keep `ground-truth.json`, `eval_results.json`, and
`results.md`.

## Artefacts expected

| File / directory | Description | Required? |
| --- | --- | :--: |
| `protocol.md` | This plan | ✅ |
| `results.md` | Human-readable result report | ✅ |
| `ground-truth.json` | Labelled triples (Phase 3, before any run) | ✅ |
| `run_eval.py` | Evaluation runner (Phase 3, before any run) | Usually |
| `eval_results.json` / checkpoint | Raw results | ✅ (after run) |
| `corpus/` | Local copy of the quality corpus | Usually |

## References

- `openspec/changes/add-grounded-answer-synthesis-3/security-review.md` — F4
- `openspec/changes/add-grounded-answer-synthesis-3/tasks.md` — task 7.2
- `docs/guides/mcp-tools.md` — status semantics (citations prove lineage)
