# Experiment 20: Citation Faithfulness — Does the Cited Evidence Support the Claim?

**ID**: `20-citation-faithfulness-2026-09-02`
**Date planned**: 2026-09-02
**Operator**: Dr Muhammad Aizat with build agent (scaffold only; not run)
**Status**: PASS (all gates met; see `results.md`)
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
3. **Operational:** judge verdicts add P95 ≤ 5 s per claim on the
   judge model (Z.AI GLM-5.3 via cloud API), small enough to gate `ok`
   without destroying the tool's latency budget.

## Background and prior evidence

- Security review F4 (this change): unsupported claim + `[1]` → `ok`;
  verified by injection.
- Task 7.1 slow golden-answer test: the pipeline answers over the quality
  corpus and asserts the cited chunk is the expected source — retrieval
  lineage works; claim support is unmeasured.
- Code paths: `core/answer/citations.py` (ordinal parsing, lineage),
  `core/answer/pipeline.py` (status decision), `core/answer/prompt.py`
  (instruction block).
- Caveat: the judge is a cloud model (GLM-5.3) distinct from the
  production answer generator (qwen3:4b, local), so the shared-blind-spot
  concern is structurally weaker than a self-judge setup. The cross-model
  cell (20C, DeepSeek V4 Flash 0731 via OpenRouter) remains as a
  judge-vs-judge agreement diagnostic.

## Variables

| Type | Variable | Values / treatment |
| --- | --- | --- |
| Independent | Verification method | `lexical` (token-overlap baseline), `judge-local` (Z.AI GLM-5.3 as judge), `judge-cross` (DeepSeek V4 Flash 0731 via OpenRouter, diagnostic only) |
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

1. **Faithful:** fact sentences A and B verbatim from each corpus file as
   extractive supported controls (amendment 1, 2026-09-02 — the original
   plan derived these from answer-pipeline outputs with human labels;
   extractive construction makes labels deterministic by construction;
   pipeline-derived faithful claims are a follow-up validation set before
   any H1-based deployment decision).
