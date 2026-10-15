# ADR-077: Web Workspace Client Foundation

- **Date:** 2026-10-15
- **Status:** Accepted (2026-10-15; evidence: `npm run lint`, `typecheck`, `test` (78 files, 816 tests) and `build` pass; guard tests `noLegacyResidue`, `cascade`, `gridColumns`, `design-md` and `App.failures` pass; visual matrix at 1280 px and 390 px in both themes)
- **Deciders:** Dr Muhammad Aizat Bin Md Hawari
- **Related:** [ADR-075](075-omrg-owned-pipeline-runner-local-web-packaging-and-external-tool-plugins.md) (local web runtime), [ADR-076](076-serve-mcp-from-the-web-server-with-a-lifespan-provided-engine.md) (MCP on the web server)
- **Change:** `openspec/changes/redesign-web-workspace/` (design D6, D9 to D13)

## Context

The first web workspace grew view by view. Each API module had its own
`sendJson`, `postJson` and `isJson` copy. Components took `fetchImpl` props.
Errors travelled as strings, so parser and status text reached the screen.
Each view loaded its own data, so an upload did not refresh the collection
counts on other views. The current view, project and pipeline lived in
browser storage beside the URL, so the two could disagree. 1,413 lines of
hand-written CSS sat in a `legacy` layer beside the Tailwind primitives.

The redesign rebuilds every view into seven areas. Without one foundation,
each rebuilt view would copy the same faults again.

## Decision

The web client has one foundation, and no code from the old one remains.

1. **One API client with typed errors.** `api/client.ts` has one
   `request<T>(method, path, { query, body, signal })`. It throws `ApiError`
   with a `kind` (`invalid-path`, `network`, `not-json`, `invalid-json`,
   `http`) and a `status`. `ApiProvider` sets the fetch implementation once,
   through React context. `lib/errors.ts` `describeError` turns every error
   into one friendly line and one action. The raw message goes to the
   console only.
2. **One cache for server state.** `@tanstack/react-query` v5 (pinned at
   `5.104.2`, owner approval 14 October 2026) holds all server data.
   `api/queries.ts` declares each read once, with a hierarchical key. Each
   mutation declares the keys it invalidates. Answers and searches are
   mutations, because each submission is a new request. Run event streams
   stay on SSE, and invalidate `["runs", id]` and `["runs"]` on a terminal
   event.
3. **The URL is the only record of location.** `lib/routes.ts` has a typed
   `Route` union, `parseRoute` and `formatRoute`. A hash that does not parse
   goes to `#/home`. There are no redirects for old hashes.
4. **Browser storage holds preferences and drafts only.** `lib/storage.ts`
   keeps two kinds of key: `omrg-preferences` (`theme`, `lastCollection`)
   and `omrg-canvas-draft:<pipeline-id>`. A value that fails its validator is
   removed. Values have no version field and are never migrated.
5. **Presentation uses only primitives and utilities.** Every view uses
   `web/src/components/ui/` and Tailwind utilities over the token bridge.
   `legacy.css` and the per-view stylesheets are deleted. Only `tokens.css`
   and `app.css` remain. `noLegacyResidue.test.ts` fails on any retired
   helper, storage key or class name.
6. **Settings shows server settings and does not edit them.** Connections
   are read-only (`GET /v1/connections`, built by
   `compose.connection_summary()`) with a manual reachability test. The
   server log is an in-memory ring buffer of 1,000 records, redacted before
   a record enters it.

The workspace is pre-release, so routes, stored state and stylesheets are
replaced, not migrated.

## Consequences

### Positive

- An upload, deletion or finished ingest job refreshes every view that shows
  the data, through one invalidation.
- No parser or status text reaches the screen. `App.failures.test.tsx`
  checks every area.
- Back, forward and bookmarks work, because the URL alone sets the view.
- Guard tests stop old helpers, keys and CSS from coming back.

### Negative

- One new runtime dependency in `web/`.
- Bookmarks to the old hashes open Home.
- Stored UI state from earlier builds is removed on first read.
- Connections cannot be edited in the browser until `add-runtime-settings`
  lands.

### Neutral

- Tests make a fresh `QueryClient` per test with `retry: false`, and build
  the API client from fixture servers through `ApiProvider`.
- The server log can show local file paths. Only a browser session on the
  loopback server can read it.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| **A hand-written keyed cache** | It would re-implement deduplication, invalidation, retry and stale handling with weaker guarantees. |
| **A router library** | The app has eleven hash routes. A typed union with two round-trip-tested functions covers them. |
| **Keep view state in storage beside the URL** | Two sources of location can disagree. The open pipeline comes from the route, and the latest run from the server. |
| **Versioned storage with migrations** | The app is pre-release. A changed shape resets to defaults. |
| **Restyle the old views instead of rebuilding** | The `legacy` layer and its 1,413 lines would stay. |
| **Edit connections in Settings now** | Editing needs settings-file precedence, safe Engine rebuilds and an embedding-model lock per collection. That is the separate change `add-runtime-settings`. |

## References

- `web/src/api/client.ts`, `web/src/api/ApiProvider.tsx`, `web/src/api/queries.ts`, `web/src/api/mutations.ts`
- `web/src/lib/errors.ts`, `web/src/lib/routes.ts`, `web/src/lib/storage.ts`
- `web/src/styles/noLegacyResidue.test.ts`, `web/src/App.failures.test.tsx`
- `src/omrg/compose_connections.py`, `src/omrg/transports/api/routes_connections.py`, `src/omrg/transports/api/log_buffer.py`
- `docs/guides/web-workspace.md`, `web/DESIGN.md`
