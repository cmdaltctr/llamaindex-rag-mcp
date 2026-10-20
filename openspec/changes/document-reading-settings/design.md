## Context

See proposal.md for the motivation. The facts below set the approach.

- The nine keys are flat, top-level `Settings` fields. `pdf_reader` and the three gate fields are in `src/omrg/config/__init__.py`. The route and maths fields are in `src/omrg/config/ocr_routes.py`. Each environment name is the key in upper case (`pdf_reader` is `PDF_READER`).
- Code defaults: `pdf_reader` `pdf_inspector`, `ocr_fallback_enabled` `true`, `ocr_fallback_min_confidence` `0.5`, `ocr_fallback_page_fraction` `0.10`, `ocr_routing_unit` `document`, `ocr_engine_primary` `dots-mocr`, `ocr_engine_fallback` `paddleocr-vl`, `ocr_maths_routing_enabled` `true`, `ocr_maths_page_fraction` `0.10`.
- `pdf_reader` accepts `auto`, `liteparse`, `pdf_inspector`, `pypdfium2` and `pypdf`. At startup an unknown value only warns and falls back to `auto` (`Settings` model validator). An uninstalled reader logs an error and resolves to `pypdf` (`capabilities.resolve_pdf_reader`). `pdf_reader` is not in `config/rules.ACCEPTED`, so the file reader passes any text through to `Settings`.
- `ocr_routing_unit` is in `ACCEPTED` (`document`, `page`). An unknown unit raises at startup.
- An engine name is a folder name under `<ocr_workers_dir>/engines/`. `integrations/ocr_worker/routes.py` holds the rule `^[A-Za-z0-9][A-Za-z0-9._-]*$` and `resolve_engine_command(name, workers_dir)`, which returns an empty command when the name is invalid, the folder is unset, or the engine is not provisioned. A non-empty `OCR_WORKER_COMMAND` overrides the primary route only.
- `build_engine` resolves `EffectiveSettings` once. The OCR route clients are built once per engine, and the engine probe is cached per process. `transports/settings_view.applies()` already returns `restart` for all nine keys, and `restart_snapshot.capture()` already tracks them.
- All nine keys feed the index identity (`core/ingestion/source_state.py`): `pdf_reader` (the resolved name) in the `parser` block, the gate, unit, route fingerprints and maths fields in their own blocks.
- `config/settings_file_write.ALLOWED_KEYS` is `(*PROVIDER_FIELDS, *FILE_ONLY)`, 16 keys, pinned by `tests/unit/test_settings_file_write.py`. The writer treats `None` or a blank string as "remove the key".
- `transports/api/settings_store.refusal_response` maps `SettingsFileRefused` to 400, `SettingsFileConflict` to 409 and other write errors to 500. `GET/PUT /v1/settings/web-port` in `routes/mcp.py` is the pattern to copy.
- The page has eight sections (`web/src/lib/routes.ts` `SETTINGS_SECTIONS`). The baseline spec lists seven.

## Goals / Non-Goals

**Goals:**

- One section edits the nine keys, with the value in force, the saved value, the source, the default and the availability of each choice.
- One exact HTTP contract, so the backend and the web front end can be built in parallel without contact.
- Write-time checks that stop a value the startup path would quietly replace.

**Non-Goals:**

- Live apply of any of the nine keys.
- Any change to how a value is resolved at startup, to the OCR routes, or to the index identity payload.
- Editing `ocr_workers_dir`, `ocr_worker_command` or any other OCR field. Provisioning engines.
- A "no fallback engine" choice (D8).
- Per-profile or per-pipeline reading settings.

## Decisions

### D1. Every key applies at the next launch only

All nine keys keep applying after a restart. `EffectiveSettings` is frozen per launch (ADR-037). The OCR route clients and the engine probe are built once per process. A live apply would need a new engine generation, a rebuild of the route clients and a cache reset, while ingest jobs may run against the old routes.

