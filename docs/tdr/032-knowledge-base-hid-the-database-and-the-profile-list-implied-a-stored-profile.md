# TDR-032: The Knowledge Base hid the database and the profile list implied a stored profile, so name the database per collection and start the list on the stored profile

- **Date:** 2026-10-15
- **Status:** Accepted (OpenSpec change `add-vector-store-label-to-knowledge-base`; browser check at 390 px and 1200 px, light and dark)
- **Deciders:** Aizat
- **Tags:** web | knowledge-base | vector-store | registry | profile
- **Related:** [ADR-049](../adr/0049-lancedb-default-and-chroma-isolation.md), `openspec/changes/add-vector-store-label-to-knowledge-base/`

## Context

The Knowledge Base did not say which vector database holds a project. LanceDB is
the default and Chroma is an optional extra, so a user could not tell where the
data lives.

The Profile tab also misled. Its "New profile" list started on `documents`
(`useState<Profile>("documents")`). In the demo data the collection is also
called `documents`. The status line said "No profile is stored", but the list
showed `documents`, so it looked as if that profile was saved.

### Root Cause Analysis

Symptom: the header said "No profile" while the Profile tab showed `documents`.

Cause: two different things shared one word. "No profile" meant nothing is
stored (`storedProfile === null`). The list value was a default pick for a
change the user had not asked for. Nothing in the UI separated the two.

Not the cause: a wrong API value. `GET /v1/collections` returned `profile: null`
correctly.

## Decision

1. **Per-collection `store` field.** `GET /v1/collections` returns
   `store: {name, label}` for each collection. One server uses one database
   today, so every item holds the same value. A per-collection field means the
   API does not change if several databases are added.
2. **The registry owns the label.** `register(..., label=...)` takes an optional
   `label`. `describe()` returns it, or the registered name when none is given.
   `LanceDB` and `ChromaDB` are set in `core/vectordb/registry.py`.
3. **The route reads the name with `compose.configured_vector_store()`.** It is
   the approved way for a transport to read the adapter name. No property was
   added to the public `Engine` (architecture invariant 10).
4. **The logo is found by file name.** The web app loads
   `integrations/vector-stores/<registered name>.png`. The Chroma file is
   `chroma.png`, not `chromadb.png`, because `chroma` is the registered name. A
   missing file shows the label alone.
5. **Every logo sits on a white tile in a fixed `size-5` box.** The LanceDB logo
   is black on a transparent background and disappears in the dark theme.
   Inverting it would break the coloured Chroma logo, so the tile serves both.
6. **Where it shows.** Header and Home card: logo and name. Project list and the
   Sources table: name only. The Home card first showed text only; the logo was
   added at the user's request, because a card with an icon is easier to scan.
7. **Profile tab.** The list starts on the stored profile when it is `documents`
   or `codebase`, and otherwise starts empty with "Choose a profile". "Preview
   profile change" stays disabled until a profile is chosen. The status line
   always shows a badge, including the neutral "No profile" badge.
8. **Narrow screens.** The Source cell has `min-w-48` and the Database cell does
   not wrap. Without this, the new column squeezed Source to about 40 px at
   390 px. The table still scrolls sideways inside its own wrapper.

## Consequences

### Positive

- Users see where a project is stored.
- Adding a database needs one module, one `register()` call and one PNG.
- The Profile tab no longer suggests a stored profile that does not exist.
- The response never carries a path, URI, tenant or key.

### Negative

- Every web fixture that builds a collection needs the `store` field (about ten
  files).
- The Database column repeats one value on every row today.
- `configured_vector_store()` reads settings, not the live Engine. A test that
  injects a fake Engine must also patch it.

### Neutral

- The logo files belong to their owners. They are used unchanged and listed in
  `web/THIRD_PARTY_NOTICES.md`.
- The source files were PNG data with a `.webp` name. They are now `.png`.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| A new `Engine.store_name` property | It widens the public `Engine` API for a display value, and every fake Engine in the web tests would need it. |
| A `logo` argument on `register()` | It puts a web file name into `core/`. |
| A global `store` field on the collection list | It forces an API break when several databases arrive. |
| Invert the logo in the dark theme | It breaks the coloured Chroma logo. |
| Keep `documents` as the list default | It is the false impression this record fixes. |

## How to Recognise / Handle This Again

- Symptom: a new database shows no logo. Add `web/public/integrations/vector-stores/<registered name>.png`.
- Symptom: a new database shows its registered name in lower case. Pass `label=` to its `register()` call.
- Symptom: a logo is hard to see in one theme. Check that it sits on the white tile in `StoreBadge`.
- Re-evaluate when one server serves collections from more than one database. The `store` field is already per collection. The route then needs a per-collection lookup instead of `configured_vector_store()`.

## References

- `src/omrg/core/vectordb/registry.py`, `src/omrg/transports/api/routes_documents.py`, `src/omrg/transports/api/openapi.yaml`
- `web/src/components/StoreBadge.tsx`, `web/src/knowledge-base/{Project,SourceTable,SourcesSection,ProfilePanel}.tsx`, `web/src/components/CollectionPicker.tsx`, `web/src/home/HomeView.tsx`
- `docs/guides/web-workspace.md` ("Database and profile in the Knowledge Base")
- `openspec/changes/add-vector-store-label-to-knowledge-base/`
