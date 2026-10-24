## Context

See proposal.md, section Why. The change touches the web front end only.

Current state on `v3` (`d6f92c41`):

- `ConfigurationSection.tsx` puts each block in a `Card` and each setting in a `ConfigurationRow`. That row wraps `SettingRow`, which is a `CardInset` mini card with its own Edit, Save, Cancel and Clear buttons, and saves one key for each request.
- The server already accepts several keys in one `PUT /v1/settings/configuration` and writes all of them or none (ADR-095). Each row carries `editable`, `read_only_reason`, `kind`, `choices`, `min`, `max`, `nullable` and `saved`.
- Before `cdab70b9` (2026-10-23) each block was a `Table` with the columns Setting, Value and Source. The `Table` primitive in `web/src/components/ui/table.tsx` still exists and is used on other pages.
- `SettingsCards.test.tsx` fails when a Settings tab has no `Card`. It also checks that each Configuration setting sits in a mini card. This change replaces that second check.
- The settings data at the time of writing: only 7 editable settings are optional, all of them numbers (6 decimal and 1 whole). No choice setting is optional. 32 editable text settings are not optional.

## Goals / Non-Goals

**Goals:**

- One table for each block in its card, with one edit mode and one save for each table.
- Keep every existing check: range rules before the request, read-only reasons, the env lock, the 409 stale-revision message, and the restart dialog.

**Non-Goals:**

- No server, OpenAPI or Python change.
- The Document reading tab and the other Settings tabs keep their mini cards.
- No save across blocks. Each table saves only its own cells.
- No "Not set" entry in choice lists. No choice setting is optional now, so the entry would never show. A choice setting that becomes optional later can add it.

## Decisions

**D1. One `ConfigurationTable` component for each block, with the draft held in the table.**
The table owns a draft map `key → typed text` that exists only in edit mode. Cells are plain controls that report a change up. Alternative: keep a state for each row and collect it on Save. That spreads one save over many components and makes "Save disabled until something changed" hard to compute. The draft in the table gives one place for "changed", "breaks a rule" and the change set.

**D2. A pure module `configurationDraft.ts` for start text, rules and the change set.**
It exposes three functions, all of them unit-tested without rendering:

- `startText(setting)`: the text the control starts with, from `saved` when the row waits for a restart, else from `value`.
- `cellRule(setting, text)`: the rule message, or `null`.
- `changesOf(settings, draft)`: the `ConfigurationChanges` for the cells that differ from their start.

The existing `rangeRule`, `wholeNumberIn` and `numberIn` in `validation.ts` give the number rules.

**D3. Rules for empty fields.**
An empty field on an optional setting means `null`, so the server removes the key. An empty field on a setting that is not optional breaks the rule "Enter a value." and disables Save. This keeps today's behaviour, where `SettingRow` refuses to save an empty text. A rule shows under the field from the first keystroke, so the user sees why Save is disabled.

**D4. Edit mode belongs to the section, so only one table is open at a time.**
`ConfigurationView` holds `open: string | null` (the block name) and whether that table has changes. Edit on another block with no changes switches at once. With changes, a `Dialog` asks "Discard your changes to <Block>?" with the buttons "Keep editing" and "Discard". Leaving the tab unmounts the section, which drops the draft. That counts as Cancel.

**D5. Save, then lock, then restart once.**
On success the response replaces the cached listing (`useSaveConfiguration` already does this) and the table leaves edit mode. If any saved key has `applies: "restart"`, the restart dialog opens once. For one key it names that key. For more, it says "<n> changed settings" in plural. It adds the index identity note when a saved key starts with `chunking.`. On failure the draft stays and `SaveErrorNotice` shows under the card header. The 409 stale-revision message keeps its Reload action.

**D6. Header buttons.**
`CardHeader` holds the title on the left. On the right it holds Edit, or Cancel and Save in edit mode. Save is the primary button. It is disabled while nothing changed, while a cell breaks its rule, or while the request runs. A block with no editable row shows no Edit.

**D7. Read-only rows.**
The Value cell keeps the text and adds a lock icon. The icon has the reason as its accessible name and `title`, so a hover or a screen reader gives the reason outside edit mode as well. In edit mode a second table row with `colSpan` over all columns shows the reason in meta text. Key rows keep "Key set · ending XXXX".

**D8. Restart-pending rows.**
The Value cell shows the launch value, then "Next launch: <saved>" in meta text under it. When `saved` is `null`, it shows "Next launch: default". The Source cell shows the source words and the "Restart to apply" badge.

**D9. Phone width.**
The Source header and cells hide below the `sm` breakpoint. The first cell then shows the source words under the key. Keys use `[overflow-wrap:anywhere]`, so a long key wraps and does not push the page sideways. Controls in a cell use `w-full max-w-xs`.

**D10. Remove what becomes unused.**
`ConfigurationRow.tsx` goes away. The `SettingRow` props `kind`, `choices`, `min`, `max`, `saved` and `clearLabel` were added for Configuration only. Each prop that no other caller uses afterwards goes away too, with its tests. `SettingControl` stays and the table cells reuse it. The table cells pass the visible label as `aria-label`.

## Risks / Trade-offs

- [A long table in edit mode puts Save far from a cell near the bottom] → Blocks are small (largest about 25 rows). The card header stays in view for most blocks. A sticky header is a later option if it is needed.
- [A user edits two blocks and expects one save] → The discard prompt (D4) stops silent loss. The spec states that Save covers one table.
- [Losing the mini card check in `SettingsCards.test.tsx`] → The test changes to check that each setting row sits in a table inside a block card. The tab still has cards.
- [Tripwire web case count changes] → Re-pin `_WEB_EXTRA_CASES` with a comment, as in earlier changes.

## Migration Plan

This is a front-end change only. Rebuild `web/`, reinstall the live app from `v3` and restart it. To roll back, revert the merge commit and rebuild. `omrs.jsonc` and the server do not change.
