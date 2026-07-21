#!/usr/bin/env python3
"""Focused G3.3-M check for the final sedimentation-to-surface causal path.

This deliberately stays separate from g33_selfcheck.check_algorithm(): the main
checker already proves the qr/nr substep ladder. This check proves only the
remaining load-bearing edge:

    final main-substep QR_FALLACC(k=K-1)
        -> surface.bottom_fall_qr
        -> left-associated per-species total
        -> actual rain/snow/graupel increments.

The surface arithmetic is independently replayed from dumped operands at f32
operation boundaries. No driver fixture value is used as an expected result.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import g33_dump as gd
import g33_expectation as ge
import g33_run_env as gre

B, K = 3, 4
QCRMIN, DTCLD, DENR = 1.0e-9, 20.0, 1000.0
EXIT_SKIP, EXIT_DRIVER, EXIT_EVIDENCE, EXIT_FIDELITY = 2, 3, 4, 5


def _die(code: int, message: str) -> None:
    print(message, file=sys.stderr, flush=True)
    raise SystemExit(code)


def _schedule(algorithm: str) -> dict:
    return {
        "case_id": "surface-selfcheck",
        "pair_id": "surface-pair",
        "backend": "cpp",
        "algorithm": algorithm,
        "B": B,
        "K": K,
        "loops": 1,
        "mstepmax_main": [2],
        "mstepmax_ice": [1],
        "species_scope": ["qr", "nr"],
        "qcrmin": QCRMIN,
        "dtcld": DTCLD,
        "instrumented_stages": ["substep_pre", "op", "substep_post", "surface"],
    }


def _record(records: list[dict], **key) -> dict:
    hits = [r for r in records if all(r.get(k) == v for k, v in key.items())]
    if len(hits) != 1:
        _die(EXIT_EVIDENCE, f"FAIL: {len(hits)} records match {key} (want exactly 1)")
    return hits[0]


def _f32(record: dict) -> np.ndarray:
    if record["dtype"] != "f32" or len(record["payload"]) % 4:
        _die(EXIT_EVIDENCE, f"FAIL: {record.get('field')} is not a whole f32 payload")
    return np.frombuffer(record["payload"], dtype=">f4").astype(np.float32)


def _bits(values: np.ndarray) -> bytes:
    return np.asarray(values, dtype=np.float32).astype(">f4").tobytes()


def _same_shape(*arrays: np.ndarray) -> None:
    shapes = {a.shape for a in arrays}
    if len(shapes) != 1:
        raise gd.G33Corruption(f"surface operands have different shapes: {sorted(shapes)}")


def recompute_surface(qr: np.ndarray, qs: np.ndarray, qg: np.ndarray,
                      qi: np.ndarray, delz: np.ndarray, dtcld: float = DTCLD) -> dict:
    """Replay surface_accumulation_torch in its exact left-associated f32 order."""
    _same_shape(qr, qs, qg, qi, delz)
    for name, array in (("qr", qr), ("qs", qs), ("qg", qg),
                        ("qi", qi), ("delz", delz)):
        if not np.isfinite(array).all():
            raise gd.G33Corruption(f"surface operand {name} is non-finite")
    if any((a < 0).any() for a in (qr, qs, qg, qi)):
        raise gd.G33Corruption("surface bottom-fall operand is negative")
    if (delz <= 0).any():
        raise gd.G33Corruption("surface delz_bottom is non-positive")

    total = (qr + qs).astype(np.float32)
    total = (total + qg).astype(np.float32)
    total = (total + qi).astype(np.float32)
    snow_total = (qs + qi).astype(np.float32)

    def increment(fall: np.ndarray) -> np.ndarray:
        out = np.maximum(fall, np.float32(0.0)).astype(np.float32)
        out = (out * delz).astype(np.float32)
        out = (out / np.float32(DENR)).astype(np.float32)
        out = (out * np.float32(dtcld)).astype(np.float32)
        return (out * np.float32(1000.0)).astype(np.float32)

    return {
        "bottom_fall_total": total,
        "rain_increment": increment(total),
        "snow_increment": increment(snow_total),
        "graupel_increment": increment(qg),
    }


def check_algorithm(driver: Path, algorithm: str, workdir: Path) -> dict:
    schedule = _schedule(algorithm)
    env = gre.build_env(
        schedule,
        workdir,
        binary=driver,
        column_map=[[i, 0, i, i] for i in range(B)],
        run_uuid=f"surface-{algorithm}-{uuid.uuid4().hex[:12]}",
        column_layout_id="surface-selfcheck-3col",
    )
    result = subprocess.run(
        [str(driver), algorithm], env={**os.environ, **env},
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        _die(EXIT_DRIVER,
             f"FAIL: surface driver rc={result.returncode}\n{result.stdout}{result.stderr}")

    contract_bytes = (workdir / "run_contract.json").read_bytes()
    file_sha = hashlib.sha256(contract_bytes).hexdigest()
    sealed_sha = env["KDM6_G33_RUN_CONTRACT_SHA256"]
    if file_sha != sealed_sha:
        _die(EXIT_EVIDENCE, "FAIL: surface run_contract.json changed after the run")
    try:
        contract = json.loads(contract_bytes.decode("utf-8"))
        containers = contract["containers"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        _die(EXIT_EVIDENCE, f"FAIL: malformed surface run contract: {exc}")

    generated = ge.run_index(schedule)["containers"]
    if containers != generated:
        _die(EXIT_EVIDENCE,
             "FAIL: generated surface container index differs from the sealed contract")

    dump_dir = Path(env["KDM6_G33_DUMP_DIR"])
    on_disk = sorted(p.name for p in dump_dir.glob("*.g33"))
    expected = sorted(c["path"] for c in containers)
    if on_disk != expected:
        _die(EXIT_EVIDENCE,
             f"FAIL surface container set:\n  disk    {on_disk}\n  sealed  {expected}")

    main_specs = [c for c in containers if c["chain"] == "main"]
    surface_specs = [c for c in containers if c["container_id"] == "L1_surface"]
    if not main_specs or len(surface_specs) != 1:
        _die(EXIT_EVIDENCE, "FAIL: surface contract lacks main or unique surface container")
    last_main_spec = max(main_specs, key=lambda c: int(c["n"]))
    surface_spec = surface_specs[0]

    last_main = gd.read_container(dump_dir / last_main_spec["path"])
    surface = gd.read_container(dump_dir / surface_spec["path"])
    for container, spec in ((last_main, last_main_spec), (surface, surface_spec)):
        if container["header"].get("run_contract_sha256") != sealed_sha:
            _die(EXIT_EVIDENCE,
                 f"FAIL: {spec['container_id']} sealed the wrong run contract")

    main_records = last_main["records"]
    surface_records = surface["records"]
    k_bottom = K - 1

    qr_fall = _record(
        main_records, stage="op", k=k_bottom, species="qr",
        op_id="QR_FALLACC", field="fall_after")
    surface_qr = _record(surface_records, stage="surface", field="bottom_fall_qr")
    if qr_fall["payload"] != surface_qr["payload"]:
        _die(EXIT_FIDELITY,
             f"FAIL surface-link: {algorithm} L1_surface bottom_fall_qr != "
             f"{last_main_spec['container_id']} QR_FALLACC(k={k_bottom}).fall_after")

    pre_delz = _record(main_records, stage="substep_pre", field="delz_raw")
    delz_all = _f32(pre_delz)
    if delz_all.size != B * K:
        _die(EXIT_EVIDENCE, "FAIL: substep_pre.delz_raw has the wrong size")
    delz_expected = delz_all.reshape(B, K)[:, k_bottom]
    delz_record = _record(surface_records, stage="surface", field="delz_bottom")
    if delz_record["payload"] != _bits(delz_expected):
        _die(EXIT_FIDELITY,
             f"FAIL surface-link: {algorithm} L1_surface delz_bottom != "
             f"{last_main_spec['container_id']} substep_pre.delz_raw[:, {k_bottom}]")

    fields = {name: _f32(_record(surface_records, stage="surface", field=name))
              for name in ("bottom_fall_qr", "bottom_fall_qs", "bottom_fall_qg",
                           "bottom_fall_qi", "bottom_fall_total", "delz_bottom",
                           "rain_increment", "snow_increment", "graupel_increment")}
    offline = recompute_surface(
        fields["bottom_fall_qr"], fields["bottom_fall_qs"],
        fields["bottom_fall_qg"], fields["bottom_fall_qi"],
        fields["delz_bottom"], DTCLD)
    for name, expected_values in offline.items():
        record = _record(surface_records, stage="surface", field=name)
        if record["payload"] != _bits(expected_values):
            _die(EXIT_FIDELITY,
                 f"FAIL surface-offline: {algorithm} L1_surface {name}")

    return {"containers": len(containers), "surface_fields": len(fields)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--driver", type=Path, required=True)
    parser.add_argument("--algorithm", choices=("legacy", "conservative", "both"),
                        default="both")
    args = parser.parse_args()
    if not args.driver.is_file():
        _die(EXIT_SKIP, f"SKIP: surface driver not found: {args.driver}")

    algorithms = ("legacy", "conservative") if args.algorithm == "both" else (args.algorithm,)
    root = Path(tempfile.mkdtemp(prefix="g33-surface-selfcheck-"))
    try:
        for algorithm in algorithms:
            stats = check_algorithm(args.driver, algorithm, root / algorithm)
            print(f"{algorithm}: SURFACE PASS — {stats['containers']} containers, "
                  f"qr bottom link + {stats['surface_fields']} fields bit-exact")
        print("SURFACE SELF-CHECK PASS")
    except SystemExit:
        print(f"(evidence preserved at {root})", file=sys.stderr)
        raise
    else:
        shutil.rmtree(root)


if __name__ == "__main__":
    main()
