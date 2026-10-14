# Frontend scaffold (task 6.8 packaging part, task 7.1)

Date: 2026-10-13. The user approved creating `web/` with npm and the listed frontend dev dependencies.

## Scope

- `web/` holds a React, Vite and TypeScript application.
- `npm run build` writes to `src/omrg/transports/api/static/` (`emptyOutDir: true`, `base: "./"`).
- The build directory is gitignored. The lead adds the Hatch force-include and the wheel smoke test.
- The app has seven placeholder views, semantic theme tokens, a theme control, an inspector region and a `/v1` client stub.
- The canvas editor (task 7.2) is not built. It needs the backend catalogue.

## Dependencies

All versions are exact pins. Each version was released on or before 2026-09-29, at least two weeks before this date.

| Package | Version | Kind |
|---|---|---|
| react, react-dom | 19.3.0 | runtime |
| @xyflow/react | 12.12.0 | runtime (installed for task 7.2, not yet imported) |
| vite | 8.3.1 | dev |
| @vitejs/plugin-react | 6.1.1 | dev |
| typescript | 6.0.3 | dev |
| vitest | 5.0.2 | dev |
| jsdom | 30.1.1 | dev |
| eslint | 10.11.0 | dev |
| @eslint/js | 10.0.1 | dev |
| typescript-eslint | 8.71.0 | dev |
| eslint-plugin-react-hooks | 7.1.1 | dev |
| globals | 17.12.0 | dev |
| @testing-library/react | 16.3.3 | dev |
| @testing-library/dom | 10.4.2 | dev |
| @testing-library/user-event | 14.6.7 | dev |
| @testing-library/jest-dom | 7.0.1 | dev |
| @types/react, @types/react-dom | 19.3.0 | dev |

TypeScript is 6.0.3, not the newer 7.0.2. The reason is that `typescript-eslint` 8.71.0 declares the peer range `typescript >=4.8.4 <6.1.0`.

`npm install` added 252 packages. `package-lock.json` is lockfile version 3 and has no range specifiers for direct dependencies. Node 26.10.0 and npm 11.19.1 were used. `engines.node` is `>=22.12.0`, which is the Vite 8 floor.

## Test-first record

1. I wrote the tests first: `src/App.test.tsx`, `src/theme.test.tsx` and `src/api/client.test.ts`.
2. Run 1 had no implementation modules. Result: 3 files failed at import, so no tests ran.
3. Run 2 used minimal stubs: an empty `<main/>` and a client that called `response.json()` directly. Result: 32 failed, 1 passed. The test that passed is the JSON happy path, which the naive stub already handles.
4. After implementation, all 33 tests passed.

### Mutation checks

Each check broke one guard, ran the full suite, then restored the guard.

| Mutation | Result |
|---|---|
| Remove the content-type check in `getJson` | 3 failed |
| Write to `localStorage` without try/catch | 2 failed |
| Remove the inspector Escape handler | 1 failed |
| Stop persisting UI state | 3 failed |

## Test coverage (33 tests, Vitest with jsdom)

- **Navigation:**
  - Seven links appear in order: Canvas, Library, Search, Ask, Runs, Experiments, Settings.
  - Each view has an H1 heading, `aria-current="page"` and an empty state.
  - The view follows the address hash.
  - The last view is restored after a reload.
- **Theme:**
  - The default is `system`, with no `data-theme` attribute.
  - Light and dark persist after a reload.
  - The user can return to `system`.
  - A theme change keeps the current view.
  - Corrupt JSON and values outside the allowed set fall back to defaults.
  - The app works when `getItem` and `setItem` throw.
  - The app works when the `localStorage` getter itself throws.
- **Inspector:**
  - Enter and Space toggle it, and `aria-expanded` follows.
  - Escape closes it and returns focus to the toggle.
  - Its state persists across navigation and reloads.
- **API client:**
  - A JSON response passes, and the request sends `Accept: application/json`.
  - An HTML 200 response and an HTML 404 response are rejected as `not-json`. The client does not parse them.
  - A response with no content type is rejected.
  - An error envelope message is reported as an `http` error.
  - Malformed JSON is reported as `invalid-json`.
  - A network failure is reported as `network`.
  - Paths outside `/v1/` are refused before fetch is called, including absolute URLs and `..` traversal.

## Commands

All commands ran in `web/`.

| Command | Result |
|---|---|
| `npm run lint` | PASS, exit 0 |
| `npm run typecheck` | PASS, exit 0 |
| `npm test` | PASS, 3 files, 33 tests |
| `npm run build` | PASS. Output: `index.html` 0.46 kB, CSS 8.58 kB (2.28 kB gzip), JS 226.05 kB (70.71 kB gzip). Total 240 KiB on disk. |
| Two consecutive builds, SHA-256 of every output file | PASS, identical |
| `git check-ignore` on `web/node_modules` and the static directory | PASS, both ignored |

