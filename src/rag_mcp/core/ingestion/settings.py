"""Pure-data settings model for the ingestion subpackage.

``embed_concurrency`` and ``embed_batch_size`` previously lived in
``ChunkingSettings``, where the flat schema had nowhere better to put them.
They are ingestion concerns, not chunking concerns, and the nested schema
gives them a home (design.md D10). The move is made in the same change as
the env-var rename so the migration cost is paid once rather than twice.

``ingest_extensions`` (fix-embedding-and-structure-fidelity-1, design D4)
is the profile-scoped set of file extensions ingestion collects; the
historical seven stay the default so the documents profile is unchanged.

This module MUST stay pure data: no imports from ``config``, ``compose``,
or any sibling ``core/`` business module.
"""

from __future__ import annotations

import json
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict
from pydantic_settings import NoDecode

#: The historical ingestible set — the DEFAULT value of the
#: ``ingest_extensions`` setting (design D4). Profiles overlay this with
#: their own list (``codebase.yaml`` adds source extensions); the module
#: constant ``SUPPORTED_EXTENSIONS`` in ``loader.py`` derives from it.
#: The ``IngestionBlock`` twin in ``core/settings.py`` repeats this tuple
#: (the import-linter pure-data contract forbids the import) — the two
#: must stay in sync.
DEFAULT_INGEST_EXTENSIONS: tuple[str, ...] = (
    ".pdf",
    ".docx",
    ".pptx",
    ".txt",
    ".md",
    ".html",
    ".csv",
)


def parse_extension_set(value: object) -> object:
    """Normalise an extension-set value to a tuple of dotted lowercase strings.

    Accepts the shapes every source can produce:

    * a bare comma-separated string (``".py, .ts"`` — the env-var form),
    * a JSON array string (``'[".py", ".ts"]'`` — the KEYWORD_RULES
      precedent),
    * an iterable of strings (YAML lists, ``model_dump`` round-trips).

    Bare extensions gain their leading dot and everything is lowercased;
    empty parts are dropped. Unknown shapes pass through for pydantic to
    reject with its own error.
    """
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("["):
            try:
                value = json.loads(text)
            except json.JSONDecodeError:
                value = text.split(",")
        else:
            value = text.split(",")
    if isinstance(value, (list, tuple, set, frozenset)):
        parts: list[str] = []
        for item in value:
            ext = str(item).strip().lower()
            if not ext:
                continue
            if not ext.startswith("."):
                ext = f".{ext}"
            parts.append(ext)
        return tuple(parts)
    return value


#: ``NoDecode`` keeps pydantic-settings from JSON-parsing the env value
#: before validators run, so the comma-separated form parses natively.
IngestExtensions = Annotated[tuple[str, ...], NoDecode, BeforeValidator(parse_extension_set)]


class IngestionSettings(BaseModel):
    """Ingestion pipeline knobs (env prefix ``INGESTION__``)."""

    model_config = ConfigDict(extra="forbid")

    # Number of parallel embedding requests in flight.
    # Raised 2 -> 4 (2026-08-05) when promoted out of .env. Machine-specific:
    # lower it if the embedding backend starts throttling.
    embed_concurrency: int = 4

    # Documents per embedding API call.
    embed_batch_size: int = 100

    # File extensions ingestion collects (design D4: profile-scoped, not a
    # global constant). The ``codebase`` profile overlays source extensions
    # onto this default; the documents profile inherits it unchanged. The
    # watcher builds its watch patterns from the same resolved set, so
    # watch and manual ingest cannot diverge. Env:
    # INGESTION__INGEST_EXTENSIONS=".py,.ts,.go" (comma-separated) or a
    # JSON array string.
    ingest_extensions: IngestExtensions = DEFAULT_INGEST_EXTENSIONS