The page states this in the section header and on each changed row ("Restart to apply"). After a save that leaves any row with `restart_pending: true`, the page opens the existing `RestartDialog`. The page also states that the nine keys are part of the index identity, so after the restart the next ingest can read existing files again.

Rejected: rebuild the engine on save. It breaks the frozen-settings rule, it races with running jobs, and the user can restart in one click from the dialog.

### D2. A dedicated route pair, not a generic settings write

`GET` and `PUT /v1/settings/document-reading` hold only the nine keys, as `web-port` and `upload-limit` hold one key each. The route refuses every other key with 400, even a key that `ALLOWED_KEYS` permits.

Rejected: a generic `PUT /v1/settings/configuration` for any key. It widens the write surface to every setting, each with its own restart and identity effects.

### D3. Write-time checks only; startup unchanged

The new checks run only on a page write.

- `config/rules.py` gains `PDF_READER_NAMES = ("auto", "liteparse", "pdf_inspector", "pypdfium2", "pypdf")`. The `Settings` validator uses the constant in place of its inline tuple. Its behaviour stays the same (warn, fall back to `auto`). `pdf_reader` does not go into `ACCEPTED`, because the file reader would then ignore a bad file value and use the code default `pdf_inspector`, which changes the startup behaviour.
- `config/rules.py` gains `ENGINE_NAME_PATTERN` (the same pattern as `routes._ENGINE_NAME_RE`) and a 64-character limit for a page write. `config/` is a leaf and cannot import `integrations/`, so a test pins the two patterns equal.
- `config/rules.py` gains one function that returns the write rule a document-reading value breaks, or `None`. `settings_file_write._plan` calls it for the nine keys before its "blank means remove" step and before `check_setting`, so a blank string for one of the nine keys is refused (D7). `null` still removes the key. The function checks the JSON type strictly: a boolean key takes `true` or `false` only, a fraction key takes a JSON number only (not a boolean, not text), and a text key takes text only.
- `ALLOWED_KEYS` gains the nine keys (16 becomes 25).

### D4. An uninstalled PDF reader is refused; an unprovisioned OCR engine is allowed

The route refuses `pdf_reader` set to a reader that `capabilities.pdf_reader_options()` reports as not installed (400). At startup such a value silently becomes `pypdf`, and the user would read every document with a reader they did not choose. `auto` is always allowed.

The route allows an OCR engine name that matches the rule but is not provisioned. The OCR design (D3 of `modular-ocr-workers-dots-mocr`) treats an unavailable route as normal: the fallback serves, or no OCR runs. The user may also provision the engine before the restart. The page marks such a choice "Not provisioned" with the reason.

The probe of the reader is a route-layer check, because `config/` must not probe packages. It runs in the route before the write.

### D5. Engine list

`ocr.engines` is the sorted, de-duplicated union of:

1. each folder name under `<ocr_workers_dir>/engines/` that matches the engine-name rule, and
2. the non-empty in-force and saved values of `ocr_engine_primary` and `ocr_engine_fallback`.

Each entry is probed now with `resolve_engine_command(name, workers_dir)`, where `workers_dir` is the launch value of `ocr_workers_dir`. The list is empty when `ocr_workers_dir` is unset and no engine value is set. A new function in `capabilities.py` does the scan and the probe, so the route stays thin. If `capabilities.py` would pass 500 lines, put the function in a new `capabilities_ocr.py`.

### D6. Locked keys

A key whose launch source is `env` or `dotenv` is locked. The row is read-only with `lock_reason` "Remove PDF_READER from the environment or .env to edit it here." (the environment name of that key). A `PUT` that names a locked key, with any value including `null`, gets 409 with the same message and writes nothing. When several keys are locked, the message names the first in the contract order (D10).

### D7. Blank text is refused; `null` resets

The writer reads a blank string as "remove the key". For `ocr_engine_fallback` a user could read a blank as "no fallback", but the result is the default `paddleocr-vl`. So the route refuses a blank or whitespace-only string with 400, and the page sends `null` to return a key to its default. `null` removes the key from `omrg.jsonc`.

