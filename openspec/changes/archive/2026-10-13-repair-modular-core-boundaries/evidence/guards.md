# Guard evidence: task 5.1 (design D6)

Base commit: `3ca82a0`, with uncommitted work in the feature worktree.
Date: 2026-10-13.

## Guard design

File: `tests/test_no_global_settings_reads.py` (342 lines, below the 500-line ceiling).

The existing regex guard for the `config` singleton is unchanged. A new AST guard follows it.

- Forbidden accessors: `get_default_effective_settings`, `_default_effective`, `get_default_store`, `_default_store`.
- Detected forms:
  - direct `from ... import X` and use;
  - qualified `module.X`, for any qualifier;
  - aliased `from ... import X as y`, with each use of `y` reported;
  - aliased module `import omrg.core.settings as cs; cs.X()`;
  - function-local imports;
  - a reference without a call;
  - `getattr(mod, "X")`;
  - star imports from a `settings` or `vectordb` module.
- Comments, strings, definitions and longer identifiers do not match.
- Sanctioned boundary: `resolve_effective_settings` is not in the forbidden set. It stays the documented compatibility entry resolution (D2, D3). There is no sanctioned default-store fallback in these leaves (D2: seed-only; D3: empty document communities).
- Scope: an explicit list `_GUARDED_LEAVES`. There is no package-wide ban and no module exemption. `test_guarded_leaves_exist` fails on a stale or missing entry.

Guarded leaves (relative to `src/omrg`):

- `core/ingestion/chunker.py`
- `core/metadata/{_common,extractor,keyword,llamacpp,llamaindex,ollama,openrouter,registry,taxonomy}.py`
- `core/codebase/{cache,codebase_map,communities,models}.py`

## Fixture results

Command:

```
PYTHONPATH=src <v3>/.venv/bin/python -m pytest tests/test_no_global_settings_reads.py -q -p no:cacheprovider
```

- 14 forbidden fixtures (direct, qualified, aliased, function-local, conditional fallback, private global, bare reference, getattr, star import): all flagged. PASS.
- 10 sanctioned fixtures (`resolve_effective_settings` direct and qualified, supplied store/settings, model imports, definitions, comments, strings, longer names): none flagged. PASS.
- Mutation check (scratch script, not committed). Each detector branch was disabled in turn:

| Branch disabled | Forbidden fixtures that then fail |
|---|---|
| Attribute (qualified) | 4 |
| Alias tracking | 2 |
| ImportFrom | 4 |
| getattr | 1 |

## Real-source hits (before evidence)

Snapshot taken while other agents were editing `src/`. Result: 5 failed, 52 passed.

| File | Line | Hit |
|---|---|---|
| (list) | | `core/codebase/models.py` missing (D4 not landed) |
| `core/metadata/taxonomy.py` | 14 | `import get_default_store` |
| `core/metadata/taxonomy.py` | 75 | `read get_default_store` |
| `core/codebase/cache.py` | 19 | `import get_default_effective_settings` |
| `core/codebase/cache.py` | 61, 93 | `read get_default_effective_settings` |
| `core/codebase/codebase_map.py` | 20 | `import get_default_effective_settings` |
| `core/codebase/codebase_map.py` | 169, 216 | conditional fallback `settings if ... else get_default_effective_settings()` |
| `core/codebase/codebase_map.py` | 292 | unconditional `get_default_effective_settings()` |
| `core/codebase/codebase_map.py` | 330, 332 | function-local `get_default_store` import and read |

`core/ingestion/chunker.py`, the metadata backends, `extractor.py` and `communities.py` pass. They use only `resolve_effective_settings`.

After evidence (2026-10-13, after agents A, B and C landed):

```bash
PYTHONPATH=src <v3>/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_no_global_settings_reads.py
```

Result: PASS. No real-source hits remain in the guarded leaves; `core/codebase/models.py` now exists.

## Default reads outside the guarded scope

These files still read defaults. They are outside the D6 leaf list, so the guard does not cover them:

- `integrations/magika.py:26,79`: `get_default_effective_settings().magika_binary`.
- `integrations/pdf/liteparse.py:266-268`: function-local default read.
- `core/documents/doc_graph.py:25,130` and `core/documents/similarity.py:19,46`: threshold fallback when the argument is omitted. D3 makes the map pass the threshold, so the map path no longer reaches this fallback.
- `core/ingestion/{pipeline,writer,replacement,loader}.py`, `core/retrieval/*`, `core/profiles/*`, `core/vectordb/chroma.py`: entry-boundary store or settings fallbacks.

## Other checks

| Check | Result |
|---|---|
| `tests/test_file_size_ceiling.py` + `tests/test_contract_coverage.py` | PASS (27 passed) |
| `lint-imports` (8 contracts) | PASS (8 kept, 0 broken) |
