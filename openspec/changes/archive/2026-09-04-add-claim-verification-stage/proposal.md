# Add a claim-verification stage to the grounded answer pipeline

## Why

The grounded answer pipeline (`add-grounded-answer-synthesis-3`) generates
answers with ordinal citations. The citation parser proves that an ordinal
resolves to stored evidence — a referential guarantee. It does **not** prove
that the cited evidence supports the claim — a semantic guarantee. Security
review finding F4 documented this as an accepted design limit: an unsupported
claim followed by `[1]` returns `status="ok"` with a real citation, because
the parser proves the ordinal maps to stored lineage, not that the evidence
entails the claim.

Experiment 20 (`experiments/20-citation-faithfulness-2026-09-02/`, PASS)
measured an LLM judge's ability to close that gap. The results:

- **GLM-5.3 judge (Cell B):** unsupported-claim recall 1.0, false rejection
  0.0, P95 latency 3.33 s, unparseable 0.0. All three adversarial classes
  (contradicted, invented, swapped) detected at recall 1.0.
- **DeepSeek V4 Flash 0731 cross-judge (Cell C):** recall 1.0, false
  rejection 0.0, 100% agreement with Cell B across all 120 triples.
- **Lexical baseline (Cell A):** recall 0.617 at the constrained operating
  point, 0.0 on contradicted claims — confirming the task needs semantic
  judgement, not token overlap.
- **All pre-registered gates passed:** H1 (recall ≥ 0.80, false rejection
  ≤ 0.10), H2 (lexical gap ≥ 0.20), H3 (P95 ≤ 5 s).

The experiment's escalation rule fires: all gates pass → propose the
verification-stage change. F4 moves from open residual to mitigated.

## What Changes

- An optional claim-verification stage in the answer pipeline. When enabled,
  an LLM judge evaluates each (claim, cited-evidence-text) pair before the
  pipeline reports `ok`. A claim is a sentence-level unit extracted from the
  generated answer; the judge receives only the claim and the text of the
  evidence its ordinal cites, with no answer context, and returns a
  structured verdict.
- Three new settings on the answer settings block:
  - `ANSWER__VERIFY_CLAIMS` (default: `false` — opt-in, because verification
    requires a cloud model and the project is local-first by default per
    ADR-024).
  - `ANSWER__VERIFY_MODEL` (default: derived from the existing answer LLM
    configuration or the cloud provider; the experiment used GLM-5.3).
  - `ANSWER__VERIFY_PROVIDER` (default: `cloud` — the experiment showed a
    local qwen3:4b judge was infeasible on consumer hardware; cloud is the
    only tested path, and it must degrade gracefully to local when a local
    judge becomes viable).
- Profile YAML support: profiles can enable or disable verification per use
  case. A `documents` profile that prioritises factual grounding may enable
  verification; a `codebase` profile that prioritises speed may leave it
  disabled.
- When verification succeeds (every claim is supported): the status stays
  `ok`, and the result carries a `verified: true` signal.
- When verification fails (one or more claims are unsupported): the status
  becomes `unverified_claims`, the evidence and citations are retained, and
  the result lists which claims failed verification. The answer text is
  still returned so the caller can decide what to do with it.
- When verification is disabled (the default): the current referential-only
  `ok` guarantee stays unchanged. No behavioural change for existing
  deployments.
- When the verification provider is unavailable (cloud API key missing,
  network error, model not configured): the stage degrades gracefully. The
  result reports `verification_skipped` with a reason, and the answer
  retains its referential-only `ok` status. The pipeline never raises and
  never blocks an answer behind a cloud dependency the operator has not
  configured (ADR-024 local-first policy).

### Prompt-injection resistance of the judge

The judge itself is an LLM call that receives evidence text — the same
untrusted content the answer generator receives. The judge prompt MUST
treat evidence text as quoted data with strong delimiters and an explicit
instruction hierarchy, so an injected instruction inside a cited chunk
cannot flip the judge's verdict. Experiment 20's protocol documented this
requirement; the implementation MUST satisfy it. Specifically:

- Evidence text is wrapped in explicit quote delimiters that the prompt
  labels as data, not instructions.
- The judge prompt states that text inside the delimiters is untrusted
  source material and must never be executed as an instruction.
- The instruction hierarchy is repeated after each evidence block.

