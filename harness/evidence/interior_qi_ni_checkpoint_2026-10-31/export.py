#!/usr/bin/env python3
"""Copy an already completed, explicitly inventoried staging capture, never launch models."""

import argparse
import hashlib
import json
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("staging", type=Path)
    ap.add_argument("destination", type=Path)
    ap.add_argument("--inventory-sha256", required=True)
    a = ap.parse_args()
    raw = (a.staging / "inventory.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != a.inventory_sha256:
        raise ValueError("inventory digest")
    inv = json.loads(raw)
    if (
        inv.get("schema") != "interior-qi-ni-export-inventory-v1"
        or inv.get("completed") is not True
    ):
        raise ValueError("completed inventory required")
    files = inv["files"]
    if not isinstance(files, dict) or not files:
        raise ValueError("empty inventory")
    captured = {}
    for name, expected in files.items():
        path = Path(name)
        if path.is_absolute() or ".." in path.parts or path == Path("inventory.json"):
            raise ValueError("unsafe inventory path")
        data = (a.staging / path).read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError("digest mismatch: " + name)
        captured[path] = data
    a.destination.mkdir(parents=True, exist_ok=False)
    (a.destination / "inventory.json").write_bytes(raw)
    for name, data in captured.items():
        target = a.destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as f:
            f.write(data)
    print(
        "Copied inventoried bytes; this does not establish provenance or validate scientific content."
    )


if __name__ == "__main__":
    main()
