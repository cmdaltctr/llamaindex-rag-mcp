"""Opt-in Chroma Cloud smoke check (add-chroma-cloud-backend, task 3.8).

Never runs in CI.  Verifies credentials, connection, and the basic
collection lifecycle against a DISPOSABLE collection that is deleted
afterwards:

    uv run python scripts/chroma_cloud_smoke.py

Prerequisites (in ``.env`` or the environment):

    CHROMA_MODE=cloud
    CHROMA_CLOUD_API_KEY=...
    # optional, supplied together:
    CHROMA_CLOUD_TENANT=...
    CHROMA_CLOUD_DATABASE=...

Configured credentials (the Chroma Cloud API key, the OpenRouter API key)
and connection identifiers (tenant, database) are never printed or logged.
Failures print a redacted message.
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from llama_index.core.schema import TextNode  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("chroma_cloud_smoke")

SMOKE_CORPUS = "smoke-check"


def _smoke_collection_name() -> str:
    """Derive the disposable collection name (deterministic, rule-safe)."""
    from rag_mcp.core.vectordb.naming import experiment_collection_name

    return experiment_collection_name(
        experiment_id="smoke",
        corpus=SMOKE_CORPUS,
        provider="smoke",
        model="probe",
    )


def run_smoke() -> int:
    """Ingest, query, and delete against a disposable cloud collection.

    Returns:
        Process exit code: 0 on success, 1 on any failure.
    """
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")

    from rag_mcp.config import Settings
    from rag_mcp.core.vectordb.chroma import build_chroma_vector_store

    settings = Settings()
    if settings.chroma_mode != "cloud":
        logger.error("CHROMA_MODE must be cloud for the smoke check (got %r)", settings.chroma_mode)
        return 1

    # The write/query paths embed via the LlamaIndex global model.
    from llama_index.core import Settings as LlamaIndexSettings

    from rag_mcp.compose import build_embed_model
    from rag_mcp.core.vectordb.identity import redact_cloud_secrets, redact_secret

    def _redact(message: str) -> str:
        """Redact every configured cloud credential and identifier."""
        return redact_secret(
            redact_cloud_secrets(
                message,
                settings.chroma_cloud_api_key,
                settings.chroma_cloud_tenant,
                settings.chroma_cloud_database,
            ),
            settings.openrouter_api_key,
        )

    try:
        LlamaIndexSettings.embed_model = build_embed_model(settings)
    except Exception as exc:
        # OpenAI-compatible clients can echo the submitted API key in
        # construction errors; redact before logging.
        logger.error("Embedding client construction failed: %s", _redact(str(exc)))
        return 1

    collection_name = _smoke_collection_name()
    logger.info(
        "Storage mode: cloud (tenant=%s database=%s)",
        "set" if settings.chroma_cloud_tenant else "unset",
        "set" if settings.chroma_cloud_database else "unset",
    )

    try:
        store = build_chroma_vector_store(
            mode="cloud",
            cloud_api_key=settings.chroma_cloud_api_key,
            cloud_tenant=settings.chroma_cloud_tenant or None,
            cloud_database=settings.chroma_cloud_database or None,
        )
    except (ValueError, RuntimeError) as exc:
        # Messages from the factory are already redacted.
        logger.error("Cloud client construction/validation failed: %s", exc)
        return 1

    started = time.perf_counter()
    try:
        # 1. Clean slate: remove any leftover smoke collection.
        if store.collection_exists(collection_name):
            store.delete_collection(collection_name)
            logger.info("Deleted leftover collection %r", collection_name)

        # 2. Create and write two nodes through the same client.
        store.create_collection(collection_name)
        nodes = [
            TextNode(text="chroma cloud smoke probe one", metadata={"smoke": SMOKE_CORPUS}),
            TextNode(text="chroma cloud smoke probe two", metadata={"smoke": SMOKE_CORPUS}),
        ]
        store.write_nodes(nodes, collection_name)
        count = store.count(collection_name)
        logger.info("Wrote %d nodes to %r", count, collection_name)
        if count < 2:
            logger.error("Expected at least 2 chunks after write, found %d", count)
            return 1

        # 3. Dense query through the same client.
        embedding = LlamaIndexSettings.embed_model.get_query_embedding("smoke probe")
        rows = store.query_dense(collection_name, embedding, n_results=2)
        logger.info("Query returned %d rows", len(rows))
        if not rows:
            logger.error("Query returned no rows")
            return 1
        logger.info("Row shape keys: %s", sorted(rows[0].keys()))
    except Exception as exc:
        logger.error(
            "Smoke operation failed: %s",
            _redact(str(exc)),
        )
        return 1
    finally:
        # 4. Always delete the disposable collection.
        try:
            if store.collection_exists(collection_name):
                store.delete_collection(collection_name)
                logger.info("Deleted disposable collection %r", collection_name)
        except Exception as exc:
            logger.warning(
                "Cleanup failed (collection may remain): %s",
                _redact(str(exc)),
            )

    logger.info("Smoke check passed in %.1fs", time.perf_counter() - started)
    return 0


if __name__ == "__main__":
    raise SystemExit(run_smoke())
