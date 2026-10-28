"""Add the 54 public liquid-failure layers to a pinned private RK trace.

This source-only overlay changes trace selection, never RK or KDM arithmetic.
The first ten targets stay in place because the existing writer uses their
indices to identify the separate QC and QI witnesses.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


BASE_SOURCE_SHA256 = "c8642c04976ba91d5ef7ebd5e9cb9c7c19d188978198fc513b756c57029129f9"
RESIDUAL_ROWS_SHA256 = "fa7ba0a92ccec5f1b8001a3c218b8a737ca90c1b9ed4a24f6253e616c1f6257e"
BASE_TARGETS_IKJ = (
    (153, 4, 111), (113, 12, 70), (155, 15, 120), (1, 33, 168),
    (112, 12, 70), (114, 12, 70), (113, 12, 69), (113, 12, 71),
    (113, 11, 70), (113, 13, 70),
)
BASE_LINES = (
    "   INTEGER, PARAMETER :: KDM6AD_UPNC_NTARGET = 10",
    "   INTEGER, PARAMETER :: KDM6AD_UPNC_I(KDM6AD_UPNC_NTARGET) = (/ 153, 113, 155, 1, 112, 114, 113, 113, 113, 113 /)",
    "   INTEGER, PARAMETER :: KDM6AD_UPNC_K(KDM6AD_UPNC_NTARGET) = (/ 4, 12, 15, 33, 12, 12, 12, 12, 11, 13 /)",
    "   INTEGER, PARAMETER :: KDM6AD_UPNC_J(KDM6AD_UPNC_NTARGET) = (/ 111, 70, 120, 168, 70, 70, 69, 71, 70, 70 /)",
)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def liquid_failure_coords(raw: bytes) -> tuple[tuple[int, int, int], ...]:
    if sha(raw) != RESIDUAL_ROWS_SHA256:
        raise ValueError("PR #466 residual layer rows changed")
    rows = json.loads(raw)["rows"]
    coords = []
    for row in rows:
        for level in row["failing_level_words"]:
            words = level["final_f32_hex"]
            if int(words["QCLOUD"], 16) > 0 and words["QNCLOUD"] == "00000000":
                coords.append((row["i_one_based"], level["native_k_one_based"],
                               row["j_one_based"]))
    if (len(rows) != 54 or len(coords) != 54 or len(set(coords)) != 54 or
            any(type(v) is not int or v < 1 for coord in coords for v in coord)):
        raise ValueError("liquid-failure target inventory differs")
    return tuple(coords)


def render_solve(source: bytes, residual_rows: bytes) -> tuple[bytes, tuple[tuple[int, int, int], ...]]:
    if sha(source) != BASE_SOURCE_SHA256:
        raise ValueError("PR #471 private solve source changed")
    liquid = liquid_failure_coords(residual_rows)
    added = tuple(coord for coord in liquid if coord not in BASE_TARGETS_IKJ)
    targets = BASE_TARGETS_IKJ + added
    if len(targets) != 61 or len(set(targets)) != len(targets):
        raise ValueError("expanded RK trace target inventory differs")
    text = source.decode("utf-8")
    new_lines = (
        f"   INTEGER, PARAMETER :: KDM6AD_UPNC_NTARGET = {len(targets)}",
        *(
            "   INTEGER, PARAMETER :: KDM6AD_UPNC_"
            f"{axis}(KDM6AD_UPNC_NTARGET) = (/ "
            + ", ".join(str(coord[index]) for coord in targets) + " /)"
            for axis, index in (("I", 0), ("K", 1), ("J", 2))
        ),
    )
    for before, after in zip(BASE_LINES, new_lines):
        if text.count(before) != 1:
            raise ValueError("private RK trace target declaration differs")
        text = text.replace(before, after)
    return text.encode("utf-8"), targets


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--solve-source", type=Path, required=True)
    parser.add_argument("--residual-rows", type=Path, required=True)
    parser.add_argument("--solve-output", type=Path, required=True)
    args = parser.parse_args()
    sources = (args.solve_source, args.residual_rows)
    output = args.solve_output
    if (output.exists() or output.is_symlink() or output.parent.is_symlink() or
            any(output.resolve() == source.resolve() for source in sources)):
        raise FileExistsError("RK trace output must be new and distinct from inputs")
    generated, targets = render_solve(sources[0].read_bytes(), sources[1].read_bytes())
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        stream.write(generated)
    print(json.dumps({"status": "RK_TRACE_TARGETS_EXPANDED", "source_sha256": sha(generated),
                      "target_count": len(targets), "liquid_target_count": 54}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
