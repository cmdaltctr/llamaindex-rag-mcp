"""Storage-selection Settings validation (task 2.5, design D7).

The vector-store compatibility, Chroma credential and provenance
validators live in a mixin so ``config/__init__.py`` stays under the
file-size ceiling. Pydantic runs base-class ``mode="after"`` validators
BEFORE the model's own, so these compare ``chroma_mode`` with
``.strip()`` — the provider-selection validator normalises it later,
and order independence must not change the outcome.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pydantic import model_validator
from pydantic_settings import PydanticBaseSettingsSource

if TYPE_CHECKING:
    from . import Settings

logger = logging.getLogger(__name__)


def source_keys(source: PydanticBaseSettingsSource) -> set[str]:
    """Return the keys a settings source would resolve, safely.

    A settings source is callable and returns the field-name-keyed dict it
    would feed the model. Calling it here — in ``settings_customise_sources``,
    before construction — records provenance without perturbing resolution.
    A source that raises (e.g. an unreadable env) contributes nothing.
    """
    try:
        values = source()
    except Exception:  # noqa: BLE001 - a broken source must not break config
        return set()
    if values is None:
        return set()
    return set(values)


class StorageValidationMixin:
    """Validators for vector-store backend selection and Chroma settings."""

    @model_validator(mode="after")
    def _validate_vector_store_compat(self) -> Settings:
        """Reject Chroma-only settings when the selected backend is not Chroma.

        Backend/settings compatibility is validated BEFORE Chroma credential
        completeness (design D7, task 2.5): ``VECTOR_STORE=lancedb`` plus
        ``CHROMA_MODE=cloud`` or any non-empty-after-trim ``CHROMA_CLOUD_*``
        value always yields the backend-mismatch error, even when the API
        key is absent. The error names the offending settings but never
        echoes their values.
        """
        if self.vector_store == "chroma":
            return self
        offenders: list[str] = []
        if self.chroma_mode.strip() == "cloud":
            offenders.append("CHROMA_MODE")
        for name, value in (
            ("CHROMA_CLOUD_API_KEY", self.chroma_cloud_api_key),
            ("CHROMA_CLOUD_TENANT", self.chroma_cloud_tenant),
            ("CHROMA_CLOUD_DATABASE", self.chroma_cloud_database),
        ):
            if value.strip():
                offenders.append(name)
        if not offenders:
            return self
        raise ValueError(
            f"VECTOR_STORE={self.vector_store!r} is selected but Chroma-only "
            f"setting(s) are set: {', '.join(offenders)}. Chroma settings "
            f"never alter an unselected backend route. Set VECTOR_STORE=chroma "
            f"to use Chroma (install the chroma extra: uv sync --extra chroma), "
            f"or clear the Chroma-only setting(s)."
        )

    @model_validator(mode="after")
    def _validate_chroma_cloud_settings(self) -> Settings:
        """Validate explicit cloud selection: key required, tenant/database paired.

        Fails at Settings construction so startup aborts before any
        ingestion or retrieval begins (chroma-cloud-backend spec).  Unlike
        the Azure document backend, cloud storage has no silent local
        fallback: an explicit ``CHROMA_MODE=cloud`` without credentials is
        an operator error, not a degradation opportunity (ADR-029 lesson).

        Credential completeness is enforced only when the Chroma backend is
        actually selected (task 2.5) — the backend-compat validator above
        already rejected Chroma settings under a non-Chroma backend.

        Error messages name the missing variables but never echo the
        submitted key material.
        """
        if self.chroma_mode.strip() != "cloud" or self.vector_store != "chroma":
            return self
        if not self.chroma_cloud_api_key.strip():
            raise ValueError(
                "CHROMA_MODE=cloud requires CHROMA_CLOUD_API_KEY to be set. "
                "Add it to your .env file (see .env.example); never commit the key."
            )
        # Store the stripped key so padded .env values authenticate cleanly.
        object.__setattr__(self, "chroma_cloud_api_key", self.chroma_cloud_api_key.strip())
        tenant = self.chroma_cloud_tenant.strip()
        database = self.chroma_cloud_database.strip()
        if bool(tenant) != bool(database):
            raise ValueError(
                "CHROMA_CLOUD_TENANT and CHROMA_CLOUD_DATABASE must be supplied "
                "together, or both omitted so the cloud client resolves them "
                "from the API key."
            )
        # Store stripped identifiers so padded .env values resolve cleanly.
        object.__setattr__(self, "chroma_cloud_tenant", tenant)
        object.__setattr__(self, "chroma_cloud_database", database)
        return self

    @model_validator(mode="after")
    def _record_vector_store_provenance(self) -> Settings:
        """Record whether ``vector_store`` came from an explicit source.

        ``settings_customise_sources`` captures which explicit (operator)
        sources would resolve ``vector_store`` — constructor/CLI args,
        environment, or ``.env``. Shipped ``defaults.yaml`` counts as a
        default, not an operator selection (design D6). ``model_fields_set``
        alone cannot distinguish them because every source that yields a
        field adds it there.
        """
        explicit = "vector_store" in self.model_fields_set and bool(
            self.__class__._explicit_vector_store_sources
        )
        object.__setattr__(self, "vector_store_provenance", "explicit" if explicit else "default")
        return self
