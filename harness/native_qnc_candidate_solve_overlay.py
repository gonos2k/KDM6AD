"""Expand only the RK trace-target roster in pinned PR474 solve source.

This is a source-only overlay: no process, tendency, or state arithmetic is
changed. It preserves all 61 PR474 targets in their existing order, then adds
the sorted liquid-failure / six-face-neighbor union not already present.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
import sys

REPOSITORY = Path(__file__).resolve().parents[1]
if str(REPOSITORY) not in sys.path:
    sys.path.insert(0, str(REPOSITORY))

from harness.native_qnc_domain_preflight_advect_overlay import (  # noqa: E402
    FAILURE_JSON_SHA256,
    failure_layer_coordinates,
)


SOLVE_SOURCE_SHA256 = "1453510a18f4e4beab33c3247b8200ae5ea34007b6f7bbdc44297bd3b288c1ea"
BASE_TARGET_COUNT = 61
TARGET_FACE_NEIGHBORS = (
    (-1, 0, 0), (1, 0, 0),
    (0, -1, 0), (0, 1, 0),
    (0, 0, -1), (0, 0, 1),
)
EXPECTED_UNION_COUNT = 374
SEAM_SENTINELS_IKJ = (
    (113, 12, 142), (113, 12, 143),
    (116, 6, 142), (116, 6, 143),
    (131, 8, 142), (131, 8, 143),
    (198, 12, 142), (198, 12, 143),
)
EXPECTED_FINAL_TARGET_COUNT = 383
ARRAYS = (("I", 0), ("K", 1), ("J", 2))


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _array_pattern(axis: str) -> re.Pattern[str]:
    return re.compile(
        rf"(?m)^(\s*INTEGER, PARAMETER :: KDM6AD_UPNC_{axis}"
        rf"\(KDM6AD_UPNC_NTARGET\) = \(/\s*)([0-9,\s]+?)(\s*/\)\s*)$"
    )


def _parse_targets(source: bytes) -> tuple[int, tuple[tuple[int, int, int], ...]]:
    try:
        text = source.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("PR474 solve source must be UTF-8") from exc
    count_matches = re.findall(
        r"(?m)^\s*INTEGER, PARAMETER :: KDM6AD_UPNC_NTARGET = ([0-9]+)\s*$", text)
    if len(count_matches) != 1:
        raise ValueError("solve target count declaration differs")
    count = int(count_matches[0])
    columns: dict[str, tuple[int, ...]] = {}
    for axis, _ in ARRAYS:
        matches = list(_array_pattern(axis).finditer(text))
        if len(matches) != 1:
            raise ValueError(f"PR474 {axis} target declaration differs")
        values = tuple(int(token.strip()) for token in matches[0].group(2).split(","))
        if len(values) != count or any(value < 1 for value in values):
            raise ValueError(f"PR474 {axis} target array inventory differs")
        columns[axis] = values
    targets = tuple(zip(columns["I"], columns["K"], columns["J"]))
    if len(set(targets)) != count:
        raise ValueError("solve target arrays contain duplicate coordinates")
    return count, targets


def parse_existing_targets(source: bytes) -> tuple[tuple[int, int, int], ...]:
    count, targets = _parse_targets(source)
    if count != BASE_TARGET_COUNT:
        raise ValueError("PR474 solve target count declaration differs")
    return targets


def candidate_union(failure_json: bytes) -> tuple[tuple[int, int, int], ...]:
    if sha(failure_json) != FAILURE_JSON_SHA256:
        raise ValueError("PR466 residual_reason_rows.json SHA differs")
    failed = set(failure_layer_coordinates(failure_json))
    union = set(failed)
    for i, k, j in failed:
        for di, dk, dj in TARGET_FACE_NEIGHBORS:
            neighbor = (i + di, k + dk, j + dj)
            if not (1 <= neighbor[0] <= 234 and 1 <= neighbor[1] <= 39 and
                    1 <= neighbor[2] <= 282):
                raise ValueError("failed-layer face neighbor falls outside native mass grid")
            union.add(neighbor)
    result = tuple(sorted(union))
    if len(result) != EXPECTED_UNION_COUNT:
        raise ValueError("failed-layer plus six-face-neighbor union count differs")
    return result


def build_target_inventory(source: bytes, failure_json: bytes) -> tuple[tuple[int, int, int], ...]:
    base = parse_existing_targets(source)
    union = candidate_union(failure_json)
    if not set(failure_layer_coordinates(failure_json)).issubset(base):
        raise ValueError("PR474 prefix no longer contains all liquid failure layers")
    additions = tuple(coord for coord in union if coord not in set(base))
    if any(coord in union or coord in base for coord in SEAM_SENTINELS_IKJ):
        raise ValueError("seam sentinel duplicates the selected target/receiver union")
    targets = base + additions + SEAM_SENTINELS_IKJ
    if (len(targets) != EXPECTED_FINAL_TARGET_COUNT or
            len(set(targets)) != EXPECTED_FINAL_TARGET_COUNT or
            additions != tuple(sorted(additions))):
        raise ValueError("candidate target suffix is not the sorted unique neighbor extension")
    return targets


def render_solve(source: bytes, failure_json: bytes) -> tuple[bytes, tuple[tuple[int, int, int], ...]]:
    if sha(source) != SOLVE_SOURCE_SHA256:
        raise ValueError("PR474 private solve source SHA differs")
    base = parse_existing_targets(source)
    targets = build_target_inventory(source, failure_json)
    text = source.decode("utf-8")

    old_count = "   INTEGER, PARAMETER :: KDM6AD_UPNC_NTARGET = 61"
    if text.count(old_count) != 1:
        raise ValueError("PR474 target count source anchor differs")
    text = text.replace(old_count,
                        f"   INTEGER, PARAMETER :: KDM6AD_UPNC_NTARGET = {len(targets)}")
    for axis, index in ARRAYS:
        pattern = _array_pattern(axis)
        matches = list(pattern.finditer(text))
        if len(matches) != 1:
            raise ValueError(f"PR474 {axis} target source anchor differs")
        match = matches[0]
        values = ", ".join(str(coord[index]) for coord in targets)
        replacement = match.group(1) + values + match.group(3)
        text = text[:match.start()] + replacement + text[match.end():]

    result = text.encode("utf-8")
    final_count, final_targets = _parse_targets(result)
    if final_count != len(targets) or final_targets[:BASE_TARGET_COUNT] != base:
        raise ValueError("PR474 first 61 target indices were not preserved")
    return result, targets


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--solve-source", type=Path, required=True)
    parser.add_argument("--failure-json", type=Path, required=True)
    parser.add_argument("--solve-output", type=Path, required=True)
    args = parser.parse_args()
    output = args.solve_output
    inputs = (args.solve_source, args.failure_json)
    if (output.exists() or output.is_symlink() or output.parent.is_symlink() or
            any(output.resolve() == source.resolve() for source in inputs)):
        raise FileExistsError("overlay output must be new and distinct from pinned inputs")
    raw_source, raw_failure = (path.read_bytes() for path in inputs)
    rendered, targets = render_solve(raw_source, raw_failure)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        stream.write(rendered)
    base_count = len(parse_existing_targets(raw_source))
    print(json.dumps({
        "status": "QNC_CANDIDATE_RK_TARGET_SOURCE_WRITTEN",
        "solve_source_sha256": SOLVE_SOURCE_SHA256,
        "failure_json_sha256": FAILURE_JSON_SHA256,
        "base_target_count": base_count,
        "liquid_neighbor_union_count": len(candidate_union(raw_failure)),
        "appended_target_count": len(targets) - base_count,
        "seam_sentinel_count": len(SEAM_SENTINELS_IKJ),
        "final_target_count": len(targets),
        "output_sha256": sha(rendered),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
