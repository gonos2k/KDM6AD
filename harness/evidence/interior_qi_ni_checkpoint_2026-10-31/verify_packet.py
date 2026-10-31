#!/usr/bin/env python3
"""Inspect pinned capture bytes and replay serialized optical secants; no model calls."""

import hashlib
import io
import json
import math
import re
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
PACKET = ROOT / "packet"
MANIFEST_SHA = "e02527838e173f81827468d627531cdef7a06d666e6216b2aced814c4b81e3a6"
HS = (1e-4, 2e-4, 4e-4, 8e-4)


def check(value, message):
    if not value:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def raw_blocks(data):
    text = data.decode("ascii")
    check(len(text) < 1000000, "raw length")
    result = {}
    for name in ("TOTAL", "BT", "QUALITY"):
        matches = re.findall(
            r"(?m)^RADIANCE%" + name + r"\s*=\s*\(\s*([\s\S]*?)\s*\)", text
        )
        check(len(matches) == 1, "raw block " + name)
        values = np.asarray([float(x.replace("D", "E")) for x in matches[0].split()])
        check(values.shape == (7,) and np.isfinite(values).all(), "raw shape or finite")
        result[name] = values
    check(
        np.all(result["QUALITY"] == 0) and np.all(result["TOTAL"] > 0),
        "raw quality or total",
    )
    return result


def verify_sources():
    source_manifest = json.loads((ROOT / "source_manifest.json").read_bytes())
    check(
        set(source_manifest)
        == {"verify_packet.py", "replay.py", "export.py", "test_replay.py"},
        "source inventory",
    )
    for name, expected in source_manifest.items():
        check(sha((ROOT / name).read_bytes()) == expected, "source digest " + name)
    expected_coordinate = (
        "e1aec7c9270bbeff6dec9aee0f7b3fa3741528b3e060bc3aa74be721e3ac97cc"
    )
    source = ROOT.parents[2] / "oracle/kdm6/obs/ami_bt_coordinate.py"
    check(sha(source.read_bytes()) == expected_coordinate, "coordinate source digest")


