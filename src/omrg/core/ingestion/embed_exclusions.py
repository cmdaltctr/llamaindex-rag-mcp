"""The embedding-text exclusion contract (capability embedding-text-composition).

Split out of ``core/ingestion/source_state.py``, which sits at the 500-line
ceiling, the same way ``ocr_identity`` was. The contract is one concern: which
metadata keys never reach the embedding model, and which of those describe only
one routing unit.

Both members are read through their module at call time, never frozen at
import, so a test override stays observable and a change to the set
invalidates the index identity precisely.
"""

from __future__ import annotations

from typing import Any

#: ``_RETAINED_EMBED_METADATA_KEYS`` instead.

EXCLUDED_EMBED_METADATA_KEYS = (
    # Parser telemetry — diagnostics about how a file was parsed, constant
    # across every chunk of a document (``pdf_inspector`` emits the first
    # four; page/layout keys cover the other readers).
    "pdf_reader",
    "pdf_type",
    "pdf_confidence",
    "ocr_required",
    "ocr_used",
    "ocr_backend",
    "pages_needing_ocr",
    "pages_needing_ocr_before_fallback",
    "extraction_fallback_backend",
    # Page-source counts, emitted only by the page routing unit. Constant
    # across a document's chunks, like every parser diagnostic above.
    "ocr_pages_native",
    "ocr_pages_local",
    "ocr_pages_worker",
    "ocr_pages_unresolved",
    "page_count",
    "page",
    "page_label",
    "column",
    "section_bbox",
    "bbox_schema_version",
    # Filesystem bookkeeping — machine-specific paths and timestamps that
    # differ between the machine that ingested and any other.
    "file_path",
    "file_type",
    "file_size",
    "creation_date",
    "last_modified_date",
    "last_accessed_date",
)

#: Keys in ``EXCLUDED_EMBED_METADATA_KEYS`` that only the ``page``
#: routing unit can emit. The document
#: unit never puts them on a Document, so their presence in the exclusion
#: set cannot change a document-unit install's embedded text, and
#: ``build_index_identity`` subtracts them from that install's payload
#: rather than reindexing every corpus for a key it will never see.
#: If ``page`` ever becomes the default, empty this set and bump
#: ``_INDEX_IDENTITY_SCHEMA``: from then on every install can emit them.
PAGE_ROUTING_ONLY_EMBED_KEYS = frozenset(
    {
        "ocr_pages_native",
        "ocr_pages_local",
        "ocr_pages_worker",
        "ocr_pages_unresolved",
    }
)


def scoped_excluded_keys(exclusion_set: tuple[str, ...], routing: dict[str, Any]) -> set[str]:
    """Return the exclusions that can affect this install's embedded text.

    A key only one routing unit can emit belongs in the identity only under
    that unit. Under ``document`` the page-routing keys are never put on a
    Document, so leaving them out is accurate rather than a lie — and it
    keeps a corpus indexed before page routing existed from reprocessing for
    a key it can never see. Under ``page`` they are included, because there
    they really do describe what was kept out of the embedded text.

    Args:
        exclusion_set: The centrally owned exclusion set.
        routing: The computed OCR routing payload. The unit is read from
            here rather than from settings, so the ``ocr_routing=``
            injection seam decides.

    Returns:
        The exclusion set, minus any key scoped to an inactive unit.
    """
    keys = set(exclusion_set)
    if routing.get("routing_unit", "document") == "document":
        keys -= PAGE_ROUTING_ONLY_EMBED_KEYS
    return keys
