## 1. Pin the core listing contract

- [ ] 1.1 Add focused `list_documents()` tests with a fake `VectorStore` passed
      through `store=`. Implement `count()` and `iter_metadatas()` on the fake.
- [ ] 1.2 Use `tmp_path` for one existing absolute path and one missing absolute
      path. Assert `orphaned` is `False` and `True`, respectively.
- [ ] 1.3 Add legacy metadata with basename-only `file_name` and no source
      metadata. Assert both listing rows report `orphaned is None`.
- [ ] 1.4 Prove a non-absolute source never reaches the existence check. Include a
      same-named file in the process working directory.
- [ ] 1.5 Update existing exact listing-shape assertions in
      `tests/test_ingestion.py` and `tests/test_lineage_store_contract.py` for
      the additive field.
- [ ] 1.6 Run the focused core tests before implementation. Confirm the new
      assertions fail for the missing field.

## 2. Add machine-local orphan classification

- [ ] 2.1 Extend `core/ingestion/loader.py::list_documents()` with an
      `orphaned: bool | None` value on every returned row.
- [ ] 2.2 Classify each grouped source once. Check existence only after the host
      runtime confirms the source is absolute.
- [ ] 2.3 Return `None` for basenames, relative paths, `"unknown"`, and foreign
      path syntax that is not absolute locally.
- [ ] 2.4 Update the function docstring and return-shape description. State that
      orphaned means “missing on this machine”.
- [ ] 2.5 Keep grouping, `source_id`, chunk counts, and empty-store behaviour
      unchanged. Add no store mutation.
- [ ] 2.6 Confirm `src/rag_mcp/core/ingestion/loader.py` remains below the
      repository's 500-line ceiling.

## 3. Expose the field through CLI and MCP listing

- [ ] 3.1 Add an `Orphaned` column to the CLI's human-readable list table. Map
      values to `Yes`, `No`, and `Unknown`.
- [ ] 3.2 Update the CLI list help and docstring. State that status means
      “missing on this machine”.
- [ ] 3.3 Preserve direct CLI JSON serialisation. Assert booleans and `null`
      pass through without conversion.
- [ ] 3.4 Keep `list_indexed_documents` as a thin MCP pass-through. Update its
      description and docstring for the additive field and local meaning.
- [ ] 3.5 Extend `tests/test_cli.py` for the new column, human labels, and JSON
      values.
- [ ] 3.6 Extend `tests/test_mcp_tools.py` to assert the MCP listing returns
      `orphaned` unchanged with all existing row keys.

## 4. Document visibility and manual cleanup

- [ ] 4.1 Update the `list` section in `docs/guides/cli-reference.md`. Explain
      the column, tri-state values, and machine-local meaning.
- [ ] 4.2 Update `docs/guides/mcp-tools.md` with the additive `orphaned` field
      and its `true`, `false`, and `null` states.
- [ ] 4.3 Link orphan discovery to existing preview and deletion commands.
      State that listing never deletes indexed chunks.
- [ ] 4.4 Confirm documentation does not claim global source absence, move
      tracking, automatic cleanup, or identity preservation across moves.

## 5. Final verification

- [ ] 5.1 Run `uv run pytest tests/test_ingestion.py
      tests/test_lineage_store_contract.py tests/test_cli.py
      tests/test_mcp_tools.py tests/test_file_size_ceiling.py -v`.
- [ ] 5.2 Run Ruff against the changed Python files and tests. Fix only findings
      introduced by this change.
- [ ] 5.3 Confirm listing remains read-only and the canonical-path `source_id`
      formula is unchanged.
- [ ] 5.4 Run `openspec validate "orphaned-source-visibility-2" --type change
      --strict` and require a successful result.
