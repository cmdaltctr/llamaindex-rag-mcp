# Tasks

## 1. Draft rules

- [ ] 1.1 Add `web/src/settings/configurationDraft.ts` with `startText`, `cellRule` and `changesOf` (design D2, D3). Verify: Vitest cases fail first, then pass. They cover start text from `saved` on a restart-pending row, the range rule for `answer.max_rounds` 12, "Enter a value." for an empty text that is not optional, `null` for an empty optional number, a bool typed as `true`/`false`, and a change set that holds only the cells that differ.

## 2. Table with edit mode

- [ ] 2.1 Load `omrs-design`. Add `ConfigurationTable.tsx`: one block card with the title, then Edit (or Cancel and Save) at the top right, then a Setting | Value | Source table. Add the read-only lock and the reason line in edit mode, "Next launch: <value>" with "Restart to apply", the chunking identity note, and the source under the key below `sm` (design D1, D6 to D9). Verify: Vitest cases from the scenarios "Block shown as a table", "Read-only identity setting", "Block with no editable setting", "Out of range number refused before the request", "Nothing changed" and "Cancel drops the changes" fail first, then pass.
- [ ] 2.2 Save the changed cells of a table in one request, lock the table, and open the restart dialog once. Keep the draft and show the server message on a refusal (design D5). Verify: Vitest cases "Edit a restart-only number", "Several cells saved together", "Turn a boolean off", "Clear an optional setting", "Refused save keeps the typed values" and "File changed under the page" fail first, then pass.
- [ ] 2.3 In `ConfigurationView`, allow one open table at a time, with the discard dialog when the open table has changes (design D4). Verify: the Vitest case "Second table while the first has changes" covers both Keep editing and Discard, and fails first, then passes.
- [ ] 2.4 Delete `ConfigurationRow.tsx`. Remove the `SettingRow` props and tests that no caller uses any more (design D10). Change the Configuration check in `SettingsCards.test.tsx` to "each setting row is in a table inside a block card". Verify: `grep -rn "ConfigurationRow" web/src` returns nothing; `npm run lint`, `npm run typecheck` and `npm test` pass in `web/`.
- [ ] 2.5 Update the Configuration section of `docs/guides/web-workspace.md` (tables, Edit for each table, one save, clear by emptying, "Next launch") and the Configuration line in `.agents/skills/omrs-design/references/screens.md`. Verify: `grep -n "mini card" docs/guides/web-workspace.md` names no Configuration setting, and `grep -n "Saved for the next launch" docs/guides` returns nothing.

## 3. Checks

- [ ] 3.1 Re-pin `_WEB_EXTRA_CASES` in `tests/test_clean_base_tripwire.py` with a comment, then run `./scripts/local_ci.sh`, `npm run lint`, `npm run typecheck`, `npm test` and `npm run build` in `web/`, and `openspec validate edit-configuration-in-tables --strict`. Verify: all pass; record the counts here.
- [ ] 3.2 Browser check in Orca on a scratch server with a scratch config, at 1280 px and 390 px, following the Orca preview steps. Edit the Retrieval table, change `retrieval.top_k` to 20 and `retrieval.hybrid_enabled`, then save. Expect one request, one restart dialog and "Next launch: 20". Type 12 in `answer.max_rounds` and expect the rule with Save disabled. Press Edit on a second table with changes open and expect the discard dialog. Check that `embed_model` shows its reason in edit mode. At 390 px expect no sideways scroll. Verify: record the results here, and confirm the server log has no error.
