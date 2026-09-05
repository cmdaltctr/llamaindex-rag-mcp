"""LanceDB metadata-schema preparation for node writes."""

from __future__ import annotations

from typing import Any

import pyarrow as pa

from .lance_meta import infer_arrow_type, metadata_field_names
from .lance_paged import INTERNAL_METADATA_KEYS


def evolve_for_nodes(store: Any, collection_name: str, nodes: list[Any]) -> None:
    """Grow an existing LanceDB metadata struct for the candidate nodes."""
    samples: dict[str, list[Any]] = {}
    for node in nodes:
        metadata = getattr(node, "metadata", None) or {}
        for key, value in metadata.items():
            samples.setdefault(key, []).append(value)
    existing = store._open_table(collection_name)
    if existing is None:
        return
    present = metadata_field_names(existing)
    new_fields: dict[str, pa.DataType] = {
        key: infer_arrow_type(values) for key, values in samples.items()
    }
    for key in INTERNAL_METADATA_KEYS - present - set(new_fields):
        new_fields[key] = pa.string()
    store.evolve_metadata_fields(collection_name, new_fields)