def main():
    verify_sources()
    manifest_raw = (PACKET / "manifest.json").read_bytes()
    check(sha(manifest_raw) == MANIFEST_SHA, "manifest pin")
    manifest = json.loads(manifest_raw)
    files = {str(x.relative_to(PACKET)) for x in PACKET.rglob("*") if x.is_file()} - {
        "manifest.json"
    }
    check(files == set(manifest), "inventory")
    data = {name: (PACKET / name).read_bytes() for name in manifest}
    for name, raw in data.items():
        check(sha(raw) == manifest[name], "digest " + name)
    attempt = json.loads(data["results/attempt.json"])
    check(
        attempt["planned_combined_direct_k"] == 1
        and attempt["planned_direct_only"] == 8,
        "planned calls",
    )
    check(attempt["lock_sha256"] == sha(data["lock.json"]), "lock")
    lock = json.loads(data["lock.json"])
    pins = json.loads(data["prepared/pins.json"])
    check(
        pins["checkpoint_sha256"]
        == "950bc5d67dc8cf4980091ecac19a9b7b1ba94756e83d9bd101180e55863c0bb6",
        "checkpoint pin",
    )
    audit = json.loads(data["results/independent_audit.json"])
    check(
        audit["executor_summary_sha256"] == sha(data["results/summary.json"]),
        "summary binding",
    )
    check(audit["lock_sha256"] == sha(data["lock.json"]), "audit lock")
    names = ["baseline"] + [f"h{i}_{s}" for i in range(4) for s in ("plus", "minus")]
    cal_raw = (
        ROOT.parents[2] / "oracle/kdm6/obs/data/gk2a_ami_cal_202507190000.json"
    ).read_bytes()
    check(
        sha(cal_raw)
        == "a6f830aa04e19f6982aa6ff36e832464a5b32fdcf8200211956969d5eb48325d",
        "calibration",
    )
    cal = json.loads(cal_raw)["channels"]
    channels = ("wv073", "ir087", "ir096", "ir105", "ir112", "ir123", "ir133")
    arrays = {}
    optics = {}
    for name in names:
        prefix = f"results/{name}/"
        receipt = json.loads(data[prefix + "receipt.json"])
        ca = json.loads(data[prefix + "attempt.json"])
        check(
            receipt["pre_input_hashes"]
            == receipt["post_input_hashes"]
            == ca["input_hashes"],
            "input attestation",
        )
        check(
            receipt["mode"]
            == ("combined_direct_k" if name == "baseline" else "direct_only"),
            "mode",
        )
        check(
            receipt["values_sha256"] == sha(data[prefix + "values.npz"]),
            "values receipt",
        )
        raw = data[prefix + "out/direct/radiance.txt"]
        check(sha(raw) == receipt["outputs"]["radiance.txt"], "direct raw receipt")
        blocks = raw_blocks(raw)
        with np.load(io.BytesIO(data[prefix + "values.npz"]), allow_pickle=False) as z:
            arrays[name] = {key: z[key].copy() for key in z.files}
        saved = arrays[name]["direct_bt" if name == "baseline" else "bt"][0]
        for j, channel in enumerate(channels):
            c = cal[channel]
            nu = float(c["bt_wavenumber_cm1"]) * 100
            planck, light, boltz = (
                float(c["Plank_constant_h"]),
                float(c["light_speed"]),
                float(c["Boltzmann_constant_k"]),
            )
            teff = (planck * light * nu / boltz) / math.log1p(
                (2 * planck * light * light * nu**3) / (blocks["TOTAL"][j] * 1e-5)
            )
            bt = (
                float(c["Teff_to_Tbb_c0"])
                + float(c["Teff_to_Tbb_c1"]) * teff
                + float(c["Teff_to_Tbb_c2"]) * teff * teff
            )
            check(
                abs(bt - saved[j]) <= 64 * np.finfo(np.float64).eps * 300,
                "raw-to-KMA BT",
            )
            if name == "baseline":
                check(
                    abs(bt - arrays[name]["bt"][0, j])
                    <= 64 * np.finfo(np.float64).eps * 300,
                    "raw-to-KMA baseline K BT",
                )
        for f in ("hydro.txt", "hydro_deff.txt"):
            path = "profiles/001/atm/" + f
            raw = data[prefix + "in/" + path]
            check(
                sha(raw)
                == lock["cases"][name][path]
                == receipt["pre_input_hashes"][path],
                "optical input hash",
            )
            arr = np.asarray(
                [
                    [float(v) for v in row.split()]
                    for row in raw.decode("ascii").splitlines()
                ]
            )
            check(
                arr.shape == (66, 8 if f == "hydro.txt" else 7)
                and np.isfinite(arr).all(),
                "optical shape",
            )
            optics[(name, f)] = arr
    baseline_inputs = lock["cases"]["baseline"]
    for name in names[1:]:
        for field, value in baseline_inputs.items():
            if field not in (
                "profiles/001/atm/hydro.txt",
                "profiles/001/atm/hydro_deff.txt",
            ):
                check(lock["cases"][name][field] == value, "fixed input hash")
        for field in ("hydro.txt", "hydro_deff.txt"):
            mask = np.ones(optics[(name, field)].shape, dtype=bool)
            mask[45, 6] = False
            check(
                optics[(name, field)][45, 6] != optics[("baseline", field)][45, 6],
                "individual target serialized change",
            )
            check(
                np.array_equal(
                    optics[(name, field)][mask], optics[("baseline", field)][mask]
                ),
                "off-target serialized change",
            )
        i = int(name[1])
        sign = 1 if name.endswith("plus") else -1
        record = pins["records"][name]
        baseline_record = pins["records"]["baseline"]
        check(
            np.float32(record["qi_f32"])
            == np.float32(baseline_record["qi_f32"] * (1 + sign * HS[i])),
            "QI REAL4",
        )
        check(
            np.float32(record["ni_f32"])
            == np.float32(baseline_record["ni_f32"] * (1 - sign * HS[i])),
            "NI REAL4",
        )
        check(
            record["hydro7"] == optics[(name, "hydro.txt")][45, 6]
            and record["deff7"] == optics[(name, "hydro_deff.txt")][45, 6],
            "serialized record",
        )
    base = arrays["baseline"]
    check(np.array_equal(base["bt"], base["direct_bt"]), "baseline K/direct")
    check(
        sha(data["results/baseline/out/k/radiance.txt"])
        == json.loads(data["results/baseline/receipt.json"])["outputs"][
            "k/radiance.txt"
        ],
        "K radiance hash",
    )
    check(
        data["results/baseline/out/k/radiance.txt"]
        == data["results/baseline/out/direct/radiance.txt"],
        "baseline raw K/direct equality",
    )
    raw_blocks(data["results/baseline/out/k/radiance.txt"])
    check(
        sha(data["results/baseline/out/k/profiles_k.txt"])
        == json.loads(data["results/baseline/receipt.json"])["outputs"][
            "k/profiles_k.txt"
        ],
        "K profiles hash",
    )
    check(base["hydro7"].shape == base["deff7"].shape == (1, 7, 66), "K slot shape")
    ratio = json.loads(data["coordinate_ratio.json"])["ratio"]
    check(
        len(ratio) == 7 and all(math.isfinite(x) and x > 0 for x in ratio),
        "coordinate ratio",
    )
    ktext = data["results/baseline/out/k/profiles_k.txt"].decode("ascii")
    for channel in range(7):
        for field, ntype, saved_field in (
            ("HYDRO", 8, "hydro7"),
            ("HYDRO_DEFF", 7, "deff7"),
        ):
            pattern = (
                r"PROFILES_K\(\s*"
                + str(channel + 1)
                + r"\)%"
                + field
                + r"\s*=\s*\(\s*([\s\S]*?)\s*\)"
            )
            blocks = re.findall(pattern, ktext)
            check(len(blocks) == 1, "K field identity")
            vals = np.array([float(x.replace("D", "E")) for x in blocks[0].split()])
            check(
                vals.shape == (ntype * 66,) and np.isfinite(vals).all(), "K field shape"
            )
            actual = vals.reshape(ntype, 66)[6] * ratio[channel]
            check(
                np.array_equal(actual, base[saved_field][0, channel]), "K scaled slot"
            )
    for i, h in enumerate(HS):
        plus, minus = f"h{i}_plus", f"h{i}_minus"
        dirs = []
        for f in ("hydro.txt", "hydro_deff.txt"):
            delta = (optics[(plus, f)] - optics[(minus, f)]) / (2 * h)
            check(np.argwhere(delta != 0).tolist() == [[45, 6]], "serialized direction")
            dirs.append(delta[45, 6])
        kh = base["hydro7"][0, :, 45]
        kd = base["deff7"][0, :, 45]
        hc = kh * dirs[0]
        dc = kd * dirs[1]
        fd = (arrays[plus]["bt"][0] - arrays[minus]["bt"][0]) / (2 * h)
        row = audit["steps"][str(h)]
        check(np.array_equal(fd, np.array(row["central_fd"])), "FD replay")
        check(
            np.array_equal(hc, np.array(row["hydro_contribution"]))
            and np.array_equal(dc, np.array(row["deff_contribution"])),
            "contribution replay",
        )
        check(np.count_nonzero(fd) == 7, "seven channels")
        k_total = hc + dc
        error = np.abs(fd - k_total)
        check(np.array_equal(k_total, np.array(row["k_total"])), "K total replay")
        check(
            np.array_equal(error, np.array(row["absolute_error"])),
            "absolute error replay",
        )
        check(float(np.max(error)) == row["max_absolute_error"], "max error replay")
        print(f"h={h:g} max |FD - K|={np.max(error):.12g}")
    print(
        "Replay consistency passed; scientific status INCONCLUSIVE. See README for attestation limits."
    )


if __name__ == "__main__":
    main()
