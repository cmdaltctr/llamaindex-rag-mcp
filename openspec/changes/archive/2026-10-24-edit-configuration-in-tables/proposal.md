# Proposal

## Why

Settings › Configuration shows each of its 121 settings as a mini card with its own Edit, Save and Cancel. The page is long and slow to scan, and changing three settings in one block takes three separate saves. The user asked for the earlier table layout back, with one edit mode for each table.

## What Changes

- Each block of Settings › Configuration (General, Retrieval, Chunking, Ocr and the others) shows a table with the columns Setting, Value and Source again. The table sits in the block card, so every Settings tab still uses cards.
- Each block card has one Edit button at its top right. Edit unlocks every editable Value cell in that table. Save and Cancel replace Edit in the same place.
- In edit mode a Value cell holds only its control (switch, number field, choice list or text field) and its rule, such as "Enter 1 to 100.". Rows have no buttons of their own.
- Save sends every changed cell of the table in one `PUT /v1/settings/configuration` request. The server writes all of them or none. After a good save the table locks again, and the restart dialog opens once when a saved setting applies at restart.
- Save stays disabled until a cell changes, and while a cell breaks its rule.
- Cancel throws away every change in the table and locks it.
- A read-only row keeps its value as text and shows a lock icon. In edit mode its reason shows on a line under the row.
- An optional setting is cleared by emptying its box. The Clear button goes away.
- Only one table is in edit mode at a time. Edit on a second table while the first has changes asks whether to discard them.
- A row waiting for a restart shows "Next launch: <value>" under the value and "Restart to apply" in the Source cell.
- At phone width the Source column moves under the setting name, so the table has two columns.
- The Document reading tab keeps its cards. The server, the route and the OpenAPI contract do not change.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `workspace-settings`: the requirement "The Configuration section lists every setting" changes from one mini card with its own Edit per setting to one table per block with a table-wide edit mode and one save for the block.

## Impact

- Web: `web/src/settings/ConfigurationSection.tsx`, a new table component for one block, and a pure draft module for typed values, rules and the change set. `ConfigurationRow.tsx` goes away. `SettingRow` loses the props that only the Configuration rows used.
- Tests: `ConfigurationSection.test.tsx`, `SettingsCards.test.tsx` and the clean-base tripwire web case count.
- Docs: `docs/guides/web-workspace.md` (Configuration) and `.agents/skills/omrs-design/references/screens.md`.
- No change to the server, `PUT /v1/settings/configuration`, `openapi.yaml`, ADR-095 or any Python test.
