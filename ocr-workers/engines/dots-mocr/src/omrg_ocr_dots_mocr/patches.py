"""Apple Silicon patches and code-file hashes for the dots.mocr model (design D4).

Upstream targets CUDA. ``modeling_dots_vision.py`` imports ``flash_attn``
at module top level, and the vision tower asks for flash attention. Two
patches make the pinned revision load on MPS or CPU:

1. make the top-level ``flash_attn`` import optional, matching at line
   start only, so the patched copy (which keeps the import, indented)
   never matches again;
2. set the vision tower's attention implementation to SDPA in
   ``config.json``.

Both patches are idempotent. After patching, provisioning records a
SHA-256 of every model code file. ``trust_remote_code`` executes these
files, so the worker refuses to load when any hash differs.

This module is pure standard library; tests run it in the main OMRG
environment.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

#: Name of the patch set. It joins the engine's pipeline revision, so a
#: different patch set changes the worker identity.
PATCH_SET = "omrg-mps-1"

#: The file, inside the model folder, that records the code-file hashes.
HASH_FILE = "omrg-code-hashes.json"

VISION_FILE = "modeling_dots_vision.py"
CONFIG_FILE = "config.json"

_FLASH_ATTN_IMPORT_RE = re.compile(
    r"^from flash_attn import flash_attn_varlen_func\n", re.MULTILINE
)
_FLASH_ATTN_REPLACEMENT = (
    "try:\n"
    "    from flash_attn import flash_attn_varlen_func\n"
    "except ImportError:  # omrg: no CUDA on Apple Silicon\n"
    "    flash_attn_varlen_func = None\n"
)


class CodeHashMismatchError(Exception):
    """A model code file differs from the hash recorded at provisioning."""


def patch_flash_attn_import(model_dir: Path) -> bool:
    """Make the top-level ``flash_attn`` import optional.

    Returns:
        True when the file changed; False when it was already patched.
    """
    path = model_dir / VISION_FILE
    source = path.read_text(encoding="utf-8")
    patched = _FLASH_ATTN_IMPORT_RE.sub(_FLASH_ATTN_REPLACEMENT, source, count=1)
    if patched == source:
        return False
    path.write_text(patched, encoding="utf-8")
    return True


def patch_vision_sdpa(model_dir: Path) -> bool:
    """Set ``vision_config.attn_implementation`` to ``sdpa``.

    Returns:
        True when the file changed; False when it already said ``sdpa``.
    """
    path = model_dir / CONFIG_FILE
    config = json.loads(path.read_text(encoding="utf-8"))
    vision = config.setdefault("vision_config", {})
    if vision.get("attn_implementation") == "sdpa":
        return False
    vision["attn_implementation"] = "sdpa"
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return True


def apply_patches(model_dir: Path) -> list[str]:
    """Apply both patches; return the names of the patches that changed a file."""
    changed: list[str] = []
    if patch_flash_attn_import(model_dir):
        changed.append("flash_attn import optional")
    if patch_vision_sdpa(model_dir):
        changed.append("vision attn_implementation=sdpa")
    return changed


def code_files(model_dir: Path) -> list[Path]:
    """Return every file that decides what ``trust_remote_code`` runs.

    That is every ``.py`` file in the model folder, plus ``config.json``,
    which names the classes and the attention implementation.
    """
    files = sorted(p for p in model_dir.glob("*.py") if p.is_file())
    config = model_dir / CONFIG_FILE
    if config.is_file():
        files.append(config)
    return files


def code_file_hashes(model_dir: Path) -> dict[str, str]:
    """Return ``{file name: SHA-256 hex digest}`` for every code file."""
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in code_files(model_dir)
    }


def record_hashes(model_dir: Path) -> Path:
    """Write the code-file hashes to :data:`HASH_FILE`; return its path."""
    target = model_dir / HASH_FILE
    payload = {"patch_set": PATCH_SET, "files": code_file_hashes(model_dir)}
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def verify_hashes(model_dir: Path) -> None:
    """Check every code file against the hashes recorded at provisioning.

    Raises:
        CodeHashMismatchError: If the record is missing, was written by
            another patch set, or any file was added, removed or changed.
    """
    record_path = model_dir / HASH_FILE
    if not record_path.is_file():
        raise CodeHashMismatchError(f"no code-hash record at {record_path}; re-provision")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    if record.get("patch_set") != PATCH_SET:
        raise CodeHashMismatchError(
            f"code hashes were recorded for patch set {record.get('patch_set')!r}, "
            f"not {PATCH_SET!r}; re-provision"
        )
    expected = record.get("files", {})
    actual = code_file_hashes(model_dir)
    if actual != expected:
        changed = sorted(
            name for name in set(expected) | set(actual) if expected.get(name) != actual.get(name)
        )
        raise CodeHashMismatchError(f"model code files changed since provisioning: {changed}")
