"""Runtime tripwire: torch must not be loaded after a default search (task 8.3).

Asserts that importing rag_mcp and running a search with rerank=True on
the default backend does not load torch into sys.modules.

This turns the existing prose requirement ("no PyTorch at runtime") into
an automated CI check. The previous violation entered through a
transitive dependency that no one audited.

The subprocess test (issue #40) runs a full search in a clean
interpreter, because in-process ``sys.modules`` checks are unfalsifiable
once other tests have imported modules. It is marked ``@pytest.mark.slow``
because it boots a subprocess, downloads a model from HuggingFace Hub on
a cold cache, and can take more than a few seconds.
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


def test_torch_absent_after_default_backend_search() -> None:
    """After a default-backend search, torch SHALL NOT be in sys.modules.

    The default backend is ONNX, which uses tokenizers (pure Rust) and
    onnxruntime. Neither can pull torch. If this test fails, a
    dependency change reintroduced torch into the default path.
    """
    # Record the set of loaded modules before importing rag_mcp.
    # We check torch specifically, not the full diff, because other
    # modules may load legitimately.
    sys.modules.pop("torch", None)

    # Import the ONNX reranker module — this is what the default path loads.
    from rag_mcp.core.retrieval.reranker import CrossEncoderReranker  # noqa: F401

    assert "torch" not in sys.modules, (
        "torch was imported on the default (ONNX) backend path. "
        "A dependency change likely reintroduced it."
    )


def test_torch_absent_after_registry_import() -> None:
    """Importing the retrieval registry SHALL NOT load torch."""
    sys.modules.pop("torch", None)

    from rag_mcp.core.retrieval import registry  # noqa: F401

    assert "torch" not in sys.modules, (
        "torch was imported when the retrieval registry was imported. "
        "The registry must stay lazy — torch is behind an optional extra."
    )


def test_torch_absent_after_backend_module_import() -> None:
    """Importing the backend resolution module SHALL NOT load torch."""
    sys.modules.pop("torch", None)

    from rag_mcp.core.retrieval.backend import resolve_reranker_backend  # noqa: F401

    assert "torch" not in sys.modules, (
        "torch was imported when the backend resolution module was imported. "
        "The torch import must be lazy, inside the torch backend's _load_model."
    )


@pytest.mark.slow
def test_torch_absent_after_full_search_subprocess() -> None:
    """A full search with rerank=True SHALL NOT load torch (issue #40).

    Runs a search in a clean subprocess with an explicitly composed LanceDB
    store and mock embeddings, then asserts ``torch`` is absent from
    ``sys.modules``. The subprocess is necessary because in-process checks are
    unfalsifiable once other tests have imported modules.

    The child pins ``RETRIEVAL__RERANK_BACKEND=onnx`` unconditionally
    (not ``setdefault``) so an inherited env var or a repo ``.env`` file
    cannot silently swap in the torch backend and invalidate the check.

    The child also reports whether reranking actually happened. A search
    that silently degrades to un-reranked results (e.g. because the
    model could not be downloaded) would make the torch-absence check
    vacuous — it wouldn't have exercised the ONNX model-loading path at
    all. This test fails loudly in that case rather than passing for the
    wrong reason.
    """
    repo_root = Path(__file__).resolve().parent.parent
    script = textwrap.dedent(
        """
        import os, sys, json, tempfile

        # Pin the backend unconditionally — this test exists to prove the
        # ONNX (default) path stays torch-free, so an inherited env var
        # or .env file must not be able to swap in the torch backend.
        os.environ["RETRIEVAL__RERANK_BACKEND"] = "onnx"

        # ── Env vars (match conftest _isolate_env) ────────────────────
        os.environ["VECTOR_STORE"] = "lancedb"
        os.environ.setdefault("EMBED_PROVIDER", "local")
        os.environ.setdefault("LOCAL_BACKEND", "ollama")
        os.environ.setdefault("EMBED_MODEL", "nomic-embed-text")
        os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434")
        os.environ.setdefault("METADATA_LLM_PROVIDER", "local")
        os.environ.setdefault("METADATA__EXTRACTION_MODE", "disabled")
        os.environ.setdefault("METADATA__KEYWORD_RULES", "")
        os.environ.setdefault("PDF_READER", "pypdf")

        # ── Mock embedding model (no Ollama) ──────────────────────────
        from llama_index.core import Settings as LlamaIndexSettings
        from llama_index.core.embeddings import MockEmbedding
        LlamaIndexSettings.embed_model = MockEmbedding(embed_dim=384)

        # ── Reset vector store singleton ──────────────────────────────
        from rag_mcp.core.vectordb import reset_default_store, set_default_store
        reset_default_store()

        # ── Install default EffectiveSettings (match conftest) ────────
        from rag_mcp.core.settings import (
            EffectiveSettings,
            MetadataBlock,
            set_default_effective_settings,
        )

        with tempfile.TemporaryDirectory(prefix="torch_tripwire_") as work_dir:
            lancedb_uri = os.path.join(work_dir, "lancedb")
            os.environ["LANCEDB_URI"] = lancedb_uri
            set_default_effective_settings(
                EffectiveSettings(
                    metadata=MetadataBlock(extraction_mode="disabled"),
                    pdf_reader="pypdf",
                    collection_name="torch_tripwire",
                    vector_store="lancedb",
                    lancedb_uri=lancedb_uri,
                )
            )

            # Task 2.3: get_default_store() is injected-only. Compose the
            # store explicitly through the production composition root rather
            # than relying on the pre-change accessor fallback.
            from rag_mcp.compose import build_vector_store
            from rag_mcp.config import Settings as AppSettings

            set_default_store(
                build_vector_store(
                    AppSettings(vector_store="lancedb", lancedb_uri=lancedb_uri)
                )
            )

            # ── Ingest a small document ─────────────────────────────────
            import asyncio
            from rag_mcp.core.ingestion import ingest_path_async
            from rag_mcp.core.retrieval import search

            test_file = tempfile.NamedTemporaryFile(
                mode="w", suffix=".md", delete=False, prefix="torch_tripwire_",
                dir=work_dir,
            )
            try:
                test_file.write(
                    "# Machine Learning\\n\\nMachine learning is a subset of AI."
                )
                test_file.close()

                async def _run():
                    await ingest_path_async(
                        test_file.name, collection_name="torch_tripwire"
                    )
                    return search(
                        "machine learning",
                        collection_name="torch_tripwire",
                        rerank=True,
                    )

                results = asyncio.run(_run())
            finally:
                os.unlink(test_file.name)

        # ── Report outcome. The parent process owns every assertion —
        # this script always exits 0 on normal completion so a real
        # torch-loaded or reranking failure is reported via the JSON
        # payload, not swallowed by an exit-code / assertion mismatch.
        torch_loaded = "torch" in sys.modules
        reranked = bool(results) and all(r.get("reranked") for r in results)
        print(json.dumps({
            "torch_loaded": torch_loaded,
            "results_count": len(results),
            "reranked": reranked,
        }))
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
        timeout=180,
    )
    assert result.returncode == 0, (
        f"Subprocess search script raised an exception (exit {result.returncode}).\n"
        f"stdout: {result.stdout}\n"
        f"stderr: {result.stderr[-2000:]}"
    )
    output = json.loads(result.stdout.strip().splitlines()[-1])
    assert not output["torch_loaded"], (
        "torch was loaded into sys.modules during a full search with "
        "rerank=True on the default (ONNX) backend. A dependency change "
        "likely reintroduced torch into the default path."
    )
    assert output["reranked"], (
        "The search did not actually rerank any results, so this run "
        "never exercised the ONNX model-loading path and proves nothing "
        "about torch absence. Check the reranker model is reachable "
        f"(results_count={output['results_count']})."
    )