2. **Adversarial-unsupported** (mirrors F4's attack classes):
   contradicted claim citing real evidence (explicitly exclusive "instead
   of" flip of one fact slot); invented claim — a purely additive
   fabrication paired with its own real file, the F4 shape where the
   citation resolves to genuine lineage that simply does not entail the
   claim; swapped evidence (citation text replaced with evidence for
   another query, claim unchanged).
3. **Neutral-hard:** paraphrased supported claims (tests the judge does not
   fail on wording change; the named institution stays the agent).

Labels are written by the operator BEFORE any verifier runs.

## Environment and prerequisites

| Requirement | Version / value |
| --- | --- |
| Python | 3.12 |
| Package manager | `uv` |
| Judge model (20B) | Z.AI GLM-5.3 via `ZAI_API_KEY` (cloud, OpenAI-compatible) |
| Cross model (20C) | DeepSeek V4 Flash 0731 via `OPENROUTER_API_KEY` (OpenRouter) |
| Optional extra | `uv sync --extra openrouter` (installs `llama-index-llms-openai-like`) |
| Hardware | any machine with network access to the cloud APIs |
| Key config | experiment-local collection; never production data |

```bash
# Sanity checks before running
uv sync --extra openrouter
echo $ZAI_API_KEY        # primary judge
echo $OPENROUTER_API_KEY # cross judge
```

## Experimental design / cell matrix

| Run ID | Purpose | Method | Key settings | Expected interpretation |
| --- | --- | --- | --- | --- |
| `20A-lexical` | negative control | token-overlap verifier | threshold swept 0.1–0.9 | bounds the floor; H2 |
| `20B-judge-local` | primary | Z.AI GLM-5.3 as judge | judge prompt v1 (protocol-only, no answer context), cloud API | H1 gate |
| `20C-judge-cross` | robustness diagnostic | DeepSeek V4 Flash 0731 (OpenRouter) as judge | same prompt as 20B | judge-vs-judge agreement |

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

The runner (`run_eval.py`) and frozen triple set (`ground-truth.json`) were
written together per the s-experiment protocol (ground truth first).  The
runner validates the triple set against this protocol's gates (≥ 100 triples,
≥ 40% unsupported, ≥ 30 adversarial, evidence byte-identical to `corpus/`)
before any verifier runs, and checkpoints per triple so an interrupted judge
cell resumes without repeating model calls.

```bash
# Sanity checks before running
uv sync --extra openrouter
echo $ZAI_API_KEY        # primary judge (Z.AI GLM-5.3)
echo $OPENROUTER_API_KEY # cross judge (OpenRouter)

# Cell 20A — lexical negative control (no model; already computed, resumable)
PYTHONUNBUFFERED=1 uv run python -u experiments/20-citation-faithfulness-2026-09-02/run_eval.py \
  --methods lexical

# Cell 20B — primary judge gate (Z.AI GLM-5.3 via cloud API)
PYTHONUNBUFFERED=1 ANSWER__TIMEOUT=600 uv run python -u experiments/20-citation-faithfulness-2026-09-02/run_eval.py \
  --methods judge-local --resume 2>&1 | tee -a experiments/20-citation-faithfulness-2026-09-02/output/run_eval.log

# Cell 20C — cross-model diagnostic (only if 20B passes H1)
PYTHONUNBUFFERED=1 ANSWER__TIMEOUT=600 uv run python -u experiments/20-citation-faithfulness-2026-09-02/run_eval.py \
  --methods judge-cross --cross-model deepseek/deepseek-v4-flash-0731 --resume
```

Judge cells construct an `OpenAILike` LLM pointed at the cloud API
(Z.AI or OpenRouter) with temperature pinned to 0;
replies are stripped of `<think>` blocks and parsed for strict JSON, with one
retry before a verdict is recorded as unparseable (reported separately,
never silently counted as either class).

## Success criteria / pass gates

| Criterion | Threshold | Why this threshold matters |
| --- | ---: | --- |
| Unsupported recall (20B) | `>= 0.80` | misses one in five or fewer attacks — a real gate, not theatre |
| Per-class recall (20B) | `>= 0.80` each for contradicted, invented, swapped | aggregate recall is gameable: swapped and invented are lexically trivial, so 0.80 overall passes while missing most contradicted claims (amendment 2) |
| Supported false rejection (20B) | `<= 0.10` | rejecting correct answers erodes trust faster than it builds it |
| Paraphrase false rejection (20B) | `<= 0.10` | the FR gate must hold on the wording-change class, not just on verbatim faithful claims (amendment 2) |
| Lexical gap (20A vs 20B) | `>= 0.20` recall | confirms semantic judgement is required; the lexical operating point is its best threshold subject to the same `<= 0.10` false-rejection budget the judge must satisfy (amendment 2) |
| P95 latency (20B) | `<= 5 s` per claim | keeps the answer tool responsive when gating `ok` (cloud API round-trip including reasoning) |

### Amendments (pre-registered changes; all made 2026-09-02 after the lexical control arm, before any judge run)

1. **Faithful construction (corpus section above).** The committed dataset
   uses verbatim corpus sentences, not pipeline-derived answers with human
   labels — deterministic labels, and pipeline-derived faithful claims
   remain a required validation set before any deployment decision built
   on H1.
2. **Gate strengthening and the H2 operating point.** The lexical control
   arm showed (a) aggregate recall 0.80 is reachable while detecting only
   4/20 contradicted claims (swapped and invented are lexically trivial),
   and (b) an unconstrained lexical best threshold (recall 0.95 at 0.267
   false rejection) caps the judge's possible gap at 0.05, making the
   original H2 formulation vacuous. Gates added/tightened as in the table
   above; the runner records both lexical operating points and names the
   constrained one as the H2 reference. Tightening a gate after seeing
   only the control arm, blind to the treatment arm, strengthens rather
   than games the pre-registration.
3. **Contradicted exclusivity.** The first dataset revision used bare
   slot flips ("every Thursday" against "every Tuesday") that can coexist
   with the evidence; all non-exclusive contradicted claims were reworded
   with explicit "instead of" contrast (audit finding, 2026-09-02). Five
   invented claims that flipped stated slots were reworded to purely
   additive fabrications, and thirteen paraphrases were reworded to keep
   the named institution as agent.
4. **Declined: a hard-swapped stratum** (swapped pairs with topically
   related evidence). This corpus is intentionally entity-disjoint per
   file; only one related pair exists (harbour ↔ meridian via golden
   query q12), which cannot support a stratum. Recorded as a known
   limitation: if 20B passes with suspiciously easy swapped detection,
   rebuild the corpus with related-file structure before trusting the
   swapped class.
5. **Cloud judge substitution (2026-09-02, before any judge run).** The
   original design used the local answer model (qwen3:4b via Ollama) as
   judge. On a 32 GB M1 Pro, LlamaIndex's Ollama client sent
   `num_ctx=262144` (qwen3's model-info default, ignoring the Modelfile
   `PARAMETER`), consuming 43 GB and spilling 41% of compute to CPU —
   zero verdicts in 10+ minutes. The judge was switched to cloud:
   Z.AI GLM-5.3 (`ZAI_API_KEY`) for 20B, DeepSeek V4 Flash 0731 via
   OpenRouter (`OPENROUTER_API_KEY`) for 20C. This is a judge-only
   substitution; the production answer generator remains qwen3:4b
   (local). The shared-blind-spot concern is structurally weaker than a
   self-judge setup because the judge and the answer generator are now
   different model families. The H3 latency gate is retained at ≤ 5 s
   but now measures cloud API round-trip (including reasoning) rather
   than local inference. The `lexical` cell (20A) is unaffected — it
   uses no model and its results stand.

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
2. Try a stronger judge model (cloud or local).
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
- Known risks: judge-vs-answer-generator model-family bias (the judge is
  GLM-5.3, the answer generator is qwen3:4b — different families, so
  shared blind spots are less likely than a self-judge setup; 20C adds a
  second judge family as further diagnostic); ground-truth labelling
  subjectivity (operator labels before any verifier output is seen).

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
