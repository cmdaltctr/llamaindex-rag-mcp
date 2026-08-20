## 1. Packaging and dependency isolation

- [ ] 1.1 Move `chromadb` and `llama-index-vector-stores-chroma` from `[project.dependencies]` into a new `[project.optional-dependencies].chroma` group, preserving their existing floors and comments.
- [ ] 1.2 Regenerate `uv.lock`; verify the lockfile still records the optional Chroma group and that a plain `uv sync` installs without chromadb.
- [ ] 1.3 Verify `tests/test_dependency_floors.py` passes with the moved entries and that the `_DRIFT_EXEMPT["chromadb"]` comment still names a true reason.

## 2. Default flip and construction paths

- [ ] 2.1 Flip the vector-store default to `lancedb` in `config/__init__.py`, `config/defaults.yaml`, and `.env.example` with explanatory comments.
- [ ] 2.2 Rewrite `core/vectordb/__init__.py::get_default_store` to construct the configured store through registry dispatch instead of importing the Chroma factory; keep the process-wide single-instance guarantee.
- [ ] 2.3 Guard the native sparse capability probe in `core/retrieval/sparse.py`: absent Chroma → warning + BM25 fallback; present-but-broken → actionable error chaining the original exception.
- [ ] 2.4 Add extra-absent vs broken-install discrimination at the `build_vector_store` boundary (`importlib.util.find_spec` check) with the documented `ValueError` message naming `uv sync --extra chroma` and the LanceDB alternative; extend `registry.get`'s ImportError with the same install hint.
- [ ] 2.5 Add settings cross-validation: `CHROMA_MODE=cloud` or any `CHROMA_CLOUD_*` credential with a non-Chroma `VECTOR_STORE` fails at resolution with a credential-free error.
- [ ] 2.6 Implement the legacy-data warning: unset `VECTOR_STORE` plus a non-empty configured Chroma directory emits one startup warning naming the directory and both migration options; no warning on fresh installs.
- [ ] 2.7 Generalise the chroma-specific startup summary/log line to report the effective store name and location.

## 3. Tests

- [ ] 3.1 Rework `tests/conftest.py`: make `_patch_chromadb` conditional on chromadb availability, point the autouse default effective-settings fixture at a `tmp_path` LanceDB URI, and mark Chroma-specific tests to skip cleanly without the extra.
- [ ] 3.2 Add tests: unset-selector resolves LanceDB; lazy default path never imports chromadb; `VECTOR_STORE=chroma` without the extra fails with the installation instruction; cloud-mode × lancedb cross-validation; legacy-directory warning present and absent cases; sparse probe fallback.
- [ ] 3.3 Keep the Chroma halves of the contract/legacy/hybrid/cloud suites passing when the extra is installed (no test deletions).
- [ ] 3.4 Add the base-install tripwire test: default settings runtime setup plus a search with `chromadb` asserted absent from loaded modules.

## 4. CI

- [ ] 4.1 Update the main test job to the chromadb-free base suite, including the tripwire.
- [ ] 4.2 Add a `chroma-extra` job (patterned on `torch-extra`): `uv sync --extra chroma`, then the Chroma-specific suites.
- [ ] 4.3 Add the `chroma` group to the `floors` matrix; confirm the `""` base entry passes without chromadb.
- [ ] 4.4 Verify `lint-imports` under the base install; if the graph requires chromadb, sync lint jobs with `--extra chroma` and record why.

## 5. Documentation and decision records

- [ ] 5.1 Write ADR-049: LanceDB as default, Chroma behind the extra, experiment store policy, CVE-2026-45829 rationale with no patched release, reconsideration trigger, migration paths, and the lockfile-scanner disposition for the optional group.
- [ ] 5.2 Sweep documentation per the drift procedure: `.env.example`, `README.md`, `CONTRIBUTING.md`, `AGENTS.md`, `docs/guides/{architecture,configuration,mcp-tools,cli-reference,ingestion,mcp-client-setup,providers}.md`; add the Chroma-user migration note.
- [ ] 5.3 Document the shared `CHROMA_SCAN_PAGE_SIZE` page-size behaviour with a comment; defer the neutral rename explicitly.
- [ ] 5.4 Record the experiment store policy in the experiment template guidance so new experiments default to LanceDB unless the store is a manipulated factor.

## 6. Gates

- [ ] 6.1 `uv sync --frozen` then full fast suite green on the base install; `uv sync --extra chroma` then Chroma suites green.
- [ ] 6.2 `ruff check .`, `ruff format --check .`, `lint-imports` (8 contracts kept), `openspec validate make-lancedb-default-and-isolate-chromadb --strict`.
- [ ] 6.3 Verify no unexpected files in `git diff` and that the release-block note in the Stage 5 record is updated to reflect the new packaging posture (advisory still tracked until a patch exists).
