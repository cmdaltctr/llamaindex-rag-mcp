# web/src (workspace front end)

The React workspace that talks to the local HTTP API.

## What belongs here

- One folder per area (`chat`, `studio`, `experiments`, `settings` and so on).
- Primitives in `components/ui/`, API clients in `api/`, helpers in `lib/`.

## Rules

1. Read `web/DESIGN.md` first. `styles/tokens.css` is the only source of colour, type, spacing and radius.
2. Use no literal colour in a component and no hand-written CSS file.
3. Use the primitives in `components/ui/`. Do not copy their classes or wrap them to change height, radius or colour.
4. Show a failure as one friendly line plus one action through `describeError` (`lib/errors.ts`). Send the raw message to the console.
5. Keep the `api/*.ts` types in step with `src/omrg/transports/api/routes/` and `openapi.yaml`.
6. Keep each file under 500 lines.
7. Run `npm run lint`, `npm run typecheck` and `npm test` in `web/` before you commit.

## Links

- [Root AGENTS.md](../../AGENTS.md)
- [Design system](../DESIGN.md)
