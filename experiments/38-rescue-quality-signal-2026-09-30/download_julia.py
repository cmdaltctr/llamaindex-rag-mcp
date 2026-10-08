"""Download the approved Julia files from their pinned public revisions."""

from __future__ import annotations

from pathlib import Path

from experiment_io import EXP_DIR, OUTPUT, approved_plan, atomic_json, sha256

ONNX_FILES = (
    "model.onnx",
    "model.onnx.data",
    "tokenizer.json",
    "tokenizer_config.json",
    "parity-cases.json",
    "parity.py",
)
REFERENCE_FILES = (
    "inference-policy.json",
    "julia/data.py",
    "julia/probabilities.py",
    "julia_config.json",
)


def download_files(model: dict, destination: Path) -> dict[str, str]:
    """Fetch immutable model and reference files, then hash the model bytes."""
    from huggingface_hub import hf_hub_download

    for filename in ONNX_FILES:
        hf_hub_download(model["model"], filename, revision=model["revision"], local_dir=destination)
        print(f"[download] {filename} verified in pinned local cache", flush=True)
    for filename in REFERENCE_FILES:
        hf_hub_download(
            "SupersonicLabs/Julia-1",
            filename,
            revision=model["reference_model_revision"],
            local_dir=destination / "reference",
        )
        print(f"[download reference] {filename}", flush=True)
    return {
        name: sha256(destination / name)
        for name in ("model.onnx", "model.onnx.data", "tokenizer.json")
    }


def main() -> None:
    """Record SHA-256 values in the approved plan; never send page text."""
    plan = approved_plan()
    plan["candidates"]["B"]["file_sha256"] = download_files(
        plan["candidates"]["B"], OUTPUT / ".models"
    )
    atomic_json(EXP_DIR / "plan.json", plan)
    print("[download] model hashes recorded in plan.json", flush=True)


if __name__ == "__main__":
    main()
