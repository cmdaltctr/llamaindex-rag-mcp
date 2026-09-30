"""``omrg-ocr-fetch``: download the pinned dots.mocr revision and patch it.

``provision.py dots-mocr --accept-model-licence`` runs this console
script inside the engine environment after ``uv sync --locked``. It is
the only place the engine touches the network. A parse never downloads
(the engine sets ``HF_HUB_OFFLINE=1`` before any Hugging Face import).

Steps:

1. download revision :data:`REVISION` of :data:`REPO_ID` into the
   engine's model cache folder;
2. apply the two Apple Silicon patches (idempotent);
3. record a SHA-256 of every model code file.

Running it twice leaves the same files and the same hashes.
"""

from __future__ import annotations

import sys

from .patches import apply_patches, record_hashes
from .paths import model_dir

REPO_ID = "rednote-hilab/dots.mocr"

#: The revision Experiment 34 measured (design D4).
REVISION = "e539fbb52280393adc081b289ec597430a0f9031"


def fetch(*, download: bool = True) -> dict[str, object]:
    """Download (optionally), patch and hash the model folder.

    Args:
        download: False skips the download step. Tests use this to run
            the patch-and-hash steps on a prepared folder.

    Returns:
        A summary with the model folder, the patches that changed a
        file, and the hash record path.
    """
    target = model_dir()
    target.mkdir(parents=True, exist_ok=True)
    if download:
        from huggingface_hub import snapshot_download  # engine environment only

        snapshot_download(REPO_ID, revision=REVISION, local_dir=target)
    changed = apply_patches(target)
    record = record_hashes(target)
    return {"model_dir": str(target), "patches_changed": changed, "hash_record": str(record)}


def main(argv: list[str] | None = None) -> int:  # noqa: ARG001 - console-script signature
    """Console-script entry point; prints a one-line summary to standard error."""
    summary = fetch()
    print(
        f"dots.mocr {REVISION} ready in {summary['model_dir']}; "
        f"patches changed: {summary['patches_changed'] or 'none'}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