### D8. Deferral: "no fallback engine"

The page cannot set `ocr_engine_fallback` to empty, because the writer removes a blank key. A later change can add an explicit value (for example `"none"`) with its own rule in `routes.py`. Until then, a user who wants no fallback sets `OCR_ENGINE_FALLBACK=` in `.env` (the row is then locked) or writes `"ocr_engine_fallback": ""` in the file by hand. The page shows a saved empty value as "None (no fallback)".

### D9. Index identity note and docs

The page shows one note for the section: "These settings are part of the index identity. After a restart, the next ingest can read existing files again." The configuration guide's identity table lists the OCR keys but not `PDF_READER`, although the resolved reader is in the `parser` block. The backend adds a `PDF_READER` row to that table.

### D10. HTTP contract

Both routes live in a new module `src/omrg/transports/api/routes/document_reading.py`, registered in `app.py`. A framework-free builder (`src/omrg/transports/api/document_reading.py`) assembles the body from the launch state on `app.state.configuration` (the same `ConfigurationState` the Configuration route reads), the current file and the probes. When `app.state.configuration` is missing (the handover failed), the builder uses `compose.get_settings()` for the launch values and the current file as the snapshot, so no row is pending. This matches the Configuration route.

**Key order.** Every list of keys, and the lock precedence, use this order:

1. `pdf_reader`
2. `ocr_fallback_enabled`
3. `ocr_fallback_min_confidence`
4. `ocr_fallback_page_fraction`
5. `ocr_routing_unit`
6. `ocr_engine_primary`
7. `ocr_engine_fallback`
8. `ocr_maths_routing_enabled`
9. `ocr_maths_page_fraction`

**Value types.**

| Key | JSON type | Rule on write |
| --- | --- | --- |
| `pdf_reader` | string | One of `auto`, `liteparse`, `pdf_inspector`, `pypdfium2`, `pypdf`, and installed unless `auto` |
| `ocr_fallback_enabled` | boolean | `true` or `false` |
| `ocr_fallback_min_confidence` | number | 0.0 to 1.0 inclusive |
| `ocr_fallback_page_fraction` | number | 0.0 to 1.0 inclusive |
| `ocr_routing_unit` | string | `document` or `page` |
| `ocr_engine_primary` | string | Matches `^[A-Za-z0-9][A-Za-z0-9._-]*$`, 1 to 64 characters |
| `ocr_engine_fallback` | string | Same as `ocr_engine_primary` |
| `ocr_maths_routing_enabled` | boolean | `true` or `false` |
| `ocr_maths_page_fraction` | number | 0.0 to 1.0 inclusive |

A JSON integer (`0`, `1`) is a valid number. Any key may be `null` in a write, which removes it from the file.

#### `GET /v1/settings/document-reading`

Scope: read (the `ReadScope` dependency, as `GET /v1/settings/web-port`). Response 200:

```json
{
  "status": "ok",
  "revision": "9f2c…e1",
  "settings": [
    {
      "key": "pdf_reader",
      "value": "auto",
      "saved": "liteparse",
      "source": "config-file",
      "locked": false,
      "lock_reason": null,
      "restart_pending": true,
      "default": "pdf_inspector"
    },
    {
      "key": "ocr_fallback_enabled",
      "value": true,
      "saved": null,
      "source": "env",
      "locked": true,
      "lock_reason": "Remove OCR_FALLBACK_ENABLED from the environment or .env to edit it here.",
      "restart_pending": false,
      "default": true
    }
  ],
  "pdf_readers": [
    { "name": "auto", "available": true, "reason": null },
    { "name": "pypdf", "available": true, "reason": null },
    { "name": "pypdfium2", "available": false, "reason": "The package 'pypdfium2' is not installed." },
    { "name": "liteparse", "available": true, "reason": null },
    { "name": "pdf_inspector", "available": true, "reason": null }
  ],
  "pdf_reader_in_use": "liteparse",
  "ocr": {
    "workers_dir": "~/ocr-workers",
    "worker_command_set": false,
    "engines": [
      { "name": "dots-mocr", "available": true, "reason": null },
      { "name": "paddleocr-vl", "available": false, "reason": "Not provisioned. Run python3 ocr-workers/provision.py paddleocr-vl." }
    ]
  }
}
```

