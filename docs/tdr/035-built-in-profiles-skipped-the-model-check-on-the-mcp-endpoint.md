# TDR-035: Built-in profiles skipped the model check on the MCP endpoint, so route every bind through the profile service

- **Date:** 2026-10-18
- **Status:** Proposed
- **Deciders:** Dr Muhammad Aizat Bin Md Hawari
- **Tags:** mcp | profiles | embedding | testing

## Context

ADR-081 lets a user profile choose its own embedding model. A collection holds
vectors from one model only, so a bind to a profile with another model must be
refused. `ProfileService.check_binding` does this for built-in and user
profiles. The web route `PATCH /v1/collections/{name}/profile` called it for
every profile.

The MCP tool `change_collection_profile` on the `omrg web` endpoint did not.
It bound `documents` or `codebase` to a collection made with another model.
The first search then failed with a stamp mismatch from the store.

### Root Cause Analysis

`transports/mcp/profile.py` chose the service like this:

```python
service = mcp.profiles if profile not in BUILTIN_PROFILES else None
if service is None:
    return apply_profile_change(collection, profile, store=engine.store)
```

Before ADR-081 a built-in profile needed no service check, so the branch was
correct. ADR-081 added the model check inside `check_binding`, and the built-in
branch never reached it.

The first test of the fix still passed the bind. The test fixture
(`make_env` in `tests/unit/test_engine_profiles_support.py`) gives the profile
service its own Engine and store. The MCP endpoint in the test uses a second
Engine. The check read the service's store, which had no stamp, and allowed the
bind. On `omrg web` both share one Engine, so production was not affected by
this test gap.

## Decision

1. When the MCP context has a profile service, run
   `service.check_binding(profile, collection)` for every profile, under
   `service.lock`, in the preview and in the confirm step. Built-in profiles
   then call `generate_safety_contract` and `apply_profile_change` without the
   catalogue, as before.
2. The test points the service's store reader at the endpoint's store:

   ```python
   monkeypatch.setattr(env.service.embedding, "_store", lambda: engine.test_store)
   ```

3. The stdio server keeps no check. It has no profile service and binds
   built-in profiles only. A wrong bind fails closed at the first query
   (ADR-051). ADR-081 decision 5 records this.

## Consequences

### Positive

- The web route and the MCP endpoint refuse the same binds, with the same
  message that names both models.

### Negative

- The stdio server can still bind a built-in profile to a collection that
  another model made. The error comes at query time, not at bind time.

### Neutral

- The MCP tests that use `make_env` still run two Engines. Tests that read a
  store through the service must patch `_store`.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| Check in the stdio server too | The transport would read the host identity through private Engine state (`engine._embedders`). The store guard already fails closed. |
| Change `make_env` to share one Engine | Many tests depend on the two-Engine fixture. The change is larger than the fix. |
| Leave the gap and rely on the store guard | The web route refuses at bind time. The MCP endpoint must give the same answer. |

## How to Recognise / Handle This Again

1. Symptom: a bind through MCP succeeds, then search fails with a stamp or
   model mismatch. The same bind through the web route returns 409
   `embedding_mismatch`.
2. Look for a branch that skips the service for built-in profiles:
   `grep -n "BUILTIN_PROFILES" src/omrg/transports/mcp/profile.py`.
3. Symptom in tests: a refusal test passes the bind although the collection
   is stamped. Check which store the service reads. Compare
   `env.service._engine.store` with the endpoint's `engine.test_store`.
4. Check: `uv run pytest tests/unit/test_mcp_profiles_web.py -q`.

## Revisit Triggers

- A new transport, or a new bind path, that changes a collection's profile.
- The stdio server gets a profile service or a public host-identity accessor.
- `make_env` changes to one shared Engine. Then remove the `_store` patch.

## References

- ADR-081 (per-profile embedding models), decision 5
- ADR-051 (fail-closed embedding write contract)
- `src/omrg/transports/mcp/profile.py`
- `src/omrg/compose_profile_embedding.py` (`ProfileEmbedding.check_binding`)
- `tests/unit/test_mcp_profiles_web.py`
- `tests/unit/test_engine_profiles_support.py` (`make_env`)
