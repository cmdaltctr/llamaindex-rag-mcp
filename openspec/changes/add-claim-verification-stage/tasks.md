# Tasks: add-claim-verification-stage

The ADR comes first — the decision is recorded before any implementation
begins, per the change workflow. Settings follow ADR-037 (injected, never
global). Cloud features degrade gracefully to local (ADR-024). This is a
proposal only; tasks are not started until the change is applied.

## 1. ADR — record the claim-verification decision

- [x] 1.1 Write `docs/adr/059-claim-verification-stage.md` recording the
      decision to add an optional claim-verification stage to the answer
      pipeline. Reference experiment 20
      (`experiments/20-citation-faithfulness-2026-09-02/`) as the empirical
      evidence: GLM-5.3 judge recall 1.0, false rejection 0.0, P95 3.33 s,
      100% cross-model agreement with DeepSeek V4 Flash 0731. Record the
      cloud-opt-in trade-off against ADR-024's local-first policy and the
      graceful-degradation requirement. Record that the referential-only
      `ok` guarantee remains the fallback when verification is disabled.
      Note the experiment caveats (entity-disjoint corpus, 120 triples,
      pipeline-derived faithful validation set still required).
- [x] 1.2 Update the security review F4 status in
      `openspec/changes/archive/2026-09-03-add-grounded-answer-synthesis-3/security-review.md`
      to reference this ADR and the verification-stage change as the
      mitigation path.

## 2. Settings — add verification configuration

- [x] 2.1 Add three fields to `core/answer/settings.py` (the pure-data
      `AnswerSettings` model): `verify_claims: LegacyBool = False`,
      `verify_model: str = ""` (empty string means derive from the existing
      answer LLM or cloud provider), `verify_provider: str = "cloud"`.
      These mirror the existing `enabled`, `model`, and `provider` fields
      and follow the same `extra="forbid"` convention.
- [x] 2.2 Add the same three fields to `core/settings.py` on the
      `AnswerBlock` (the frozen `EffectiveSettings` block), keeping both
      models in sync per the established convention.
- [x] 2.3 Add the three settings to `config/defaults.yaml` under the
      `answer` block with their default values and inline comments
      explaining the opt-in cloud dependency (ADR-024).
- [x] 2.4 Add the three settings to `.env.example` with commented
      assignment and explanatory comments, per the established convention.
- [x] 2.5 Validate `verify_provider` at startup through
      `compose._resolve_active_strategies`, failing fast on a bad name —
      the same pattern the answer `provider` field already follows.

## 3. Profile YAML — support verification overrides

- [x] 3.1 Add optional `answer.verify_claims`, `answer.verify_model`, and
      `answer.verify_provider` keys to the profile overlay logic in
      `core/profiles/resolver.py` (`_bundle_to_effective`). The
      profile-level value takes precedence over the global default at
      operation time, following the established pattern for
      `retrieval.top_k` and `retrieval.rerank_enabled`.
- [x] 3.2 Add env-var overrides (`ANSWER__VERIFY_CLAIMS`,
      `ANSWER__VERIFY_MODEL`, `ANSWER__VERIFY_PROVIDER`) that take
      precedence over the profile bundle, preserving the "env still wins"
      precedence established by the startup settings resolver.
- [x] 3.3 Document the profile override in `config/profiles/documents.yaml`
      with a commented example showing how to enable verification for the
      document-grounding use case. Do NOT enable it by default in any
      shipped profile — it is opt-in.

## 4. Core implementation — the verification stage

- [x] 4.1 Create `core/answer/verify.py` with an async
      `verify_claims(claims, evidence, verify_llm, settings)` function.
      Split the answer text into claim-level units, pair each with the text
      of the evidence its citation references, and call the judge LLM for
      each pair. Parse the structured verdict (`supported` / `unsupported`
      / `unparseable`). Include `from __future__ import annotations` and
      Google-style docstrings.
- [x] 4.2 Construct the judge prompt with evidence text wrapped in explicit
      quote delimiters, labelled as untrusted data, with the instruction
      hierarchy repeated after each evidence block. This satisfies the
      prompt-injection resistance requirement.
