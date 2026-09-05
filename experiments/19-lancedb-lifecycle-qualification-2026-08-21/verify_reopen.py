#!/usr/bin/env python3
"""Fresh-interpreter reopen check (gate G2).

Run as a subprocess by ``run_qualification.py`` so the reopen happens in
a brand-new interpreter with no inherited in-process state. The parent
exports the pinned campaign environment (VECTOR_STORE, LANCEDB_URI,
embedding provider vars); this script inherits it via ``os.environ``.

Writes a JSON verdict to ``--out`` and exits non-zero on any mismatch.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expect-count", type=int, required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--expect-file", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    out_path = Path(args.out)

    payload: dict = {"ok": False}
    try:
        import os

        payload["env"] = {
            "VECTOR_STORE": os.environ.get("VECTOR_STORE"),
            "LANCEDB_URI": os.environ.get("LANCEDB_URI"),
        }

        from omrg.compose import ensure_runtime_setup

        ensure_runtime_setup()

        from omrg.core.retrieval import search
        from omrg.core.vectordb import get_default_store

        store = get_default_store()
        count = store.count("qual_documents")
        rows = search(args.query, top_k=3, hybrid=False, collection_name="qual_documents")
        top_meta = (rows[0].get("metadata") or {}) if rows else {}
        top_file = str(top_meta.get("file_path") or top_meta.get("file_name") or "")
        payload.update(
            {
                "count": count,
                "expect_count": args.expect_count,
                "top_file": top_file,
                "rows": len(rows),
                "expect_file": args.expect_file,
            }
        )
        payload["ok"] = count == args.expect_count and bool(rows) and args.expect_file in top_file
    except Exception as exc:  # noqa: BLE001 - recorded verbatim
        payload["error"] = repr(exc)

    out_path.write_text(json.dumps(payload, indent=1, sort_keys=True), encoding="utf-8")
    print(json.dumps(payload, sort_keys=True), flush=True)
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