The example shows two of the nine `settings` entries. A real response always holds all nine, in the key order.

| Field | Type | Meaning |
| --- | --- | --- |
| `status` | `"ok"` | Success envelope |
| `revision` | string | SHA-256 hex of `omrg.jsonc`, or `"absent"` when there is no file. Send it back on `PUT` |
| `settings` | array of 9 objects | One per key, in the key order |
| `settings[].key` | string | One of the nine keys |
| `settings[].value` | per value-type table | The value in force since this launch (launch `Settings`). For `pdf_reader` this is the configured name, which can be `auto` |
| `settings[].saved` | per value-type table, or `null` | The valid value `omrg.jsonc` holds now. `null` when the file does not set the key, or holds a value that breaks its rule (the Configuration section lists that problem). For `ocr_engine_fallback`, a hand-written `""` comes back as `""` |
| `settings[].source` | `"env"` \| `"dotenv"` \| `"config-file"` \| `"default"` | Source of `value` at launch. `yaml` and `init` read `default` |
| `settings[].locked` | boolean | `true` when `source` is `env` or `dotenv` |
| `settings[].lock_reason` | string or `null` | `"Remove <ENV_NAME> from the environment or .env to edit it here."` when locked, else `null` |
| `settings[].restart_pending` | boolean | The file value differs from the value captured at launch, and the key is not locked |
| `settings[].default` | per value-type table | The code default from the `Settings` model |
| `pdf_readers` | array | `auto` first (always available, `reason: null`), then each registered reader in the order `capabilities.pdf_reader_options()` returns |
| `pdf_readers[].name` | string | Reader name |
| `pdf_readers[].available` | boolean | The reader's package imports |
| `pdf_readers[].reason` | string or `null` | Why it cannot run (names the missing package), `null` when available |
| `pdf_reader_in_use` | string or `null` | The reader the running engine uses after resolution (`auto` resolved, an uninstalled choice replaced by `pypdf`). Computed once per process with `capabilities.resolve_pdf_reader` on the launch `Settings`. `null` only when it cannot be computed |
| `ocr.workers_dir` | string or `null` | Launch `ocr_workers_dir` with the home folder as `~`, or `null` when unset |
| `ocr.worker_command_set` | boolean | Launch `ocr_worker_command` is not empty, so it replaces the primary engine |
| `ocr.engines` | array | Sorted by `name` (D5) |
| `ocr.engines[].name` | string | Engine folder name |
| `ocr.engines[].available` | boolean | `resolve_engine_command` returns a command now |
| `ocr.engines[].reason` | string or `null` | `null` when available. Otherwise one of: `"OCR_WORKERS_DIR is not set, so no OCR engine can run."`, `"The name is not a folder name."`, `"Not provisioned. Run python3 ocr-workers/provision.py <name>."` |

Errors: 401 or 403 from the session check, as for every route.

#### `PUT /v1/settings/document-reading`

Scope: manage (a browser session, the `ManageScope` dependency of `routes/mcp.py`). Body:

```json
{
  "values": { "pdf_reader": "liteparse", "ocr_fallback_page_fraction": 0.2, "ocr_engine_fallback": null },
  "revision": "9f2c…e1"
}
```

| Field | Type | Rule |
| --- | --- | --- |
| `values` | object | 1 to 9 members. Each member name is one of the nine keys. Each value has the key's JSON type, or is `null` (remove the key, so the default applies) |
| `revision` | string | Required, at most 128 characters. The `revision` of the last read |

No other top-level field is allowed. All members land in one file write, or none do.

Response 200: the same body as `GET`, read after the write, with the new `revision`.

The server checks in this order and stops at the first failure. Nothing is written on any failure.

