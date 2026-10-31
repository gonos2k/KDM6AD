"""Offline export and replay of a completed, locked four-arm diagnostic.

No RTTOV, KDM, host or optimizer call is made here.
"""

import argparse
import hashlib
import json
import math
import re
from pathlib import Path
import subprocess
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
WITNESS = HERE.parent / "east_optical_witness_2026-10-31"
ARMS = ("GG", "PG", "GP", "PP")
JS = [*range(3, 12), 52]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(obj):
    return (json.dumps(obj, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def check(condition, message):
    if not condition:
        raise ValueError(message)


def check_source_pins():
    manifest = json.loads((HERE / "source_manifest.json").read_bytes())
    check(
        manifest.get("schema") == "east-optical-factorial-source-v1"
        and set(manifest.get("sha256", {}))
        == {
            "packet.py",
            "test_packet.py",
            "README.md",
            "excluded_attempts.json",
            "export.json",
            "analysis.json",
            "private_verifier_summary.json",
            *(f"raw/{a}.txt" for a in ARMS),
        },
        "source inventory differs",
    )
    for name, expected in manifest["sha256"].items():
        check(
            digest((HERE / name).read_bytes()) == expected,
            "packet source changed: " + name,
        )


def historical():
    # The parent replay checks its sources, receipt mappings and public direct captures.
    subprocess.run(
        [sys.executable, str(WITNESS / "replay.py")],
        cwd=REPO,
        check=True,
        capture_output=True,
    )
    return json.loads((WITNESS / "witness.json").read_bytes())


def verify_case_files(case, expected):
    wanted = {
        k: v
        for k, v in expected.items()
        if k.startswith("in/")
        or k in ("out/rttov_test.txt", "out/run.sh", "out/env.sh")
    }
    found = {
        "in/" + p.relative_to(case / "in").as_posix(): digest(p.read_bytes())
        for p in (case / "in").rglob("*")
        if p.is_file()
    }
    for name in ("out/rttov_test.txt", "out/run.sh", "out/env.sh"):
        found[name] = digest((case / name).read_bytes())
    check(found == wanted, "consumed case files differ from preflight pins")


def export(prepared, results):
    pins_raw = (prepared / "pins.json").read_bytes()
    pins = json.loads(pins_raw)
    pin_sha = digest(pins_raw)
    witness = historical()
    mapping = pins["mapping"]
    check(
        [m["j"] for m in mapping] == JS and len(mapping) == 10,
        "profile mapping differs",
    )
    for m, p in zip(mapping, witness["profiles"]):
        check(
            m["flat"] == p["flat"]
            and m["chunk"] == p["chunk"]
            and m["guard_ordinal"] == int(p["case_profiles_1based"][1])
            and m["pilot_ordinal"] == int(p["case_profiles_1based"][2]),
            "historical mapping differs",
        )
    attempt_raw = (results / "attempt.json").read_bytes()
    attempt = json.loads(attempt_raw)
    check(
        attempt["manifest_sha256"] == pin_sha
        and attempt["corners"] == list(ARMS)
        and attempt["K_calls"] == 0
        and pins["direct_calls"] == 0,
        "attempt metadata differs",
    )
    check(set(pins["cases"]) == set(ARMS), "arm inventory differs")
    # Independently check that only slot 7 of the two declared inputs varies.
    inputs = {}
    for name in ARMS:
        case = results / name
        verify_case_files(case, pins["cases"][name])
        inputs[name] = {
            p.relative_to(case / "in").as_posix(): p.read_bytes()
            for p in (case / "in").rglob("*")
            if p.is_file()
        }
    for name in ARMS[1:]:
        check(set(inputs[name]) == set(inputs["GG"]), "input inventory differs")
        for path, raw in inputs["GG"].items():
            if path.endswith(("/atm/hydro.txt", "/atm/hydro_deff.txt")):
                a = [line.split() for line in raw.splitlines()]
                b = [line.split() for line in inputs[name][path].splitlines()]
                check(
                    len(a) == len(b)
                    and all(
                        len(x) == len(y)
                        and len(x) >= 7
                        and x[:6] + x[7:] == y[:6] + y[7:]
                        for x, y in zip(a, b)
                    ),
                    "non-slot-7 input differs",
                )
                # First letter controls content; second controls effective diameter.
                selected = name[0] if path.endswith("/atm/hydro.txt") else name[1]
                ref = "PP" if selected == "P" else "GG"
                check(
                    [x[6] for x in b]
                    == [x.split()[6] for x in inputs[ref][path].splitlines()],
                    "factor assignment differs",
                )
            else:
                check(raw == inputs[name][path], "background input differs")
    for i, profile in enumerate(witness["profiles"], 1):
        for arm, state in (("GG", 1), ("PP", 2)):
            for filename in ("hydro.txt", "hydro_deff.txt"):
                raw = inputs[arm][f"profiles/{i:03d}/atm/{filename}"]
                values = [float(row.split()[6]) for row in raw.splitlines()]
                check(
                    values == profile["optics"][state][filename]["values"],
                    "endpoint optical values differ",
                )
    arms = {}
    for name in ARMS:
        case = results / name
        verify_case_files(case, pins["cases"][name])
        receipt_raw = (case / "result.json").read_bytes()
        receipt = json.loads(receipt_raw)
        capture = (case / "result.npz").read_bytes()
        check(
            receipt["manifest_sha256"] == pin_sha
            and receipt["result_sha256"] == digest(capture)
            and receipt["direct_calls"] == 1
            and receipt["K_calls"] == 0
            and receipt["coordinate"] == {"bt_coordinate": "kma_v3_0"},
            "result receipt differs",
        )
        import io

        with np.load(io.BytesIO(capture), allow_pickle=False) as z:
            bt, quality = z["bt"], z["quality"]
            check(
                bt.shape == (10, 7)
                and quality.shape == (10, 7)
                and np.isfinite(bt).all()
                and (quality == 0).all(),
                "BT or quality invalid",
            )
            arms[name] = {
                "bt": bt.tolist(),
                "quality": quality.tolist(),
                "capture_sha256": digest(capture),
                "receipt_sha256": digest(receipt_raw),
                "receipt": receipt,
            }
    # Hash every original source pin without exposing private filesystem paths.
    for path, expected in pins["source_pins"].items():
        check(
            digest(Path(path).read_bytes()) == expected,
            "source, runtime or asset pin changed",
        )
    source_hashes = sorted(
        (
            {"name": Path(path).name, "sha256": value}
            for path, value in pins["source_pins"].items()
        ),
        key=lambda x: (x["name"], x["sha256"]),
    )
    check(
        source_hashes and all(len(x["sha256"]) == 64 for x in source_hashes),
        "source pins missing",
    )
    return {
        "schema": "east-optical-factorial-export-v1",
        "manifest_sha256": pin_sha,
        "attempt_sha256": digest(attempt_raw),
        "attempt": attempt,
        "source_hashes": source_hashes,
        "source_tree_sha256": pins["source_tree_sha256"],
        "runtime": pins["runtime"],
        "case_input_hashes": pins["cases"],
        "mapping": mapping,
        "arms": arms,
        "recorded_direct_calls": 4,
        "recorded_K_calls": 0,
        "witness_sha256": digest((WITNESS / "witness.json").read_bytes()),
    }


def raw_field(raw, field):
    matches = re.findall(rb"RADIANCE%" + field.encode() + rb"\s*=\s*\(([^)]*)\)", raw)
    check(len(matches) == 1, "raw radiance field missing or duplicated")
    values = [float(v.replace(b"D", b"E")) for v in matches[0].split()]
    check(
        len(values) == 70 and all(math.isfinite(v) for v in values),
        "raw radiance shape or values differ",
    )
    return values


def raw_differences():
    summary = json.loads((HERE / "private_verifier_summary.json").read_bytes())
    raw = {}
    for arm in ARMS:
        content = (HERE / "raw" / f"{arm}.txt").read_bytes()
        check(
            digest(content) == summary["results"][arm]["radiance"],
            "raw radiance SHA differs",
        )
        raw[arm] = {f: raw_field(content, f) for f in ("TOTAL", "BT")}
    effects = {}
    for field in ("TOTAL", "BT"):
        effects[field] = {}
        for label, a, b in (("GP_minus_GG", "GP", "GG"), ("PP_minus_PG", "PP", "PG")):
            d = [x - y for x, y in zip(raw[a][field], raw[b][field])]
            effects[field][label] = {
                "differences": d,
                "nonzero": sum(x != 0 for x in d),
                "max_abs": max(map(abs, d)),
            }
    return effects


def analyze(packet, witness):
    check(
        packet["schema"] == "east-optical-factorial-export-v1"
        and packet["recorded_direct_calls"] == 4
        and packet["recorded_K_calls"] == 0
        and packet["witness_sha256"] == digest((WITNESS / "witness.json").read_bytes()),
        "export identity differs",
    )
    check(set(packet["arms"]) == set(ARMS), "arm inventory differs")
    check([m["j"] for m in packet["mapping"]] == JS, "mapping differs")
    result = []
    for i, (m, p) in enumerate(zip(packet["mapping"], witness["profiles"])):
        check(
            m["flat"] == p["flat"]
            and m["chunk"] == p["chunk"]
            and m["guard_ordinal"] == int(p["case_profiles_1based"][1])
            and m["pilot_ordinal"] == int(p["case_profiles_1based"][2]),
            "mapping differs",
        )
        cells = []
        for c, obs in enumerate(p["observation"]):
            b = {}
            for arm in ARMS:
                data = packet["arms"][arm]
                check(
                    len(data["bt"]) == len(data["quality"]) == 10
                    and all(len(row) == 7 for row in data["bt"])
                    and all(len(row) == 7 for row in data["quality"]),
                    "matrix shape differs",
                )
                v = data["bt"][i][c]
                check(
                    isinstance(v, (float, int))
                    and math.isfinite(v)
                    and data["quality"][i][c] == 0,
                    "quality differs",
                )
                b[arm] = float(v)
            h = {
                a: (0.5 * (v - obs) ** 2 if abs(v - obs) <= 1 else abs(v - obs) - 0.5)
                for a, v in b.items()
            }

            def effects(x):
                return {
                    "content_at_guard_diameter": x["PG"] - x["GG"],
                    "diameter_at_guard_content": x["GP"] - x["GG"],
                    "content_at_pilot_diameter": x["PP"] - x["GP"],
                    "diameter_at_pilot_content": x["PP"] - x["PG"],
                    "interaction": x["PP"] - x["PG"] - x["GP"] + x["GG"],
                }

            cells.append(
                {
                    "channel": c + 10,
                    "bt": b,
                    "huber": h,
                    "bt_effects": effects(b),
                    "huber_effects": effects(h),
                    "GG_minus_historical_guard": b["GG"] - p["bt"][1][c],
                    "PP_minus_historical_pilot": b["PP"] - p["bt"][2][c],
                }
            )
        result.append({"j": m["j"], "flat": m["flat"], "cells": cells})
    numerator = math.fsum(
        cell["huber_effects"]["content_at_guard_diameter"]
        for profile in result
        for cell in profile["cells"]
    )
    summary = {
        "huber_content_numerator_fsum": numerator,
        "huber_content_mean_70_cells": numerator / 70,
        "huber_content_fixed_m0_contribution": numerator / 377342,
    }
    return {
        "schema": "east-optical-factorial-analysis-v1",
        "profiles": result,
        "summary": summary,
        "support_denominator": 377342,
        "huber_delta": 1,
        "model_calls_in_replay": 0,
        "recorded_direct_calls": 4,
        "raw_diameter_differences": raw_differences(),
    }


def main():
    check_source_pins()
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)
    ex = sub.add_parser("export")
    ex.add_argument("prepared", type=Path)
    ex.add_argument("results", type=Path)
    ex.add_argument("output", type=Path)
    rp = sub.add_parser("replay")
    rp.add_argument("packet", type=Path)
    args = parser.parse_args()
    if args.action == "export":
        payload = encoded(export(args.prepared, args.results))
        with args.output.open("xb") as f:
            f.write(payload)
        print(json.dumps({"export_sha256": digest(payload), "model_calls": 0}))
    else:
        print(
            encoded(
                analyze(json.loads(args.packet.read_bytes()), historical())
            ).decode(),
            end="",
        )


if __name__ == "__main__":
    main()
