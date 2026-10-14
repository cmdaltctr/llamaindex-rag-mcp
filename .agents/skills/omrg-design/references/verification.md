# Verification

## Documentation-only work

For edits to this skill, check the frontmatter, relative links, source paths, and examples. Check that each cited file still exists. Re-check the palette against `web/src/styles/tokens.css`. Re-run the contrast calculation if a token changes. This shows the guidance is usable. It does not show that any screen passes. Do not report a visual matrix as passed after documentation-only work.

## Source checks for a UI change

Run commands from `web/` with an explicit working directory. The scripts are in `web/package.json`.

```bash
cd web
npm run lint
npm run typecheck
npm run test
npm run build
```

Run one test file while you work:

```bash
cd web && npx vitest run src/components/ui/button.test.tsx
```

Backend changes in the redesign (experiment folders, `GET /v1/integrations`) use the Python gate from the repository root:

```bash
uv run pytest -m "not slow"
```

Ask before you run a full suite or `./scripts/local_ci.sh`. Run `openspec validate <change-name> --strict` for the change you touched.

Test rules:

1. Write the test before the change. Confirm it fails against the old code, then make it pass.
2. After you write a test, break the code under test and confirm the test fails.
3. Prove the token bridge with computed styles: render a fixture that uses a bridged utility, and assert the computed colour equals the `tokens.css` value in light and dark. jsdom does not apply Tailwind, so use a real browser for this check, or test the CSS output (`web/src/styles/bridge.test.ts` does this with Tailwind's `compile`). Vitest blanks CSS imports, so tests read CSS source with `?raw`; `vite.config.ts` sets `test.css.include` to allow it. When you touch stylesheets or class names, run `cascade.test.ts` and `tokens.test.ts`, and compare computed styles and element boxes against a baseline build in light and dark at 1280px and a real 390px viewport (emulate it; the Chrome window cannot go below 500px).
4. Keep Radix keyboard flows tested: open, Escape, focus return.

## Coexistence checks for `add-web-ui-stack`

1. No existing view imports a new primitive (task 3.4). Search imports of `components/ui`.
2. One pre-existing view renders pixel-identical before and after (task 3.1). Capture both at the same theme, width, and data.
3. The legacy tests stay green with no edits.

## Run the correct app

`npm run dev` starts Vite. The `/v1` proxy forwards to the local web transport (default `http://127.0.0.1:8000`, overridable by environment variable). Read `web/vite.config.ts` for the variable name. Confirm the page loads styles from the checkout you are editing.

The transport needs a one-time browser session. Read `docs/guides/web-workspace.md` ("Sign in") before you start. If the Vite origin cannot hold a session, build with `npm run build` and serve the built app through `omrg web`. The build writes to `src/omrg/transports/api/static/`, which is gitignored.

Start a throwaway server. Never point it at the real workspace or real documents:

```bash
omrg web --workspace <scratch>/ws --root <scratch>/docs --experiment-root <scratch>/exp
```

Use the scratch directory from the session, not `/tmp`. Fill `<scratch>/docs` with synthetic files. One server holds one workspace lock, so stop any other server on the same path first. Do not restart a server the user is running. Keep secrets, one-time credentials, and private documents out of screenshots and reports.

Chat needs a working answer pipeline. If no model is configured, use the fixture servers in `web/src/**/test/*Server.ts` for component tests, and mark the live Chat check `BLOCKED` with the reason. Do not fake an answer to pass a check.

## Screens

From `redesign-web-workspace` task 8.2: Home, Chat, Knowledge Base, Studio gallery, Studio canvas, Experiments, Integrations, and Settings.

| Theme | Widths |
| --- | --- |
| Light and dark | 1280px desktop and 390px narrow |

Add 768px for shared shell, navigation, or primitive changes. Use 800px height as a start. Spot-check 320px width and 200% browser zoom for the controls you touched. These are verification targets, not new breakpoints.

For a shared token, primitive, or shell change, inspect every screen. For a local change, inspect that screen and the shared components it uses.

### Mobile checks

Check mobile layouts in a desktop browser only. Set the viewport with device mode or the automation tool (for example 390x844 and 320x480, touch on). Do not use a simulator, an emulator, or a physical device. Keep it simple: look at the layout and check for overflow. Do not simulate gestures or multi-step interactions at mobile widths. Run keyboard and focus checks at desktop width.

With the Chrome DevTools tools, use `resize_page` or `emulate` for the viewport, `take_screenshot` for evidence, `take_snapshot` for the accessibility tree, and `list_console_messages` to confirm that raw errors went to the console and not the page.

## Per-case checklist

1. Inspect the default, hover, focus, selected, disabled, loading, empty, and error states where present.
2. Measure text contrast against the real composite background. Target AA. Include badge text on its tint.
3. Check control boundaries and focus indicators against neighbouring colours. Tab through the screen.
4. Look for horizontal page overflow, clipped text, cramped icons, and hidden actions.
5. Open each dialog and select. Check Escape, Tab order, focus trap, and focus return.
6. Switch theme with a safe draft open. Confirm the route and draft stay.
7. Reload. Confirm the theme and the active project persist. Confirm stale storage keys are dropped.
8. Force a failure (stop the server or block `/v1`). Confirm one friendly line, one action, and no parser text in the DOM.
9. Check reduced motion in the browser setting.
10. Confirm status badges show text, not colour alone.

Use long synthetic values: a long collection name, a long file path, and a long experiment folder name. Wrapping must keep layout intact.

## Evidence and reporting

Capture before and after images at matching theme, width, and data. Record computed styles when you need to prove a token or font. Report each check as `PASS`, `FAIL`, `NOT RUN`, or `BLOCKED`, with the command or browser case. A type check proves types. A screenshot proves appearance only for the case captured. Explain each gap and the next action to close it. Do not infer runtime or accessibility behaviour from static checks.

This skill does not authorise a security scan, a package install, live-data changes, or a git push. Ask first.
