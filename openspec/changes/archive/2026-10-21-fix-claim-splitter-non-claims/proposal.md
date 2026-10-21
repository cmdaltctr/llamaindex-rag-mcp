# Proposal: fix-claim-splitter-non-claims

## Why

Claim verification (ADR-059) splits an answer into claims and asks a judge whether each claim's cited passage supports it. The splitter also sends markdown structure to the judge: headings, code-fence lines such as ```` ``` ```` and ```` ```bash ````, code lines, horizontal rules and table separator rows. The judge cannot find support for a fence line, so it returns `unsupported`. The answer then gets `status="unverified_claims"` and the amber "Unverified claims" badge, although no real claim is wrong. Each such line also costs one extra judge call. This was seen live on an install-steps answer.

## What Changes

- The claim splitter skips markdown structure lines. It does not send them to the judge: ATX headings, setext underlines, code-fence delimiter lines, the lines inside a fenced code block, horizontal rules, table separator rows and bare list markers.
- A citation marker on a skipped line, or on a marker-only line that follows a skipped line, is not judged. The marker still counts for grounding and stays in `citations`.
- A grounded answer that has no judgeable claim reports `verification_skipped` with a reason (status stays `ok`). Today such an answer reports `verified: true` after zero judge calls.
- Real prose claims next to headings and code blocks are judged as before.
- No change to the result shape, the closed status set, the OpenAPI schema or the web status mapping. Only the `verification_skipped` field description in `openapi.yaml` gets one more reason.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `grounded-answer-synthesis`: adds requirements that state which answer segments are claims, how a citation on a non-claim line is handled, and what an answer with no judgeable claim reports. Modifies "Claim verification is an optional stage gated by configuration": its "Verification enabled" scenario said the result always has a `verified` field, which was already false for failing and degraded runs.

## Impact

- Code: `src/omrg/core/answer/verify.py` (`split_claims`, `verify_claims`, docstrings). `run_verification_stage` already maps a skip reason, so no other module changes.
- Tests: `tests/test_answer_verify.py` (new failing-first tests per construct).
- Contract: `src/omrg/transports/api/openapi.yaml` (`verification_skipped` description text only).
- Docs: `docs/guides/mcp-tools.md` (Claim verification section), `docs/guides/configuration.md` (`verify_claims` row, if the per-claim cost text needs the word "prose").
- Experiments: none. Experiment 20 judges frozen claim–evidence pairs and never calls the splitter.
- Unrelated and untouched: the reranker ÷30 threshold calibration.
