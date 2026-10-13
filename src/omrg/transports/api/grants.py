"""Operator-approved file roots (design D8).

The operator approves roots on the command line (``omrg web --root``).
Browser requests name a root by its identifier plus a relative path; they
never send an arbitrary server path. Every candidate is canonicalised
(symlinks followed, ``..`` removed) and must stay inside its root. A path
read from indexed metadata is checked the same way, so indexing a file
never grants access to it.

The check and a later open are two steps. A process that can swap files
inside an approved root between them is outside this threat model: it
already has the operator's file access.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


class GrantDenied(PermissionError):
    """A path is outside every approved root, or the root is unknown.

    The message is the same for missing and existing files, so a denial
    does not disclose what exists outside the grants.
    """


@dataclass(frozen=True)
class Root:
    """One approved directory.

    Attributes:
        id: Stable identifier derived from the canonical path.
        path: Canonical absolute directory path.
        kind: ``"operator"`` for CLI roots, ``"managed"`` for workspace storage.
    """

    id: str
    path: Path
    kind: str = "operator"


def _root_id(path: Path) -> str:
    return "root_" + hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:12]


def _inside(candidate: Path, root: Path) -> bool:
    return candidate == root or candidate.is_relative_to(root)


class RootGrants:
    """The set of approved roots for one launch."""

    def __init__(self, roots: Iterable[Root]) -> None:
        """Hold already-canonical roots. Use :meth:`from_paths` to build."""
        self._roots = {root.id: root for root in roots}

    @classmethod
    def from_paths(cls, paths: Iterable[Path | str], kind: str = "operator") -> RootGrants:
        """Canonicalise operator paths into roots.

        Args:
            paths: Directories the operator approved.
            kind: Root kind recorded for each path.

        Raises:
            ValueError: A path does not exist or is not a directory.
        """
        roots = []
        for raw in paths:
            path = Path(raw).expanduser()
            if not path.is_dir():
                raise ValueError(f"Approved root is not an existing directory: {raw}")
            canonical = path.resolve(strict=True)
            roots.append(Root(_root_id(canonical), canonical, kind))
        return cls(roots)

    def with_root(self, path: Path, kind: str) -> RootGrants:
        """Return a copy that also contains *path* as a root of *kind*."""
        extra = RootGrants.from_paths([path], kind=kind)
        return RootGrants([*self._roots.values(), *extra._roots.values()])

    def describe(self) -> list[dict[str, str]]:
        """List the roots for an authorised session."""
        return [
            {"id": root.id, "path": str(root.path), "kind": root.kind}
            for root in self._roots.values()
        ]

    def resolve(self, root_id: str, relative: str) -> Path:
        """Resolve *relative* inside the root named *root_id*.

        Args:
            root_id: Identifier from :meth:`describe`.
            relative: A relative path inside that root.

        Returns:
            The canonical path of an existing file or directory.

        Raises:
            GrantDenied: Unknown root, absolute or escaping path, or no such file.
        """
        root = self._roots.get(root_id)
        if root is None:
            raise GrantDenied("Unknown file root.")
        if "\x00" in relative or os.path.isabs(relative) or relative.startswith("~"):
            raise GrantDenied("Paths must be relative to an approved root.")
        return self._contain(root.path / relative, [root])

    def check(self, path: Path | str) -> Path:
        """Check an absolute path, such as one read from indexed metadata.

        Args:
            path: The absolute path to check.

        Returns:
            The canonical path when it exists inside an approved root.

        Raises:
            GrantDenied: Relative, outside every root, or no such file.
        """
        text = str(path)
        if "\x00" in text or not os.path.isabs(text):
            raise GrantDenied("Path is outside the approved roots.")
        return self._contain(Path(text), list(self._roots.values()))

    @staticmethod
    def _contain(candidate: Path, roots: list[Root]) -> Path:
        """Canonicalise *candidate* and require it inside one of *roots*."""
        try:
            canonical = candidate.resolve(strict=False)
        except (OSError, RuntimeError):
            raise GrantDenied("Path is outside the approved roots.") from None
        if not any(_inside(canonical, root.path) for root in roots):
            raise GrantDenied("Path is outside the approved roots.")
        if not canonical.exists():
            raise GrantDenied("Path is outside the approved roots or does not exist.")
        return canonical