| Step | Status | `message` |
| --- | --- | --- |
| 1. Body shape (missing `revision`, extra field, `values` not an object, empty `values`, more than 9 members) | 400 | The framework validation text (`Invalid request. …`), which names the field and never the value |
| 2. A member name that is not one of the nine keys | 400 | `<key> is not a document reading setting.` |
| 3. A member names a locked key | 409 | `Remove <ENV_NAME> from the environment or .env to edit it here.` (first locked key in the key order) |
| 4. A value breaks its rule (type, range, choice, name rule, blank text) | 400 | `<key>: <rule>`, for example `ocr_fallback_page_fraction: The value must be a number from 0.0 to 1.0.`, `pdf_reader: The value must be one of: auto, liteparse, pdf_inspector, pypdfium2, pypdf.`, `ocr_engine_primary: The engine name must start with a letter or digit, hold only letters, digits, dots, hyphens and underscores, and be at most 64 characters.`, `ocr_engine_fallback: The value must not be blank. Send null to use the default.` |
| 5. `pdf_reader` names a reader that is not installed | 400 | `pdf_reader: This PDF reader is not installed. Install its package, then save again.` |
| 6. The file changed since `revision` | 409 | `omrg.jsonc changed on disk. Reload to see the new values.` |
| 7. The file cannot be parsed, or a key appears twice | 409 | `omrg.jsonc could not be read. Fix it, then save again.` |
| 8. The disk refuses the write | 500 | `omrg.jsonc could not be written.` |

Every error body is `{"status": "error", "message": "<text>"}`. No message holds a submitted value. Steps 6 to 8 reuse `refusal_response`.

`openapi.yaml` gains the two operations (`getDocumentReadingSettings`, `setDocumentReadingSettings`) and the schemas `DocumentReadingState`, `DocumentReadingSetting`, `ReaderOption`, `OcrEngineOption` and `DocumentReadingUpdate`.

### D11. The web section

- `SETTINGS_SECTIONS` becomes `appearance, providers, chat, mcp, log, runtime, workspace, document-reading, configuration`. The chip label is "Document reading". The address is `#/settings/document-reading`.
- The section reads the route through a query keyed `["settings", "document-reading"]`, so `reloadSettings` covers it. The read and the write go through `rememberRevision` and `settingsWritten`.
- One row per key, through the existing `SettingRow`. Controls: a select for `pdf_reader` (unavailable readers disabled, with the reason), a switch for each boolean, a select for `ocr_routing_unit`, a select of `ocr.engines` for each engine key (unprovisioned names allowed, marked "Not provisioned"), and a number input from 0 to 1 for each fraction. Each row offers "Use default", which sends `null`.
- The section shows: the restart note, the index identity note (D9), `pdf_reader_in_use` when it differs from `value`, a notice on the primary engine row when `ocr.worker_command_set` is `true`, and a note that a Read document step in a pipeline can choose its own reader.
- A failed save shows `SaveErrorNotice` with the server message. A 409 offers Reload.

## Risks / Trade-offs

- [The `pdf_reader` list in `config/rules.py` can drift from the PDF registry] → A test asserts that `PDF_READER_NAMES` minus `auto` equals the registry names.
- [The engine-name pattern exists twice] → A test asserts that `ENGINE_NAME_PATTERN` equals `routes._ENGINE_NAME_RE.pattern`.
- [A save starts a full re-read of existing files at the next ingest] → The page says so before and after a save. The restart is the user's choice.
- [Engine availability is probed now, while the running routes were built at launch] → The page shows availability as a guide for the next launch, which is what a choice needs.
- [A reader installed after a save can be removed before the restart] → Startup keeps its existing fallback to `pypdf` with an error in the log.
- [Two agents build in parallel] → D10 is the only contract. The web group owns no backend file, and the backend group owns no web file. The integrator re-measures the tripwire once.

## Migration Plan

No data migration. A file without the nine keys keeps its current behaviour. Rollback: revert the change. Keys the page wrote stay valid in `omrg.jsonc`, and an older build reads them as before.

## Open Questions

None.
