"""Replay a bounded source-form estimate. This does not execute the model."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
WITNESS = ROOT / "harness/evidence/east_optical_witness_2026-10-31/witness.json"
FLOOR = 10.01
PIDNI = 1570.79638671875
DATA_SHA256 = "abe2ed52c417bf38ffebf06ec32782cbbf448f624766b320da58c88278c21c97"
EXPORTER_SHA256 = "7f251057e2983fb5627aebc777c247e4ff3ad41497cf7b4312c8a0cc21fffea8"
SOURCE_SHA256 = {
    "harness/native_checkpoint_observation.py": "115bdf2b8db76b69852fe5262c01723d198660dc9be9f7361a0ed1023671ba14",
    "oracle/kdm6/constants.py": "aa489872c2b00d1160e158b9390ebe7bdcbbe4b31a468673cf22615f137f1b62",
    "oracle/kdm6/coordinator.py": "05981b7a19c8d4fe262cb8080b14ddf3b4eb5c027b58604803b2e0b80764a0bd",
    "oracle/kdm6/fconst.py": "c6529c9a543ad8ed0a33524114f30f5665cd9a7b6983b32a917cc39debd377f2",
    "oracle/kdm6/obs/model_profile_builder.py": "b9264edb61f32010c025718ad59ef686746f156e2a3c011c473943fbf82788ab",
    "oracle/kdm6/obs/native_cloud_profile.py": "2aeb687fed9f660818d76f98d1f8588e2cc21c9d20a7e471ff166a999a5d202c",
    "oracle/kdm6/rttov_bridge.py": "3c61c7fa6baa21ba294b37cdc17886c0f17979ee4adfae0af7e22154af964116",
    "oracle/kdm6/runtime.py": "e505c3a1d42fb2880d0ce3d65381488a06528de8d4133b39d4e9a573cef997ac",
    "oracle/kdm6/slope.py": "5121761c97390eb0348ad3ed1c2b8aec6ad697b839826fdcac1cd6437978e823",
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def f32(x):
    return struct.unpack(">f", struct.pack(">f", x))[0]


def value(word):
    if not isinstance(word, str) or len(word) != 8 or word.upper() != word:
        raise ValueError("invalid f32 word")
    return struct.unpack(">f", bytes.fromhex(word))[0]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify(data, witness_bytes, root=ROOT):
    require(data["schema"] == "kdm6.east_ice_radius_floor.v1", "schema")
    require(
        hashlib.sha256(witness_bytes).hexdigest() == data["witness_sha256"],
        "witness hash",
    )
    witness = json.loads(witness_bytes)
    for path, expected in data["source_sha256"].items():
        require(digest(root / path) == expected, "source hash: " + path)
    require(data["source_sha256"] == SOURCE_SHA256, "source pins")
    require(data["exporter_sha256"] == EXPORTER_SHA256, "producer pin")
    require(
        data["checkpoint_sha256"]
        == {
            "guard": witness["checkpoint_sha256"]["qnc_guard_control"],
            "pilot": witness["checkpoint_sha256"]["pilot_control"],
        },
        "checkpoint pins",
    )
    profiles = {(p["i"], p["j"]): p for p in witness["profiles"]}
    require(
        set(profiles) == {(234, j) for j in [*range(3, 12), 52]}, "profile selection"
    )
    seen = set()
    results = []
    for row in data["rows"]:
        case = row["case"]
        i = row["i"]
        j = row["j"]
        k = row["k"]
        layer = row["layer"]
        key = (case, i, j, k)
        require(key not in seen, "duplicate row")
        seen.add(key)
        require(
            case in ("guard", "pilot")
            and (i, j) in profiles
            and 1 <= k <= 39
            and layer == 66 - k,
            "row map",
        )
        op = profiles[(i, j)]["optics"][1 if case == "guard" else 2]
        require(
            row["fraction"] == op["hydro_frac.txt"]["values"][layer]
            and row["fraction"] > 0,
            "cloud fraction",
        )
        require(
            row["saved_deff_um"] == op["hydro_deff.txt"]["values"][layer],
            "saved diameter",
        )
        require(abs(row["saved_deff_um"] - 20.02) < 1e-12, "diameter floor mismatch")
        require(
            set(row["words"]) == {"QICE", "QNICE", "QSNOW", "AL", "ALB"}, "word set"
        )
        v = {name: value(word) for name, word in row["words"].items()}
        require(all(math.isfinite(x) for x in v.values()), "nonfinite input")
        require(
            v["QICE"] > 1e-15 and v["QNICE"] > 0 and v["QSNOW"] == 0,
            "ice or snow branch",
        )
        rho = f32(1.0 / f32(v["AL"] + v["ALB"]))
        require(rho > 0, "density")
        require(
            1000 * rho * (v["QICE"] + v["QSNOW"]) == op["hydro.txt"]["values"][layer],
            "ice content witness",
        )
        ni = v["QNICE"] * rho
        den = max(v["QICE"] * rho, 1e-30)
        ratio = max(PIDNI * ni / den, 1e-30)
        inv = f32(1.0 / 3.0)
        raw_rslope = 1.0 / math.exp(math.log(ratio) * inv)
        clamped = max(1 / 1820000.0, min(raw_rslope, 1 / 9080.0))
        radius_um = clamped * 1e6 / 6.0
        require(radius_um < FLOOR, "radius not below floor")
        results.append(
            {
                "case": case,
                "i": i,
                "j": j,
                "k": k,
                "layer": layer,
                "radius_um": radius_um,
                "floor_margin_um": FLOOR - radius_um,
                "raw_rslope_m": raw_rslope,
                "rho_d": rho,
            }
        )
    require(
        len(seen) == 84
        and all(sum(r["case"] == c for r in results) == 42 for c in ("guard", "pilot")),
        "row counts",
    )
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--exporter", type=Path, help="optional private exporter to verify"
    )
    args = parser.parse_args()
    data_bytes = (HERE / "data.json").read_bytes()
    require(hashlib.sha256(data_bytes).hexdigest() == DATA_SHA256, "data hash")
    if args.exporter is not None:
        require(digest(args.exporter) == EXPORTER_SHA256, "private exporter hash")
    data = json.loads(data_bytes)
    witness_bytes = WITNESS.read_bytes()
    results = verify(data, witness_bytes)
    for case in ("guard", "pilot"):
        a = [r for r in results if r["case"] == case]
        best = min(a, key=lambda r: r["floor_margin_um"])
        print(
            case,
            "rows",
            len(a),
            "interior",
            sum(r["radius_um"] > FLOOR for r in a),
            "range_um",
            min(r["radius_um"] for r in a),
            max(r["radius_um"] for r in a),
            "nearest",
            best,
        )


if __name__ == "__main__":
    main()
