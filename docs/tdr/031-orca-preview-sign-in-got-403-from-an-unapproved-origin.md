# TDR-031: The Orca preview sign-in got 403 from an unapproved origin, so approve the origin with --allow-origin

- **Date:** 2026-10-15
- **Status:** Accepted (fix `244c9be`; live check in the Orca preview: sign-in 200, collections 200)
- **Deciders:** Aizat
- **Tags:** web | auth | origin | orca | preview
- **Related:** [ADR-079](../adr/079-approve-extra-loopback-origins-at-launch.md)

## Context

The page shows "The workspace session was not accepted. Open the workspace
again from the link that omrg web prints." The user saw it in the Orca browser
preview, and earlier in Safari and Edge when the preview address was in use.

### Root Cause Analysis

Symptom: the server log shows `POST /v1/session` with 403, then `GET /v1/*`
with 401 (there is no session cookie).

Cause: Orca serves the page from its own address,
`http://<worktree>.orca.localhost:<port>` (port `57977` here). The browser
sends that address as `Origin`. `GuardMiddleware` and the session route accept
only the server's own loopback origins, so they return 403. The `Host` check
passes first, and the client uses relative URLs, so only the `Origin` rule
fails.

Not the cause: `Referrer-Policy: no-referrer`. A logging proxy recorded the
real `Origin` on 2026-10-15 and disproved that theory.

Why it came back after the first fix attempt: the number at the end of the host
name changes when Orca reopens the preview. It moved from `...core-web-2` to
`-3` to `-4` in one session. An approved `-2` origin correctly refused a `-3`
page.

## Decision

Approve the exact origin when you start the server. Repeat the option for
more host names.

```bash
omrg web --allow-origin http://<worktree>.orca.localhost:<port>
# several host names in one launch
omrg web --allow-origin http://wt-2.orca.localhost:57977 \
         --allow-origin http://wt-3.orca.localhost:57977
```

Then click the printed link in the terminal. Orca rewrites it to its own
address, and that rewrite is the origin you approved. Do not edit the
`Host`, `Sec-Fetch-Site` or cookie rules.

## Consequences

### Positive

- The Orca preview signs in. The default behaviour is unchanged.

### Negative

- You must pass the current host name on each launch.

### Neutral

- A pattern for the suffix is a possible follow-up (ADR-079).

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| Open a normal browser and paste the link | Works, but not inside the preview. Kept as the fallback. |
| Wildcard `*.orca.localhost` | Approves every local page under the suffix. |
| Change `Referrer-Policy` | A logging proxy showed it is not the cause. |

## How to Recognise / Handle This Again

1. Look for `POST /v1/session` with 403 in the `omrg web` output.
2. Read the preview address: `orca tab list --json`, field `url`.
3. Compare its scheme, host and port with the `Approved extra origin:` lines
   that `omrg web` prints. They must match exactly.
4. If they differ, start the server again with the preview origin. The link
   works once, so use the new link.
5. Do not test with `orca goto` or `orca tab create`. Pages opened that way
   stay on `127.0.0.1` and never use the `orca.localhost` address, so they
   sign in even when the approval is wrong.
6. A quick probe: `POST /v1/session` with a wrong secret and `Origin` set to
   the preview origin. 401 means the origin is approved. 403 means it is not.

## Revisit Triggers

- Orca gives the preview a fixed host name or port.
- Orca changes how it serves the page (for example, it forwards a loopback
  `Origin`).
- Users pass many `--allow-origin` values on each launch. Then reconsider a
  suffix pattern.

## References

- `src/omrg/transports/api/origins.py`, `src/omrg/transports/api/security.py`,
  `src/omrg/transports/api/middleware.py`, `src/omrg/transports/cli/web.py`
- `docs/guides/web-workspace.md` ("Use an embedded preview")
- `openspec/changes/archive/2026-10-15-add-web-allow-origin-option/`