- [x] 4.3 Add `compose.build_verify_llm(settings)` resolving through
      `core/providers/llm/registry.py`; return `None` when verification is
      disabled or no usable provider is configured. Resolve lazily so
      retrieval-only startup remains usable.
- [x] 4.4 Modify `core/answer/pipeline.py` to call the verification stage
      after citation assembly and before the final status decision, when
      `verify_claims` is true and a verification LLM is available. On
      success: keep `status="ok"`, add `verified=true`. On failure: set
      `status="unverified_claims"`, list failing claims, retain evidence.
      On provider unavailable or unparseable: keep `status="ok"`, add
      `verification_skipped` with a reason. Never raise.
- [x] 4.5 Report `verification_ms` and `verification_calls` in diagnostics
      when diagnostics are enabled and verification ran, separate from
      `retrieval_ms` and `generation_ms`.
- [x] 4.6 Confirm no file exceeds the 500-line ceiling; split cohesive
      helpers before editing the already-hot `pipeline.py` and `compose.py`.

## 5. Tests — unit and integration

- [x] 5.1 Unit test: `verify_claims` with all-supported claims returns
      `verified=true` and keeps `status="ok"`.
- [x] 5.2 Unit test: `verify_claims` with one unsupported claim returns
      `status="unverified_claims"`, lists the failing claim, and retains
      evidence and citations.
- [x] 5.3 Unit test: verification disabled by default — no judge call is
      made, `status="ok"`, no `verified` field.
- [x] 5.4 Unit test: verification provider unavailable (no API key) —
      `status="ok"` with `verification_skipped`, no judge call.
- [x] 5.5 Unit test: judge call raises a network error — `status="ok"`
      with `verification_skipped`, evidence retained, pipeline does not
      raise.
- [x] 5.6 Unit test: all verdicts unparseable — `status="ok"` with
      `verification_skipped` naming the unparseable rate.
- [x] 5.7 Unit test: evidence text is wrapped in quote delimiters and the
      prompt labels it as untrusted data (prompt-injection resistance).
- [x] 5.8 Unit test: profile override enables verification for a
      collection bound to a profile with `answer.verify_claims: true`.
- [x] 5.9 Unit test: env var `ANSWER__VERIFY_CLAIMS=true` overrides a
      profile bundle that sets `answer.verify_claims: false`.
- [x] 5.10 Integration test: the full answer pipeline with verification
       enabled produces `verified=true` on a grounded answer and
       `unverified_claims` on an adversarial answer, with evidence
       retained in both cases.
- [x] 5.11 Confirm `uv run pytest -m "not slow" --cov=rag_mcp` is green
       and coverage floors are held.

## 6. Documentation

- [x] 6.1 Update `docs/guides/mcp-tools.md`: document the `verified` field,
       the `unverified_claims` and `verification_skipped` statuses, the
       three new settings, and the F4 mitigation. State the cloud
       dependency and the latency cost (P95 ~3.3 s per claim on GLM-5.3).
- [x] 6.2 Update `docs/guides/configuration.md`: document
       `ANSWER__VERIFY_CLAIMS`, `ANSWER__VERIFY_MODEL`,
       `ANSWER__VERIFY_PROVIDER`, their defaults, and the opt-in cloud
       trade-off against ADR-024.
- [x] 6.3 Update `docs/guides/cli-reference.md`: document the `--verify`
       flag if exposed on the CLI `answer` command, or note that
       verification is settings-only.
- [x] 6.4 Update `.env.example` with the three new settings (task 2.4
       covers the file edit; this task confirms the documentation is
       consistent).

## 7. OpenSpec validation

- [x] 7.1 `openspec validate add-claim-verification-stage --strict` —
       passes.
- [x] 7.2 `openspec validate --all --strict` — passes with no regressions
       on existing changes or specs.
- [x] 7.3 `uv run lint-imports` — clean, no new ignore entries. If an
       ignore is needed, the injection pattern has been violated — fix it
       instead.
- [x] 7.4 Confirm no file exceeds 500 lines (`tests/test_file_size_ceiling.py`).
