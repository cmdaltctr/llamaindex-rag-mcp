# Tasks

## 1. Origin validation

- [x] 1.1 Write `tests/unit/test_web_origins.py` for `parse_extra_origin`: accepts `localhost`, `*.localhost` names, `127.0.0.1` and `[::1]`; lower-cases; drops default ports 80 and 443; rejects a path, query, fragment, user information, wildcard, `ftp` scheme and a public host. Run it and confirm it fails because the module is missing.
- [x] 1.2 Add `src/omrg/transports/api/origins.py` with `parse_extra_origin`, Google-style docstring and `from __future__ import annotations`. Verify `uv run pytest tests/unit/test_web_origins.py -v` passes and that each error message names the broken rule.

## 2. Access policy

- [x] 2.1 Add tests to `tests/unit/test_web_security.py`: with an approved origin, `POST /v1/session` returns 200 and sets the cookie; a signed-in state-changing request with that origin is admitted; a different foreign origin still gets 403; a foreign `Host` still gets 400; `Sec-Fetch-Site: cross-site` still gets 403; with no approved origin the same request still gets 403; `allowed_hosts` is unchanged. Confirm they fail on the current code.
- [x] 2.2 Add `extra_origins` to `AccessPolicy.__init__` and `for_launch` in `src/omrg/transports/api/security.py`. Verify the new tests pass, and that `security.py` stays under 500 lines (`uv run pytest tests/test_file_size_ceiling.py`).
- [x] 2.3 Add a test in `tests/unit/test_web_mcp_http_support.py` that an approved origin reaches the MCP-over-HTTP route and that the SDK `allowed_origins` list contains it. Verify it passes, and that it fails when `mcp_http.py` is pointed at a policy without the extra origin.

## 3. Launch option and docs

- [x] 3.1 Add tests to `tests/unit/test_web_launch.py`: a bad `--allow-origin` exits with code 2 and names the value before any socket is bound; two values both reach the policy; each approved origin is printed before the launch link. Confirm they fail on the current code.
- [x] 3.2 Add the repeatable `--allow-origin` option to `src/omrg/transports/cli/web.py`, validate it with the other argument checks, pass it to `AccessPolicy.for_launch` and print each origin. Verify the launch tests pass and `uv run omrg web --help` shows the option.
- [x] 3.3 Document the option in `docs/guides/web-workspace.md` (options table and the "Request checks" list) and in `docs/guides/cli-reference.md` (options table). State that it approves one exact loopback origin for one run and does not change the `Host` rule. Verify `uv run pytest tests/unit/test_web_workspace_guide.py -v` passes, then grep `docs/guides/` for the old "foreign `Origin`" wording and confirm no page contradicts the new text.

## 4. Record and integration checks

- [x] 4.1 Write ADR-079 in `docs/adr/` with `s-adr`: exact, loopback-only, per-launch approval of extra origins, and why `Host` and `Sec-Fetch-Site` stay unchanged. Verify the file follows `docs/adr/ADR_README.md` and the ADR index lists it.
- [x] 4.2 Run `openspec validate add-web-allow-origin-option --strict`, `uv run pytest -m "not slow" --cov=omrg` and `./scripts/local_ci.sh`. Verify all pass and that the coverage floors for `transports/cli` and `transports/api` hold.
- [x] 4.3 Manual check in the Orca preview: launch `omrg web --allow-origin <the origin shown in the preview address bar>`, open the printed link in the preview, and verify the workspace loads collections. If the preview still returns 403, capture `Origin`, `Sec-Fetch-Site` and `Host` from a logging proxy and stop to revise `design.md` (decision 5) before any further code change.