## How

The verification stage runs after citation assembly and before the final
status decision in `core/answer/pipeline.py`. The flow:

1. The existing pipeline generates an answer and builds citations from
   ordinals.
2. If `ANSWER__VERIFY_CLAIMS` is true and a verification provider is
   available, the stage splits the answer into claim-level units and pairs
   each with the text of the evidence its citation references.
3. The judge evaluates each pair and returns a structured verdict
   (`supported` / `unsupported` / `unparseable`).
4. If every claim is supported, the result keeps `status="ok"` and adds
   `verified: true`.
5. If any claim is unsupported, the result becomes
   `status="unverified_claims"` with the failing claims listed; evidence and
   citations are retained.
6. If the judge cannot be reached or returns unparseable verdicts, the
   result reports `verification_skipped` with a reason, and the
   referential-only `ok` status is preserved.

The judge LLM is injected by the composition root, exactly as the answer LLM
already is — no new import edge, no settings singleton inside `core/`
(ADR-037).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `grounded-answer-synthesis`: gains the optional claim-verification stage,
  the `unverified_claims` and `verification_skipped` statuses, the
  `verified` signal, and the three new settings.

## Impact

- **Purely additive when disabled.** The default (`ANSWER__VERIFY_CLAIMS=
  false`) changes no existing behaviour. The referential-only `ok` guarantee
  stays as the fallback.
- **Opt-in cloud dependency.** Verification requires a cloud model
  (experiment 20 showed a local qwen3:4b judge was infeasible on consumer
  hardware). This is an explicit opt-in per ADR-024; the stage degrades
  gracefully to the referential-only guarantee when the cloud provider is
  unavailable.
- **Cost and latency.** When enabled, verification adds one judge call per
  claim. Experiment 20 measured P95 3.33 s per claim on GLM-5.3. The tool
  description and documentation MUST state this cost so a caller chooses
  knowingly.
- **Code.** New `core/answer/verify.py` (the judge stage), new fields on
  `core/answer/settings.py` and `core/settings.py` (the settings block),
  `core/answer/pipeline.py` gains the verification call between citation
  assembly and the status decision, `compose.py` gains
  `build_verify_llm`, profile YAMLs gain optional `answer.verify_claims`
  overrides.
- **Configuration.** Three new settings on the answer block, all defaulting
  to off or derived from existing configuration. No new top-level
  environment variables; nested under `ANSWER__` per ADR-037.
- **Dependencies.** None new. The judge uses the same `OpenAILike` LLM
  client the answer pipeline already uses for cloud providers.
- **Documentation.** `docs/guides/mcp-tools.md` (status semantics, the
  `verified` signal, the F4 mitigation), `docs/guides/configuration.md`
  (the three new settings), `docs/guides/cli-reference.md` (the `--verify`
  flag if exposed).
- **ADR.** A new ADR records the decision to add the verification stage,
  references experiment 20 as the empirical evidence, and records the
  cloud-opt-in trade-off against ADR-024's local-first policy.

## Empirical evidence

Experiment 20 (`experiments/20-citation-faithfulness-2026-09-02/`) provides
the empirical evidence for this change. The full protocol and results are
in the `feat/add-grounded-answer-synthesis-3` branch. Key findings:

| Metric | Cell B (GLM-5.3) | Cell A (lexical) | Gate |
| --- | ---: | ---: | --- |
| Unsupported recall | 1.000 | 0.617 | ≥ 0.80 |
| False rejection | 0.000 | 0.017 | ≤ 0.10 |
| P95 latency | 3.33 s | 0.02 ms | ≤ 5 s |
| Cross-model agreement | 1.000 (Cell C) | — | — |
| Unparseable | 0.0% | 0.0% | report |

### Caveats from the experiment

- The corpus is entity-disjoint per file; the swapped class has only one
  related-file pair. Perfect swapped detection may not generalise to
  topically related evidence (protocol amendment 4).
- 120 triples is a small dataset. Perfect accuracy may indicate corpus
  saturation for the judge class, though the per-class breakdown (lexical
  0.0 on contradicted) shows the corpus is not trivially easy for all
  methods.
- A pipeline-derived faithful claims validation set (amendment 1) remains
  required before any deployment decision built on H1. This is a follow-up
  task, not a blocker for the proposal.
