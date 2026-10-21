# Tasks

Before you start: get the user's answers to the open questions in design.md. These tasks follow the recommended options. Work in a feature worktree `llamaindex-rag-mcp-feat-fix-claim-splitter-non-claims` on branch `feat/fix-claim-splitter-non-claims`, forked from `v3`. Prepare it with `uv sync --frozen --extra web`.

Run every command below with `uv run --no-sync`. Plain `uv run` re-syncs the environment and removes the `web` extra. The OpenAPI and web tests then skip, and a skipped test looks like a pass.

## 1. Failing tests for each skipped construct

Add the tests to `tests/test_answer_verify.py` next to the existing `split_claims` tests. Run each new test on the unchanged code and record that it fails.

- [ ] 1.1 Add a test: `## Installation [1]` plus a cited sentence gives only the sentence claim. Verify it fails on current code (today `## Installation` is a claim).
- [ ] 1.2 Add a parametrised test for ATX headings `#` to `######` with a citation on the line, and for a heading followed by a marker-only line. Verify every case fails on current code.
- [ ] 1.3 Add a test for the live case: cited sentence, fenced `bash` block, then a line `[1]`. Assert the claims hold only the sentence and no claim text starts with three backticks. Verify it fails on current code.
- [ ] 1.4 Add tests for an opening fence with a marker (`` ```bash [1] ``), a closing fence with a marker, an indented fence inside a list, and a tilde fence. Verify each fails on current code.
- [ ] 1.5 Add tests for code lines inside a fence: a cited code line, and a code line followed by `[1]`. Verify both fail on current code.
- [ ] 1.6 Add tests for horizontal rules `---`, `***` and `* * *`, a table separator row and bare list markers `-` and `1.`, each followed by `[1]` or cited on the line. Verify each fails on current code.
- [ ] 1.7 Add a test: cited sentence, fenced block, then `[2]`. Assert the claims are only the sentence with ordinal 1. Verify it fails on current code (today `[2]` attaches to the fence line).
- [ ] 1.8 Add a pipeline test through `answer(...)` with `include_diagnostics=True`: an answer with a cited heading, a fenced block and two cited prose sentences. Use a judge seam that returns `unsupported` for any prompt holding a heading or fence line and `supported` otherwise. Assert `status="ok"`, `verified=true` and `verification_calls == 2`. Verify it fails on current code.
- [ ] 1.9 Add a pipeline test: the only citation sits on a heading. Assert no judge call, `verification_calls == 0`, `status="ok"`, no `verified` field and a `verification_skipped` reason that names no verifiable claims. Add the same test for a leading marker-only line followed by uncited prose. Change the zero-claims assertion in `test_empty_claims_outcome_reports_zero_rate` (`tests/test_answer_verify.py:606`) to match design D4. Verify all three fail on current code.
- [ ] 1.10 Run `uv run --no-sync pytest tests/test_answer_verify.py -q` and confirm only the new tests (and the changed one) fail.

## 2. Fix the splitter

- [ ] 2.1 In `src/omrg/core/answer/verify.py`, add a line classifier that tracks the open fence character and length (design D1, D2). Skip structure lines before the sentence split. Keep the module under 500 lines. Verify tests 1.1 to 1.6 pass.
- [ ] 2.2 Clear `last_text` when the splitter skips a line (design D3). Verify test 1.7 passes and `test_trailing_citation_attaches_to_preceding_claim` still passes.
- [ ] 2.3 In `verify_claims`, set `skipped_reason="no verifiable claims (no cited prose sentence)"` when no claim remains (design D4). Do not change `run_verification_stage`; it already maps the reason to `verification_skipped` with `verified` absent. Verify tests 1.8 and 1.9 pass.
- [ ] 2.4 Update the docstrings: `split_claims` and the module docstring name the skipped constructs; `VerificationOutcome.skipped_reason` and `verify_claims` name the zero-claims reason next to the all-unparseable one. Verify `uv run --no-sync ruff check src/omrg/core/answer/verify.py` passes.

## 3. Real claims are still judged

- [ ] 3.1 Add guard tests that pass before and after the fix: prose after a heading, prose between two fenced blocks, a cited table data row, inline code such as ``Use `## Title` syntax [1].``, `#hashtag` text, and `Fact one [1].` above a `---` underline. Verify each keeps its claim.
- [ ] 3.2 Add fence-rule tests (design D1). (a) The line ```` ```uv sync``` installs it [1]. ```` followed by a cited sentence keeps both claims. It passes on current code; verify it still passes after the fix. (b) A `~~~` line inside a backtick block does not close it, and (c) a closing-like fence with an info string does not close it: the lines after it up to the real closing fence give no claim. Verify (b) and (c) fail on current code and pass after the fix.
- [ ] 3.3 Add a test for an unclosed fence: prose after the opening fence is not judged. Verify it passes and pins the behaviour named in design Risks.
- [ ] 3.4 Run `uv run --no-sync pytest tests/test_answer_verify.py tests/test_file_size_ceiling.py -q`. Verify all pass.

## 4. Contract and docs

- [ ] 4.1 In `src/omrg/transports/api/openapi.yaml`, add "or no cited prose sentence to check" to the `verification_skipped` description (line 5119). Do not change the schema shape. Verify `uv run --no-sync pytest tests/unit/test_web_openapi_conformance*.py -q` passes with no skipped tests.
- [ ] 4.2 In `docs/guides/mcp-tools.md`, Claim verification section: state that only cited prose sentences are judged, that headings, code blocks, rules and table separators are skipped, and the new `verification_skipped` reason. Verify the text with a read-through against the delta spec.
- [ ] 4.3 Grep `docs/guides/` for "per cited claim" and update the wording where it needs "prose". Verify `grep -rn "per cited claim" docs/guides/` shows only consistent text.
- [ ] 4.4 Check that `web/src/chat/answerStatus.ts` and `web/src/chat/AssistantTurn.tsx` need no change (design D4, D5). Record the check in the PR description.

## 5. Integration checks

- [ ] 5.1 Run `uv run --no-sync pytest -n auto -m "not slow" --deselect tests/test_clean_base_tripwire.py -q`. Ask the user before you run the full suite. Verify it passes.
- [ ] 5.2 Run `openspec validate fix-claim-splitter-non-claims --strict`. Verify it reports the change as valid.
- [ ] 5.3 Live check. Ask the user before you start any server. Start `omrg web` from the feature worktree on a free port other than 8765, with `--workspace` set to a scratch folder and `OMRG_CONFIG_DIR` set to a scratch folder. Never use `~/.omrg` or `~/.config/omrg`. Ingest a small install guide, turn on claim checks with a configured judge, and ask for install steps. Verify the answer badge is not amber for heading or fence lines and `verification_calls` equals the number of cited prose sentences. Stop the server afterwards.
