"""Lazy Chroma Cloud client construction and connectivity validation."""

from __future__ import annotations

from typing import Any

from .identity import redact_cloud_secrets


def construct_cloud_client(
    cloud_api_key: str | None,
    cloud_tenant: str | None,
    cloud_database: str | None,
) -> Any:
    """Construct and validate a Chroma Cloud client with redacted errors.

    Raises:
        ValueError: If the resolved cloud configuration is incomplete.
        RuntimeError: If the client cannot connect.
    """
    key = (cloud_api_key or "").strip()
    if not key:
        raise ValueError(
            "CHROMA_MODE=cloud requires CHROMA_CLOUD_API_KEY to be set. "
            "Add it to your .env file (see .env.example); never commit the key."
        )
    kwargs: dict[str, str] = {"api_key": key}
    tenant = (cloud_tenant or "").strip()
    database = (cloud_database or "").strip()
    if tenant or database:
        if not (tenant and database):
            raise ValueError(
                "CHROMA_CLOUD_TENANT and CHROMA_CLOUD_DATABASE must be supplied "
                "together, or both omitted so the cloud client resolves them from the API key."
            )
        kwargs["tenant"] = tenant
        kwargs["database"] = database
    try:
        import chromadb

        client = chromadb.CloudClient(**kwargs)
        client.heartbeat()
    except Exception as exc:
        raise RuntimeError(
            redact_cloud_secrets(
                f"CHROMA_MODE=cloud connection check failed ({type(exc).__name__}): {exc}. "
                "Verify CHROMA_CLOUD_API_KEY, CHROMA_CLOUD_TENANT, and "
                "CHROMA_CLOUD_DATABASE, and network reachability of Chroma Cloud. "
                "No local fallback is performed after an explicit cloud selection.",
                key,
                tenant,
                database,
            )
        ) from None
    return client
