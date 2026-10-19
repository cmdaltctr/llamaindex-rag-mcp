"""Which source set each setting (move-settings-to-config-file, D3).

``Settings`` reads its sources in this order, highest first: ``init`` (an
explicit option), ``env`` (the process environment), ``dotenv`` (the ``.env``
file), ``config-file`` (``omrg.jsonc``), ``yaml`` (``defaults.yaml`` and the
profile bundle). A setting that no source sets reports ``default``. A secret
can also report ``key-file`` or ``keychain``.

``load_dotenv`` copies ``.env`` into ``os.environ`` when the package loads,
so the environment source alone cannot tell a shell export from a ``.env``
line. This module keeps the **names** that ``.env`` added (never the values)
and uses them to tell the two apart.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from dotenv import dotenv_values, find_dotenv, load_dotenv

#: Source words, highest priority first.
SOURCE_ORDER: tuple[str, ...] = ("init", "env", "dotenv", "config-file", "yaml")
#: Source word of a setting that no source sets.
DEFAULT_SOURCE = "default"

#: Upper-case names that ``.env`` added to the environment at load time.
#: A name that the shell had already exported is not in it: the shell wins.
DOTENV_KEYS: frozenset[str] = frozenset()


def load_project_dotenv() -> frozenset[str]:
    """Load the working directory's ``.env`` and remember which names it added.

    Returns:
        The upper-case names the file added to the environment. The values
        are not kept anywhere.
    """
    global DOTENV_KEYS
    path = find_dotenv(usecwd=True)
    if not path:
        DOTENV_KEYS = frozenset()
        return DOTENV_KEYS
    before = set(os.environ)
    load_dotenv(path)
    DOTENV_KEYS = frozenset(
        name.upper() for name in dotenv_values(path) if name not in before and name.upper()
    )
    return DOTENV_KEYS


def leaf_paths(values: Mapping[str, Any], blocks: Iterable[str]) -> frozenset[str]:
    """Return the dotted paths of the non-blank leaves in a source's output.

    Args:
        values: What a settings source returned (nested under block names).
        blocks: The names of the nested blocks (``retrieval``, ``answer``...).
    """
    block_names = set(blocks)
    found: set[str] = set()
    for key, value in values.items():
        name = str(key).lower()
        if name in block_names and isinstance(value, Mapping):
            found.update(
                f"{name}.{str(leaf).lower()}"
                for leaf, leaf_value in value.items()
                if _present(leaf_value)
            )
        elif _present(value):
            found.add(name)
    return frozenset(found)


def _present(value: Any) -> bool:
    return value is not None and not (isinstance(value, str) and not value.strip())


def split_environment(paths: Iterable[str]) -> tuple[frozenset[str], frozenset[str]]:
    """Split environment-source paths into shell exports and ``.env`` lines.

    Returns:
        ``(env, dotenv)``. A path is ``dotenv`` when ``.env`` added its
        environment name at load time.
    """
    shell: set[str] = set()
    file: set[str] = set()
    for path in paths:
        (file if path.replace(".", "__").upper() in DOTENV_KEYS else shell).add(path)
    return frozenset(shell), frozenset(file)


def merge_layers(layers: Sequence[tuple[str, Iterable[str]]]) -> dict[str, str]:
    """Return the source word of each path. The first layer that holds a path wins.

    Args:
        layers: ``(source word, paths)`` pairs, highest priority first.
    """
    sources: dict[str, str] = {}
    for word, paths in layers:
        for path in paths:
            sources.setdefault(path, word)
    return sources


def source_of(sources: Mapping[str, str], path: str) -> str:
    """Return the source word of *path*; ``default`` when no source set it."""
    return sources.get(path, DEFAULT_SOURCE)
