# Tasks

Before you start: get the user's answers to the open questions in design.md. These tasks follow the recommended options. Work in a feature worktree `llamaindex-rag-mcp-feat-fix-claim-splitter-non-claims` on branch `feat/fix-claim-splitter-non-claims`, forked from `v3`. Prepare it with `uv sync --frozen --extra web`.

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
- [ ] 1.9 Add a pipeline test: the only citation sits on a heading. Assert no judge call, `status="ok"`, no `verified` field and a `verification_skipped` reason that names no verifiable claims. Change the zero-claims assertion at `tests/test_answer_verify.py:606` to match design D4. Verify both fail on current code.
- [ ] 1.10 Run `uv run pytest tests/test_answer_verify.py -q` and confirm only the new tests (and the changed one) fail.

## 2. Fix the splitter

- [ ] 2.1 In `src/omrg/core/answer/verify.py`, add a line classifier with a fence-state flag (design D1, D2). Skip structure lines before the sentence split. Keep the module under 500 lines. Verify tests 1.1 to 1.6 pass.
- [ ] 2.2 Clear `last_text` when the splitter skips a line (design D3). Verify test 1.7 passes and `test_trailing_citation_attaches_to_preceding_claim` still passes.
- [ ] 2.3 In `verify_claims`, return a `skipped_reason` when no claim remains (design D4). Make sure `run_verification_stage` maps it to `verification_skipped` with `verified` absent. Verify tests 1.8 and 1.9 pass.
- [ ] 2.4 Update the `split_claims` docstring and the module docstring to name the skipped constructs. Verify `uv run ruff check src/omrg/core/answer/verify.py` passes.

## 3. Real claims are still judged

- [ ] 3.1 Add guard tests that pass before and after the fix: prose after a heading, prose between two fenced blocks, a cited table data row, inline code such as ``Use `## Title` syntax [1].``, `#hashtag` text, and `Fact one [1].` above a `---` underline. Verify each keeps its claim.
- [ ] 3.2 Add a test for an unclosed fence: prose after the opening fence is not judged. Verify it passes and pins the behaviour named in design Risks.
- [ ] 3.3 Run `uv run pytest tests/test_answer_verify.py tests/test_file_size_ceiling.py -q`. Verify all pass.

## 4. Contract and docs

- [ ] 4.1 In `src/omrg/transports/api/openapi.yaml`, add "no verifiable claims" to the `verification_skipped` description. Do not change the schema shape. Verify the OpenAPI contract tests pass (`uv run pytest -q -k openapi`).
- [ ] 4.2 In `docs/guides/mcp-tools.md`, Claim verification section: state that only cited prose sentences are judged, that headings, code blocks, rules and table separators are skipped, and the new `verification_skipped` reason. Verify the text with a read-through against the delta spec.
- [ ] 4.3 Grep `docs/guides/` for "per cited claim" and update the wording where it needs "prose". Verify `grep -rn "per cited claim" docs/guides/` shows only consistent text.
- [ ] 4.4 Check that `web/src/chat/answerStatus.ts` and `web/src/chat/AssistantTurn.tsx` need no change (design D4, D5). Record the check in the PR description.

## 5. Integration checks

- [ ] 5.1 Run `uv run pytest -n auto -m "not slow" --deselect tests/test_clean_base_tripwire.py -q`. Ask the user before you run the full suite. Verify it passes.
- [ ] 5.2 Run `openspec validate fix-claim-splitter-non-claims --strict`. Verify it reports the change as valid.
- [ ] 5.3 Live check. Ask the user before you start any server. Start `omrg web` from the feature worktree on a free port other than 8765, with `--workspace` set to a scratch folder and `OMRG_CONFIG_DIR` set to a scratch folder. Never use `~/.omrg` or `~/.config/omrg`. Ingest a small install guide, turn on claim checks with a configured judge, and ask for install steps. Verify the answer badge is not amber for heading or fence lines and `verification_calls` equals the number of cited prose sentences. Stop the server afterwards.