The built `index.html` references `./assets/...`, so the asset URLs are relative.

## Browser layout check

Method:

- `vite preview` served the production build on loopback.
- Chrome DevTools MCP loaded the build in an isolated context, using viewport emulation. No browser was installed.
- Each case measured horizontal page overflow, the inspector position and whether the inspector actions were reachable.

| Width | Themes | Inspector | Result |
|---|---|---|---|
| 1280 | light, dark | closed and open | PASS. No overflow. The inspector is a third grid column (960 to 1280 px). |
| 768 | light, dark | closed and open | PASS. No overflow. The inspector is a fixed overlay at the inline end. Close is reachable. |
| 390 (mobile, touch) | light, dark | closed and open | PASS. No page overflow. Navigation scrolls inside its own strip. Links and buttons are 44 px high. |
| 320 (mobile, touch) | light, dark | closed and open | PASS. No overflow. The inspector fills the width. Close, toggle and the theme control stay in view. |
| 1280 with `dir="rtl"` | light | open | PASS. Navigation moves to the right and the inspector moves to the left, with no rule changes. |

I viewed one screenshot (1280, light, inspector open) inline. The DevTools server cannot write files into the worktree, so no image is saved.

## Contrast

These are computed WCAG ratios for the token pairs, using the composite background where the colour is translucent.

| Pair | Light | Dark |
|---|---|---|
| Main text on canvas | 11.20 | 11.07 |
| Secondary text on muted or elevated | 6.24 / 6.30 | 5.32 / 5.27 |
| Tinted button label on strongest tint | 4.52 | 5.34 |
| Text on selected navigation fill | 9.27 | 7.24 |
| Focus ring on muted or elevated | 4.77 / 4.81 | 5.99 / 5.93 |

Adaptation: the dark tinted label first used `#eb8c57`, which gave 4.48. I changed it to the source's dark pressed accent, `#fd9b66`.

Open finding: control borders (`--border`, and `--border-hover` at 1.57 light and 2.16 dark) are below 3:1 against their fill. The source palette has the same values. Controls stay identifiable by their label and fill. Decide this when shared controls are styled in task 7.2.

## Attribution

`web/THIRD_PARTY_NOTICES.md` carries the OpenChamber MIT notice for the adapted palette and geometry. `web/src/styles/tokens.css` points to it.

## Not run or partial

- **NOT RUN:** keyboard and focus walk-through in a real browser. jsdom tests cover the toggle, Escape and focus return.
- **NOT RUN:** 200% zoom.
- **NOT RUN:** OS-level reduced-motion emulation. The CSS rule is present.
- **NOT RUN:** Arabic prose content check. No translated content exists yet.
- **NOT RUN:** wheel install outside the checkout. This is the lead's job (task 6.8, second half).
- **PARTIAL (7.1):** draft state covers view, inspector and theme only. Canvas draft and run identity arrive with tasks 7.2 and 7.3.

## Task 6.8 wheel packaging (lead, 2026-10-13)

- `pyproject.toml` `[tool.hatch.build.targets.wheel] artifacts = ["src/omrg/transports/api/static/**"]` ships the gitignored build output when present.
- `scripts/check_web_wheel.py WHEEL` fails release preparation when `omrg/transports/api/static/index.html` or any `./assets/` file it references is missing. Checked both ways: built wheel exit 0; the same wheel with `static/` stripped exit 1 with the `npm ci && npm run build` hint.
- Installed-wheel smoke outside the checkout: `uv build --wheel` into the scratchpad, then installed with `uv pip install --offline --no-deps` into a fresh scratch venv (dependencies resolved from the worktree venv through a `.pth`; the worktree's editable `omrg` is not importable that way). Ran from `/tmp` with `env -i PATH=/usr/bin:/bin` and `shutil.which("node") is None` asserted.
  - `omrg` imported from the scratch venv `site-packages`, not the checkout.
  - Real Uvicorn socket with a fake Engine: `GET /` 200 HTML; both referenced assets 200 (`text/javascript`, `text/css`); SPA route `/library` 200 HTML; `/v1/health` 200 JSON; unknown `/v1/no-such-route` 404 JSON error envelope, no HTML.
  - Result: WHEEL SMOKE PASS.
- Limitation: a fully offline `uv pip install "omrg[web]"` from the lock was not possible because the local uv cache lacks some locked wheels (for example `aiohttp 3.14.3`). The dependency set itself is checked by `uv lock` and the floors test (see `web-dependency.md`). A networked clean install is left to CI or task 9.2.
