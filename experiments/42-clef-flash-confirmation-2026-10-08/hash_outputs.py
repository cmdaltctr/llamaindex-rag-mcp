"""Task 5.4: hash every scoring output before any summary is opened."""

from __future__ import annotations

from exp42_io import OUTPUT, atomic_json, read_json, sha256

FILES = ("candidate_a.json", "clef_flash.json", "speed.json", "control_routing.json", "labels.json")


def main() -> None:
    """Require complete scoring, then write output/output_hashes.json."""
    for name in ("candidate_a.json", "clef_flash.json"):
        payload = read_json(OUTPUT / name)
        labels = read_json(OUTPUT / "labels.json")
        expected = sum(r["class"] in {"junk", "healthy"} for r in labels["rows"])
        if len(payload["rows"]) + len(payload["failed"]) != expected:
            raise SystemExit(f"{name} is incomplete")
    atomic_json(OUTPUT / "output_hashes.json", {"files": {n: sha256(OUTPUT / n) for n in FILES}})
    print("output hashes written", flush=True)


if __name__ == "__main__":
    main()
