## 1. Diagnosis

- [ ] 1.1 Capture the full `result.output` of the failing pair and record the
      complete `--- Logging error ---` traceback, naming the failing handler
      class and the stream it holds.
- [ ] 1.2 Bisect `tests/test_mcp_tools.py` to the exact test or import that
      installs the surviving handler, using a root-handler snapshot diff
      (list `logging.root.handlers` before and after candidate phases).
- [ ] 1.3 Confirm the handler references a stream pytest replaced or closed,
      and record the finding in this change's notes.

## 2. Fix

- [ ] 2.1 Add an autouse fixture scoped to the leaking module that snapshots
      and restores root logger handlers and level around each test.
- [ ] 2.2 Confirm no production code change is required. If diagnosis
      implicates production logging behaviour, stop and record the decision
      here before touching `src/`.

## 3. Regression and documentation

- [ ] 3.1 Add a regression guard that fails when a root handler bound to a
      closed or replaced stream survives `tests/test_mcp_tools.py`, or the
      equivalent pair-level guard chosen during implementation.
- [ ] 3.2 Document the order-pair verification command in
      `tests/TEST_README.md` next to the existing targeted commands.
- [ ] 3.3 Record the root cause and fix in `docs/tdr/` from the repository
      template, and index it in `docs/tdr/README.md`.

## 4. Verification

- [ ] 4.1 Run the order pair from task 1.1 and confirm it passes; run the
      CLI JSON test alone and confirm it still passes.
- [ ] 4.2 Run `LOCAL_BACKEND=ollama uv run pytest -m "not slow"` and the
      clean-base tripwire. Update pinned counts only if new tests change the
      verified manifest.
- [ ] 4.3 Run `openspec validate "fix-test-isolation-mcp-cli-order"
      --type change --strict` and resolve every reported error.
